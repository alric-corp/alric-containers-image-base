"""LAB-only: real LAB artifacts and their real GitHub REST records through the binding adapter.

Expected subjects come from tests/fixtures/hgc04/expected.json, a source
independent of the artifact's own validated-index.json. Not part of a
corporate port; the portable tests are in test_artifact_binding.py.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.pipeline.analytics.artifact_binding import bind
from scripts.pipeline.analytics.artifact_input import stage
from scripts.pipeline.analytics.normalize import prepare
from scripts.pipeline.analytics.spdx import AnalyticsError, document, sha256

ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS = ROOT / 'tests/fixtures/sbom-analytics/build-artifacts'
RECORDS = ROOT / 'tests/fixtures/sbom-analytics/artifact-binding'
EXPECTED = json.loads((ROOT / 'tests/fixtures/hgc04/expected.json').read_text())
ORIGIN = dict(repository=EXPECTED['repository'], run_id=EXPECTED['run_id'], run_attempt=EXPECTED['run_attempt'],
              source_sha=EXPECTED['source_sha'], event=EXPECTED['event'], ref=EXPECTED['ref'])


def manifest():
    artifacts = []
    for candidate in EXPECTED['candidates']:
        name = 'sbom-%s-%d' % (candidate['framework'], EXPECTED['run_attempt'])
        record_name = '%s-%d.artifact-api.json' % (candidate['framework'], EXPECTED['run_attempt'])
        record = json.loads((RECORDS / record_name).read_text())
        artifacts.append(dict(framework=candidate['framework'], name=name, path=name + '.zip',
                              artifact_id=record['id'], api_record=record_name,
                              expected_subjects={'index': candidate['digest'], **candidate['platforms']},
                              subjects_source='tests/fixtures/hgc04/expected.json'))
    return dict(schema_version=1, sample_classification='LAB_REAL', origin=dict(ORIGIN),
                repository_id=EXPECTED['repository_id'], image_registry='registry.example.invalid',
                repository_prefix='image-base-', archive_digest_policy='REQUIRED', artifacts=artifacts)


class LabArtifactBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sbom-artifact-binding-lab-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        for path in list(ARTIFACTS.glob('*.zip')) + list(RECORDS.glob('*.artifact-api.json')):
            shutil.copyfile(path, self.inputs / path.name)

    def test_real_records_bind_the_real_archives_and_keep_the_normalized_batch(self):
        receipt = bind(manifest(), self.root / 'bound', base_directory=self.inputs)
        for entry in receipt['artifacts']:
            record = json.loads((self.inputs / (entry['name'][len('sbom-'):] + '.artifact-api.json')).read_text())
            self.assertEqual('sha256:' + entry['archive_sha256'], record['digest'])
            self.assertEqual(set(entry['checks'].values()), {'MATCHED'}, entry['checks'])
            self.assertIs(entry['api_record_expired'], False)
        selection = dict(schema_version=1, origin=dict(ORIGIN), image_registry='registry.example.invalid',
                         repository_prefix='image-base-',
                         artifacts=[dict(framework=a['framework'], name=a['name'], path=a['path'],
                                         artifact_id=a['artifact_id']) for a in manifest()['artifacts']])
        unbound = stage(selection, self.root / 'unbound', base_directory=self.inputs)
        self.assertEqual(receipt['batch_id'], unbound['batch_id'])  # binding refuses, never rewrites data
        projection = prepare(document((self.root / 'bound/context.json').read_bytes()),
                             base_directory=self.root / 'bound')
        self.assertEqual(len(document(projection.records)['observations']), 6)

    def test_real_record_of_another_artifact_is_refused(self):
        value = manifest()
        first, second = value['artifacts']
        first['api_record'], second['api_record'] = second['api_record'], first['api_record']
        with self.assertRaisesRegex(AnalyticsError, 'ARTIFACT_ID_DIFFERS'):
            bind(value, self.root / 'swapped', base_directory=self.inputs)
        self.assertFalse((self.root / 'swapped').exists())
        self.assertEqual(sha256((self.inputs / 'sbom-go1-26-1.zip').read_bytes()),
                         '3d4f92aa57234511ecbcc0d570e1fcbfef3cb4ceaf7f07c20ae1c4ebf97ef2ca')


if __name__ == '__main__':
    unittest.main()
