import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics.normalize import prepare
from scripts.pipeline.analytics.spdx import AnalyticsError, LIMITS, canonical, document
from tests.unit.pipeline.analytics.fixture_support import historical, synthetic


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sbom-normalize-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = synthetic(self.root)

    def test_historical_unit_has_six_observations_and_all_300_package_records(self):
        context = historical(self.root / 'historical')
        data = document(prepare(context).records)
        self.assertEqual(len(data['observations']), 6)
        self.assertEqual(len(data['packages']), 300)
        for row in data['observations']:
            self.assertEqual(row['integrity_check'], 'MATCHED_EXTERNAL_SHA256')
            self.assertEqual(row['validation_record_check'], 'MATCHED')
            self.assertEqual(row['publication_record_check'], 'MATCHED')
            self.assertEqual(row['candidate_identity_check'], 'MATCHED')
            self.assertEqual(row['hosted_verification_status'], 'REPORTED_SUCCESS')
            self.assertEqual(row['cryptographic_authenticity'], 'NOT_REVALIDATED')
            self.assertFalse(row['publication_authority'])

    def test_other_frameworks_work_without_catalog_or_go_name_special_case(self):
        data = document(prepare(self.context).records)
        self.assertEqual({r['framework'] for r in data['observations']}, {'python-3.14'})

    def test_optional_metadata_remains_null_or_not_provided(self):
        rows = document(prepare(self.context).records)['observations']
        for row in rows:
            for field in ('artifact_id', 'source_path', 'source_timestamp', 'source_timestamp_origin'):
                self.assertIsNone(row[field])
            self.assertEqual(row['validation_record_check'], 'NOT_PROVIDED')
            self.assertEqual(row['integrity_check'], 'SHA256_COMPUTED')

    def test_document_is_shared_across_observations_without_duplicate_package_rows(self):
        image = copy.deepcopy(self.context['images'][0])
        image['framework'] = 'another-compatible-framework'
        image['image_repository'] = 'example.invalid/another-image'
        self.context['images'].append(image)
        data = document(prepare(self.context).records)
        self.assertEqual(len(data['observations']), 6)
        self.assertEqual(len(data['packages']), 9)
        self.assertEqual(len({r['sbom_sha256'] for r in data['observations']}), 3)

    def test_different_run_and_attempt_preserve_distinct_observations_of_same_documents(self):
        before = document(prepare(self.context).records)
        self.context['origin'].update(run_id=18, run_attempt=2)
        after = document(prepare(self.context).records)
        self.assertEqual(before['packages'], after['packages'])
        self.assertTrue({r['observation_id'] for r in before['observations']}.isdisjoint(
                        r['observation_id'] for r in after['observations']))

    def test_input_order_does_not_change_record_or_batch_identity(self):
        context = historical(self.root / 'historical')
        before = prepare(context)
        context['images'].reverse()
        for image in context['images']:image['documents'].reverse()
        after = prepare(context)
        self.assertEqual(before, after)

    def test_pr_event_and_ref_are_retained_without_publication_authority(self):
        self.context['origin'].update(event='pull_request', ref='refs/pull/114/merge')
        rows = document(prepare(self.context).records)['observations']
        self.assertTrue(all(r['event'] == 'pull_request' and r['ref'] == 'refs/pull/114/merge'
                            and r['publication_authority'] is False for r in rows))
        self.assertTrue(all('stable' not in r and 'release_id' not in r for r in rows))

    def test_pr_context_cannot_be_relabelled_as_native_push(self):
        self.context['origin'].update(ref='refs/pull/114/merge')
        with self.assertRaisesRegex(AnalyticsError, 'event/ref'):prepare(self.context)

    def test_wrong_subject_or_raw_hash_rejects_entire_input(self):
        self.context['images'][0]['documents'][1]['sha256'] = '0'*64
        with self.assertRaisesRegex(AnalyticsError, 'hash mismatch'):prepare(self.context)
        del self.context['images'][0]['documents'][1]['sha256']
        self.context['images'][0]['platforms']['linux/amd64'] = 'sha256:' + '0'*64
        with self.assertRaisesRegex(AnalyticsError, 'subject checksum'):prepare(self.context)

    def test_validation_publication_and_candidate_mismatches_are_rejected(self):
        for record, field, replacement in [('validation', 'digest', 'sha256:'+'0'*64),
                ('publication', 'remote_digest', 'sha256:'+'0'*64), ('candidate_identity', 'run_id', 7)]:
            context = historical(self.root / record)
            path = Path(context['images'][0][record]['path'])
            value = json.loads(path.read_bytes());value[field] = replacement
            path.write_bytes(canonical(value))
            with self.subTest(record=record), self.assertRaises(AnalyticsError):prepare(context)

    def test_changed_published_index_is_not_accepted_by_record_claims(self):
        context = historical(self.root / 'historical')
        path = Path(context['images'][0]['publication']['remote_index_path'])
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'published index differs'):prepare(context)

    def test_incomplete_duplicate_and_inconsistent_document_sets_rejected(self):
        for mode in ('missing', 'duplicate', 'platform'):
            context = copy.deepcopy(self.context)
            docs = context['images'][0]['documents']
            if mode == 'missing':docs.pop()
            elif mode == 'duplicate':docs[1] = docs[0]
            else:docs[1]['document_platform'] = 'linux/s390x'
            with self.subTest(mode=mode), self.assertRaises(AnalyticsError):prepare(context)

    def test_unknown_schema_fields_boolean_ids_and_invalid_digests_rejected(self):
        for mutate in (lambda c:c.update(schema_version=2), lambda c:c.update(schema_version=True),
                       lambda c:c.update(unrecognized=True), lambda c:c['origin'].update(run_id=True),
                       lambda c:c['origin'].update(source_sha='main'),
                       lambda c:c['origin'].update(run_id=2**63)):
            context = copy.deepcopy(self.context);mutate(context)
            with self.assertRaises(AnalyticsError):prepare(context)

    def test_namespace_is_not_a_document_identity_or_deduplication_key(self):
        rows = document(prepare(self.context).records)['observations']
        self.assertEqual(len({r['document_namespace'] for r in rows}), 1)
        self.assertEqual(len({r['sbom_sha256'] for r in rows}), 3)

    def test_timestamp_keeps_offset_and_requires_its_declared_source(self):
        self.context['origin'].update(source_timestamp='2026-10-08T13:08:48-03:00')
        with self.assertRaisesRegex(AnalyticsError, 'explicit origin'):prepare(self.context)
        self.context['origin']['source_timestamp_origin'] = 'external preserved Git committer date'
        rows = document(prepare(self.context).records)['observations']
        self.assertTrue(all(r['source_timestamp'] == '2026-10-08T13:08:48-03:00' for r in rows))

    def test_batch_and_document_limits_are_enforced(self):
        for key, limit in (('batch_bytes', 1), ('documents', 2), ('batch_packages', 2)):
            with self.subTest(key=key), patch.dict(LIMITS, {key:limit}), self.assertRaises(AnalyticsError):
                prepare(self.context)

    def test_document_platform_is_not_invented_as_component_architecture(self):
        data = document(prepare(self.context).records)
        self.assertTrue(any(r['document_platform'] == 'linux/arm64' for r in data['observations']))
        self.assertTrue(all('architecture' not in r and 'document_platform' not in r for r in data['packages']))
