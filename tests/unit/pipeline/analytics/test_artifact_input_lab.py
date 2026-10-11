"""LAB-only links between the artifact adapter and the proven LAB S3/Athena batch.

The portable adapter tests live in test_artifact_input.py. These depend on the
LAB frozen plan and release platform and are not part of a corporate port.
"""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.pipeline.analytics.artifact_input import CONSUMED, stage
from scripts.pipeline.analytics.normalize import prepare
from scripts.pipeline.analytics.spdx import checksum, document, sha256
from tests.unit.pipeline.analytics.test_artifact_input import HISTORICAL, REGISTRY, ZIPS, members, selection

ROOT = Path(__file__).resolve().parents[4]
LAB_VALUES = ('712107929769', 'us-east-1', 'alric-distroless-sbom', 'poc_distroless', 'itau-github-repo-factory',
              'lab-sbom-athena', '6ae0d5a463a20961e4431cb86d7d969ff2157bf25428a22dd08aa119632548b6')


def frozen_records():
    with zipfile.ZipFile(ROOT / 'tests/fixtures/sbom-analytics/lab-frozen-plan.zip') as archive:
        return json.loads(archive.read('batch/reports/records.json'))


class LabProofLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sbom-artifact-input-lab-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def staged(self, value, name):
        receipt = stage(value, self.root / name)
        context = document((self.root / name / 'context.json').read_bytes())
        return receipt, prepare(context, base_directory=self.root / name)

    def test_real_artifacts_reproduce_the_records_proven_in_s3_and_athena(self):
        receipt, projection = self.staged(selection(ZIPS), 'real')
        data, frozen = document(projection.records), frozen_records()
        self.assertEqual(data['packages'], frozen['packages'])
        self.assertEqual((len(data['observations']), len(data['packages'])), (6, 300))
        shared = ('sbom_sha256', 'predicate_digest', 'framework', 'image_index_digest', 'subject_digest', 'sbom_scope',
                  'document_platform', 'document_namespace', 'spdx_version', 'spdx_created', 'package_count',
                  'relationship_count', 'raw_spdx_path', 'source_path', 'artifact_id', 'integrity_check',
                  'subject_check', 'validation_record_check', 'validation_record_sha256', 'repository', 'run_id',
                  'run_attempt', 'source_sha', 'event', 'ref')
        project = lambda rows: sorted((tuple(r[k] for k in shared) for r in rows), key=repr)
        self.assertEqual(project(data['observations']), project(frozen['observations']))
        for row in data['observations']:
            self.assertEqual(row['image_repository'], REGISTRY + '/image-base-' + row['framework'])
            self.assertEqual((row['publication_record_check'], row['candidate_identity_check'],
                              row['hosted_verification_status']), ('NOT_PROVIDED',) * 3)
            self.assertEqual((row['cryptographic_authenticity'], row['publication_authority']), ('NOT_REVALIDATED', False))
        raw = dict(projection.materials)
        for path in ZIPS.values():
            original = members(path)
            for name in ('sbom/sbom-index.spdx.json', 'sbom/sbom-x86_64.spdx.json', 'sbom/sbom-aarch64.spdx.json'):
                self.assertEqual(raw['raw/spdx/sha256=' + sha256(original[name]) + '/document.spdx.json'], original[name])
            self.assertEqual(raw['raw/records/sha256=' + sha256(original['validated-index.json']) + '/record.json'],
                             original['validated-index.json'])
        for item in receipt['artifacts']:
            self.assertEqual(item['archive_sha256'], sha256(ZIPS[item['framework']].read_bytes()))
            self.assertEqual(sorted(item['consumed']), sorted(CONSUMED))
            self.assertEqual(sorted(item['unconsumed']), ['binfmt-evidence.json', 'melange-environment-evidence.json',
                                                          'melange-reproducibility-evidence.json'])
        self.assertEqual((receipt['status'], receipt['cloud_calls'], receipt['batch_id']), ('STAGED', 0, projection.batch_id))

    def test_spdx_checksum_equals_the_release_manifest_digest_it_replaces(self):
        from scripts.pipeline.release.release_manifest import checksum as release_checksum
        for path in ZIPS.values():
            for name, body in members(path).items():
                if name.startswith('sbom/'):
                    self.assertEqual(checksum(document(body)), release_checksum(json.loads(body)))

    def test_no_lab_destination_or_round_value_in_consumer_code_or_new_identity_records(self):
        for module in ('artifact_input', 'normalize', 'spdx', 'parquet', 'ingestion_types', 'snapshot',
                       's3_ingestion', 'ingest'):
            source = (ROOT / 'scripts/pipeline/analytics' / (module + '.py')).read_text()
            for value in LAB_VALUES:
                self.assertNotIn(value, source, module)
        other = dict(HISTORICAL, repository='example-org/example-factory', run_id=4242, run_attempt=2)
        _, projection = self.staged(selection(ZIPS, origin=other), 'other')
        for value in LAB_VALUES:
            self.assertNotIn(value.encode(), projection.records)


if __name__ == '__main__':
    unittest.main()
