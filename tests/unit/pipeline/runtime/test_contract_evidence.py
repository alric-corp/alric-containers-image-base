import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts.pipeline.artifacts.oci_artifact import INDEX, MANIFEST, verify
from scripts.pipeline.runtime import runtime_images as runtime

REPOSITORY = 'alric-corp/alric-containers-image-base'
REVISION = 'a' * 40


def layout_fixture(path, label):
    (path / 'blobs/sha256').mkdir(parents=True)

    def store(value):
        raw = json.dumps(value).encode()
        digest = hashlib.sha256(raw).hexdigest()
        (path / 'blobs/sha256' / digest).write_bytes(raw)
        return {'digest': 'sha256:' + digest, 'size': len(raw)}

    manifests = []
    for arch in ('amd64', 'arm64'):
        config = store({'os': 'linux', 'architecture': arch})
        layer = store({'fixture': label, 'architecture': arch})
        manifest = store({'schemaVersion': 2, 'config': config, 'layers': [layer]})
        manifests.append(dict(manifest, mediaType=MANIFEST,
                              platform={'os': 'linux', 'architecture': arch}))
    index = store({'schemaVersion': 2, 'mediaType': INDEX, 'manifests': manifests})
    (path / 'index.json').write_text(json.dumps({'manifests': [dict(index, mediaType=INDEX)]}))
    expected = verify(path)
    (path / 'validated-index.json').write_text(json.dumps(expected))
    return expected


class ContractEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.layout = self.root / 'image.oci'
        self.expected = layout_fixture(self.layout, 'runtime')
        self.dev_layout = self.root / 'dev.oci'
        self.dev_expected = layout_fixture(self.dev_layout, 'dev')
        self.reports = self.root / 'reports'
        self.reports.mkdir()
        self.framework = 'nodejs24'
        self.attempt = 1
        self.artifacts = []
        self.jobs = []

    def job(self, attempt, conclusion='success', framework=None):
        self.jobs.append({'id': 200 + len(self.jobs), 'run_id': 41, 'run_attempt': attempt,
                          'head_sha': REVISION, 'status': 'completed', 'conclusion': conclusion,
                          'name': f'build-base-images / Functional contract / runtime / Runtime '
                                  f'{framework or self.framework} (both architectures)'})

    def add(self, attempt, expected=None, dev_expected=None):
        expected = expected or self.expected
        name = f'runtime-{self.framework}-{attempt}'
        directory = self.reports / name
        directory.mkdir()
        for arch in ('amd64', 'arm64'):
            report = {'schema_version': 1, 'framework': self.framework,
                      'contract': 'compiled' if dev_expected else 'interpreted',
                      'platform': f'linux/{arch}', 'repository': REPOSITORY,
                      'run_id': '41', 'run_attempt': str(attempt), 'revision': REVISION,
                      'index_digest': expected['digest'],
                      'manifest_digest': expected['platforms'][f'linux/{arch}'],
                      'status': 'passed', 'checks': {'fixture': True}}
            if dev_expected:
                report.update(dev_framework=self.framework + '-dev',
                              dev_index_digest=dev_expected['digest'],
                              dev_manifest_digest=dev_expected['platforms'][f'linux/{arch}'])
            (directory / f'runtime-{self.framework}-{arch}.json').write_text(json.dumps(report))
        self.artifacts.append({'id': 100 + attempt, 'name': name, 'expired': False,
                               'workflow_run': {'id': 41, 'head_sha': REVISION}})
        self.job(attempt)
        return directory

    def metadata(self):
        paths = []
        for key, values in [('artifacts', self.artifacts), ('jobs', self.jobs)]:
            path = self.root / (key + '.json')
            # Exercise the actual gh --paginate --slurp layout with two pages.
            pages = [{'total_count': len(values), key: values[:1]},
                     {'total_count': len(values), key: values[1:]}]
            path.write_text(json.dumps(pages))
            paths.append(path)
        return paths

    def call(self, **overrides):
        artifacts, jobs = self.metadata()
        options = dict(layout=self.layout, artifact_metadata=artifacts, job_metadata=jobs,
                       run_id='41', attempt=str(self.attempt), repository=REPOSITORY,
                       revision=REVISION, dev_layout=self.dev_layout)
        options.update(overrides)
        return runtime.gate(self.reports, self.framework, **options)

    def report(self, directory, arch='arm64'):
        return directory / f'runtime-{self.framework}-{arch}.json'

    def assert_failed(self, result, fragment=None):
        self.assertIs(result['passed'], False, result)
        if fragment:
            self.assertIn(fragment, result['error'])

    def test_first_attempt_with_flat_download_is_approved(self):
        directory = self.add(1)
        for path in directory.iterdir():
            path.rename(self.reports / path.name)
        directory.rmdir()
        result = self.call()
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['index_digest'], self.expected['digest'])
        self.assertEqual(result['selected_attempt'], 1)
        self.assertFalse(result['reused'])

    def test_attempt_two_reuses_one_with_carried_success_and_no_build(self):
        self.add(1)
        self.attempt = 2
        self.job(2)  # GitHub can carry a success to attempt2 without execution.
        before = {str(p): p.read_bytes() for p in self.layout.rglob('*') if p.is_file()}
        with patch.object(runtime, 'command') as command, \
                patch.object(runtime, 'run_platform') as execute:
            result = self.call()
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['selected_attempt'], 1)
        self.assertEqual(result['latest_producer_attempt'], 2)
        self.assertTrue(result['reused'])
        command.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.layout.rglob('*') if p.is_file()})

    def test_attempts_one_and_two_choose_two(self):
        self.add(1)
        self.add(2)
        self.attempt = 2
        self.assertEqual(self.call()['selected_attempt'], 2)

    def test_attempt_ten_is_newer_than_two(self):
        self.add(2)
        self.add(10)
        self.attempt = 10
        self.assertEqual(self.call()['selected_attempt'], 10)

    def test_well_formed_different_candidate_is_not_selected(self):
        self.add(1)
        other = layout_fixture(self.root / 'other.oci', 'other')
        self.add(2, other)
        self.attempt = 2
        result = self.call()
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['selected_attempt'], 1)

    def test_only_mismatched_digest_is_rejected(self):
        other = layout_fixture(self.root / 'other.oci', 'other')
        self.add(1, other)
        self.assert_failed(self.call(), 'no functional evidence matches')

    def test_missing_artifact_is_rejected_even_when_download_action_succeeds(self):
        self.job(1)
        self.assert_failed(self.call(), 'missing functional contract artifact')

    def test_failed_download_cannot_use_partial_files(self):
        self.add(1)
        self.assert_failed(self.call(download_result='failure'), 'download failed')

    def test_missing_platform_cannot_be_filled_from_another_attempt(self):
        first = self.add(1)
        second = self.add(2)
        self.attempt = 2
        self.report(first, 'amd64').unlink()
        self.report(second, 'arm64').unlink()
        self.assert_failed(self.call(), 'exactly both platform reports')

    def test_invalid_json_or_duplicate_fields_fail(self):
        directory = self.add(1)
        for raw in ('{', '[]', '{"status":"failed","status":"passed"}', '{"value":NaN}'):
            with self.subTest(raw=raw):
                self.report(directory).write_text(raw)
                self.assert_failed(self.call())

    def test_wrong_context_framework_platform_and_missing_digest_fail(self):
        directory = self.add(1)
        path = self.report(directory)
        original = json.loads(path.read_text())
        cases = [('run_id', '42'), ('run_attempt', '2'), ('repository', 'other/repo'),
                 ('revision', 'b' * 40), ('framework', 'python3-13'),
                 ('platform', 'linux/amd64'), ('contract', 'compiled'),
                 ('index_digest', ''), ('manifest_digest', 'sha256:bad'),
                 ('status', 'unknown'), ('checks', {}), ('schema_version', True)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                report = dict(original, **{field: value})
                path.write_text(json.dumps(report))
                self.assert_failed(self.call())
        for field in ('index_digest', 'run_id', 'run_attempt', 'framework', 'schema_version'):
            with self.subTest(missing=field):
                report = dict(original)
                del report[field]
                path.write_text(json.dumps(report))
                self.assert_failed(self.call())

    def test_conflicting_platform_index_or_manifest_fails(self):
        directory = self.add(1)
        path = self.report(directory)
        original = json.loads(path.read_text())
        for field in ('index_digest', 'manifest_digest'):
            with self.subTest(field=field):
                path.write_text(json.dumps(dict(original, **{field: 'sha256:' + 'b' * 64})))
                self.assert_failed(self.call())

    def test_duplicate_artifact_name_is_not_hidden_by_download_latest(self):
        self.add(1)
        self.artifacts.append(dict(self.artifacts[0], id=999))
        self.assert_failed(self.call(), 'duplicate/conflicting artifacts')

    def test_artifact_from_another_run_or_revision_is_rejected(self):
        self.add(1)
        self.artifacts[0]['workflow_run']['id'] = 42
        self.assert_failed(self.call(), 'another workflow run')
        self.artifacts[0]['workflow_run'] = {'id': 41, 'head_sha': 'b' * 40}
        self.assert_failed(self.call(), 'artifact revision')

    def test_expired_or_future_artifact_is_rejected(self):
        self.add(1)
        self.artifacts[0]['expired'] = True
        self.assert_failed(self.call(), 'expired')
        self.artifacts[0].update(expired=False, name='runtime-nodejs24-2')
        self.assert_failed(self.call(), 'future attempt')

    def test_latest_failed_producer_without_new_reports_blocks_reuse(self):
        self.add(1)
        self.attempt = 2
        self.job(2, 'failure')
        self.assert_failed(self.call(), 'latest functional producer did not succeed')

    def test_latest_failed_report_does_not_fall_back_to_old_pass(self):
        self.add(1)
        directory = self.add(2)
        self.attempt = 2
        path = self.report(directory)
        path.write_text(json.dumps(dict(json.loads(path.read_text()), status='failed')))
        self.assert_failed(self.call(), 'no fallback to an older PASS')

    def test_failed_old_attempt_can_be_followed_by_new_approved_attempt(self):
        directory = self.add(1)
        path = self.report(directory)
        path.write_text(json.dumps(dict(json.loads(path.read_text()), status='failed')))
        self.jobs[0]['conclusion'] = 'failure'
        self.add(2)
        self.attempt = 2
        self.assertTrue(self.call()['passed'])

    def test_failure_of_another_framework_does_not_block_this_framework(self):
        self.add(1)
        self.job(1, 'failure', 'python3-13')
        self.assertTrue(self.call()['passed'])

    def test_missing_ambiguous_or_incomplete_producer_blocks(self):
        self.add(1)
        original = copy.deepcopy(self.jobs)
        for jobs in ([], original + [dict(original[0], id=900)],
                     [dict(original[0], status='in_progress', conclusion=None)]):
            with self.subTest(jobs=jobs):
                self.jobs = jobs
                self.assert_failed(self.call())

    def test_truncated_metadata_and_missing_download_directory_fail(self):
        self.add(1)
        artifacts, jobs = self.metadata()
        artifacts.write_text(json.dumps([{'total_count': 2, 'artifacts': self.artifacts}]))
        result = runtime.gate(self.reports, self.framework, self.layout, artifacts, jobs,
                              '41', '1', REPOSITORY, REVISION)
        self.assert_failed(result, 'incomplete or duplicate artifacts')
        self.add(2)
        self.attempt = 2
        shutil.rmtree(self.reports / 'runtime-nodejs24-2')
        self.assert_failed(self.call(), 'complete run inventory')

    def test_oci_blob_or_validation_record_tampering_blocks_gate(self):
        self.add(1)
        path = self.layout / 'blobs/sha256' / self.expected['digest'][7:]
        path.write_bytes(path.read_bytes() + b' ')
        self.assert_failed(self.call(), 'blob OCI alterado')

    def test_compiled_pair_is_bound_to_both_current_indexes(self):
        self.framework = 'go1-26'
        directory = self.add(1, dev_expected=self.dev_expected)
        self.assertTrue(self.call()['passed'])
        other_dev = self.root / 'other-dev.oci'
        layout_fixture(other_dev, 'changed-dev')
        self.assert_failed(self.call(dev_layout=other_dev), 'no functional evidence matches')
        path = self.report(directory)
        report = json.loads(path.read_text())
        report['dev_manifest_digest'] = 'sha256:' + 'b' * 64
        path.write_text(json.dumps(report))
        self.assert_failed(self.call(), 'functional build manifest')

    def test_legacy_status_only_reports_do_not_authorize_publication(self):
        directory = self.add(1)
        for path in directory.iterdir():
            path.write_text('{"status":"passed"}')
        self.assert_failed(self.call())

    def test_cli_reuses_and_records_exact_oci_identity(self):
        self.add(1)
        self.attempt = 2
        self.job(2)
        artifacts, jobs = self.metadata()
        output = self.root / 'gate.json'
        result = subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.runtime.runtime_images',
                                 str(self.layout), '--gate', self.framework, '--reports', str(self.reports),
                                 '--requested', '["nodejs24"]', '--run-id', '41', '--run-attempt', '2',
                                 '--repository', REPOSITORY, '--revision', REVISION,
                                 '--artifact-metadata', str(artifacts), '--job-metadata', str(jobs),
                                 '--gate-output', str(output)],
                                cwd=runtime.ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = json.loads(output.read_text())
        self.assertTrue(evidence['passed'])
        self.assertEqual(evidence['selected_attempt'], 1)
        self.assertEqual(evidence['index_digest'], self.expected['digest'])
        self.assertEqual(evidence['platforms'], self.expected['platforms'])


class PublicationWiringTests(unittest.TestCase):
    def test_download_is_scoped_and_publisher_has_no_base_rebuild(self):
        workflow = yaml.safe_load((runtime.ROOT / '.github/workflows/build-base-images.yml').read_text())
        steps = workflow['jobs']['build-push']['steps']
        download = next(step for step in steps if step.get('id') == 'contract')['with']
        self.assertEqual(download['run-id'], '${{ github.run_id }}')
        self.assertEqual(download['repository'], '${{ github.repository }}')
        self.assertIn('github-token', download)
        self.assertEqual(download['pattern'], 'runtime-${{ matrix.framework }}-[0-9]*')
        self.assertFalse(download['merge-multiple'])
        self.assertEqual(download['digest-mismatch'], 'error')
        commands = '\n'.join(step.get('run', '') for step in steps)
        self.assertIn('jobs?filter=all&per_page=100', commands)
        self.assertIn('--paginate --slurp', commands)
        self.assertIn('--dev-layout runtime-dev.oci', commands)
        for rebuild in ('apko build', 'melange build', 'oci_artifact prepare', 'docker build'):
            self.assertNotIn(rebuild, commands)
        gate = next(index for index, step in enumerate(steps)
                    if step['name'] == 'Require the functional contract of this framework')
        publish = next(index for index, step in enumerate(steps)
                       if step['name'] == 'Publish validated OCI artifact (multi-arch)')
        self.assertLess(gate, publish)


if __name__ == '__main__':
    unittest.main()
