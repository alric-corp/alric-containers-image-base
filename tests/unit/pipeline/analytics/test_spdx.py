import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics.spdx import AnalyticsError, LIMITS, document, packages
from tests.unit.pipeline.analytics.fixture_support import historical, mutate_spdx, synthetic


class SpdxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sbom-spdx-')
        self.addCleanup(self.temp.cleanup)
        self.context = synthetic(self.temp.name)
        self.item = self.context['images'][0]['documents'][0]
        self.subject = self.context['images'][0]['image_index_digest']

    def parse(self):
        return packages(Path(self.item['path']).read_bytes(), self.subject)

    def test_real_documents_include_packages_references_licenses_and_relationships(self):
        ctx = historical(Path(self.temp.name) / 'historical')
        counts = {}
        for image in ctx['images']:
            for item in image['documents']:
                subject = image['image_index_digest'] if item['sbom_scope'] == 'index' else image['platforms'][item['document_platform']]
                value, rows, created, relationships = packages(Path(item['path']).read_bytes(), subject)
                counts[image['framework'], item['document_platform']] = len(rows)
                self.assertEqual(sum(r['is_document_subject'] for r in rows), 1)
                self.assertTrue(any(r['purls'] for r in rows))
                self.assertEqual(created, '2026-10-08T16:08:48Z')
                self.assertGreater(relationships, 0)
                self.assertEqual(value['spdxVersion'], 'SPDX-2.3')
        self.assertEqual(sorted(counts.values()), [3, 3, 23, 23, 124, 124])

    def test_subject_must_come_from_external_expected_identity(self):
        with self.assertRaisesRegex(AnalyticsError, 'subject checksum'):
            packages(Path(self.item['path']).read_bytes(), 'sha256:' + '0'*64)

    def test_optional_values_are_null_and_homonyms_retain_distinct_ids(self):
        _, rows, created, relations = self.parse()
        others = [r for r in rows if not r['is_document_subject']]
        self.assertEqual(len(others), 2)
        self.assertEqual({r['package_name'] for r in others}, {'same-name'})
        self.assertEqual(len({r['package_spdx_id'] for r in others}), 2)
        self.assertTrue(all(r['license_declared'] is None and r['purls'] is None for r in others))
        self.assertIsNone(created)
        self.assertIsNone(relations)

    def test_source_characters_special_license_values_and_expressions_are_unchanged(self):
        names = ['  café+Lib / A\t', 'Cafe\u0301']
        def transform(d):
            d['packages'][1].update(name=names[0], versionInfo=' 1:2.0+Rev-A\t', licenseDeclared='NOASSERTION', licenseConcluded='NONE')
            d['packages'][2].update(name=names[1], licenseDeclared='(MIT OR Apache-2.0) AND BSD-3-Clause')
        mutate_spdx(self.context, transform)
        rows = {r['package_spdx_id']:r for r in self.parse()[1]}
        self.assertEqual(rows['SPDXRef-one']['package_name'], names[0])
        self.assertEqual(rows['SPDXRef-one']['package_version'], ' 1:2.0+Rev-A\t')
        self.assertEqual(rows['SPDXRef-one']['license_declared'], 'NOASSERTION')
        self.assertEqual(rows['SPDXRef-one']['license_concluded'], 'NONE')
        self.assertEqual(rows['SPDXRef-two']['package_name'], names[1])
        self.assertEqual(rows['SPDXRef-two']['license_declared'], '(MIT OR Apache-2.0) AND BSD-3-Clause')

    def test_multiple_purls_and_other_refs_do_not_multiply_package_rows(self):
        refs = [dict(referenceCategory='PACKAGE-MANAGER', referenceType='purl', referenceLocator='pkg:apk/wolfi/a@1'),
                dict(referenceCategory='PACKAGE-MANAGER', referenceType='purl', referenceLocator='pkg:generic/a@1', comment='source spelling'),
                dict(referenceCategory='SECURITY', referenceType='cpe23Type', referenceLocator='cpe:2.3:a:a:a:1:*:*:*:*:*:*:*')]
        mutate_spdx(self.context, lambda d: d['packages'][1].update(externalRefs=refs))
        _, rows, _, _ = self.parse()
        self.assertEqual(len(rows), 3)
        row = next(r for r in rows if r['package_spdx_id'] == 'SPDXRef-one')
        self.assertEqual(row['purls'], [r['referenceLocator'] for r in refs[:2]])
        self.assertEqual(len(row['external_references']), 3)
        self.assertEqual(row['external_references'][1]['comment'], 'source spelling')

    def test_duplicate_package_identifier_rejected(self):
        mutate_spdx(self.context, lambda d: d['packages'].append(copy.deepcopy(d['packages'][1])))
        with self.assertRaisesRegex(AnalyticsError, 'duplicate package SPDXID'):
            self.parse()

    def test_malformed_duplicate_keys_and_nonfinite_json_rejected(self):
        for raw in (b'{', b'{"x":1,"x":2}', b'{"a":{"x":1,"x":2}}', b'{"x":NaN}', b'{"x":1e99999}'):
            with self.subTest(raw=raw), self.assertRaises(AnalyticsError):
                document(raw)

    def test_unknown_spdx_version_rejected(self):
        mutate_spdx(self.context, lambda d: d.update(spdxVersion='SPDX-3.0'))
        with self.assertRaisesRegex(AnalyticsError, 'unsupported SPDX'):
            self.parse()

    def test_missing_or_ambiguous_document_root_rejected(self):
        original = Path(self.item['path']).read_bytes()
        for describes in ([], ['SPDXRef-one', 'SPDXRef-image'], ['SPDXRef-missing'], ['SPDXRef-image', 'SPDXRef-image']):
            Path(self.item['path']).write_bytes(original)
            mutate_spdx(self.context, lambda d: d.update(documentDescribes=describes))
            with self.subTest(describes=describes), self.assertRaises(AnalyticsError):
                self.parse()

    def test_relationship_cannot_supply_a_conflicting_root(self):
        mutate_spdx(self.context, lambda d: d.update(relationships=[dict(spdxElementId='SPDXRef-DOCUMENT',
            relationshipType='DESCRIBES', relatedSpdxElement='SPDXRef-one')]))
        with self.assertRaisesRegex(AnalyticsError, 'ambiguous relationship'):
            self.parse()

    def test_no_dependency_classification_is_invented_from_package_order(self):
        _, rows, _, _ = self.parse()
        self.assertTrue(all('direct_dependency' not in r and 'component_architecture' not in r for r in rows))

    def test_wrong_optional_types_and_conflicting_sha256_rejected(self):
        original = Path(self.item['path']).read_bytes()
        for mutation in (lambda d: d['packages'][1].update(versionInfo=True),
                         lambda d: d['packages'][1].update(externalRefs={}),
                         lambda d: d['packages'][0]['checksums'].append(dict(algorithm='SHA256', checksumValue='0'*64))):
            Path(self.item['path']).write_bytes(original)
            mutate_spdx(self.context, mutation)
            with self.assertRaises(AnalyticsError):self.parse()

    def test_size_count_and_depth_limits_rejected(self):
        raw = Path(self.item['path']).read_bytes()
        for key, limit in (('document_bytes', 8), ('packages', 2), ('depth', 1)):
            with self.subTest(key=key), patch.dict(LIMITS, {key:limit}), self.assertRaises(AnalyticsError):
                packages(raw, self.subject)
