import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.pipeline.runtime import retry_lab as lab, runtime_images as runtime
from tests.unit.pipeline.runtime.test_contract_evidence import layout_fixture

ROOT = Path(__file__).resolve().parents[4]
REVISION = 'a' * 40
NOW = datetime(2026, 9, 14, 11, 1, tzinfo=timezone.utc)


class RetryLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {'GITHUB_EVENT_NAME': 'workflow_dispatch',
                    'GITHUB_REPOSITORY': lab.REPOSITORY, 'GITHUB_REF': 'refs/heads/main',
                    'GITHUB_SHA': REVISION, 'GITHUB_WORKFLOW_SHA': REVISION,
                    'GITHUB_WORKFLOW_REF': f'{lab.REPOSITORY}/{lab.WORKFLOW}@refs/heads/main',
                    'GITHUB_RUN_ID': '41', 'GITHUB_RUN_ATTEMPT': '1'}
        self.event = {'inputs': {'confirmation': lab.CONFIRMATION, 'reviewed-sha': REVISION}}
        self.ctx = lab.context(self.env, self.event)
        self.layout = self.root / 'image.oci'
        self.dev = self.root / 'dev.oci'
        self.expected = layout_fixture(self.layout, 'runtime-lab')
        self.dev_expected = layout_fixture(self.dev, 'dev-lab')
        self.reports = self.root / 'reports'
        self.reports.mkdir()
        for arch in ('amd64', 'arm64'):
            report = {'schema_version': 1, 'framework': 'go1-26', 'contract': 'compiled',
                      'platform': f'linux/{arch}', 'repository': lab.REPOSITORY,
                      'run_id': '41', 'run_attempt': '1', 'revision': REVISION,
                      'status': 'passed', 'checks': {'fixture': True},
                      'index_digest': self.expected['digest'],
                      'manifest_digest': self.expected['platforms'][f'linux/{arch}'],
                      'dev_framework': 'go1-26-dev', 'dev_index_digest': self.dev_expected['digest'],
                      'dev_manifest_digest': self.dev_expected['platforms'][f'linux/{arch}']}
            (self.reports / f'runtime-go1-26-{arch}.json').write_text(json.dumps(report))
        names = ['Lab request'] + [f'Lab build / validate / {name}' for name in
                                  ('Compile certs with melange', 'Validate go1-26', 'Validate go1-26-dev')]
        names += ['Lab contract / runtime / Runtime go1-26 (both architectures)']
        self.jobs = [self.job(100 + n, name) for n, name in enumerate(names)]
        self.jobs.append(self.job(200, lab.CONSUMER, status='in_progress', conclusion=None,
                                  started_at='2026-09-14T10:06:00Z', completed_at=None))
        self.artifacts = [self.artifact(300 + n, name) for n, name in enumerate(
            ('validated-oci-go1-26', 'validated-oci-go1-26-dev', 'runtime-go1-26-1'))]

    def job(self, identifier, name, **overrides):
        job = {'id': identifier, 'name': name, 'run_id': 41, 'run_attempt': 1,
               'head_sha': REVISION, 'status': 'completed', 'conclusion': 'success',
               'started_at': '2026-09-14T10:00:00Z', 'completed_at': '2026-09-14T10:05:00Z',
               'steps': [{'number': 1, 'name': 'Actual producer step', 'status': 'completed',
                          'conclusion': 'success', 'started_at': '2026-09-14T10:01:00Z',
                          'completed_at': '2026-09-14T10:04:00Z'}]}
        return dict(job, **overrides)

    def artifact(self, identifier, name):
        return {'id': identifier, 'name': name, 'expired': False, 'size_in_bytes': 1024,
                'digest': 'sha256:' + hashlib.sha256(name.encode()).hexdigest(),
                'workflow_run': {'id': 41, 'head_sha': REVISION},
                'created_at': '2026-09-14T10:05:00Z', 'expires_at': '2030-09-17T10:05:00Z'}

    @staticmethod
    def pages(key, items):
        return [{'total_count': len(items), key: items[:1]},
                {'total_count': len(items), key: items[1:]}]

    def gate(self):
        for name, items in [('artifacts', self.artifacts), ('jobs', self.jobs)]:
            (self.root / f'{name}.json').write_text(json.dumps(self.pages(name, items)))
        return runtime.gate(self.reports, 'go1-26', self.layout,
                            self.root / 'artifacts.json', self.root / 'jobs.json',
                            '41', self.ctx['run_attempt'], lab.REPOSITORY, REVISION, self.dev)

    def assess(self, baseline=None, gate=None):
        return lab.assess(self.ctx, self.gate() if gate is None else gate,
                          self.pages('artifacts', self.artifacts), self.pages('jobs', self.jobs),
                          baseline, NOW)

    def retry(self, copied=True):
        baseline = self.assess()
        old = self.jobs[-1]
        old.update(status='completed', conclusion='failure', completed_at='2026-09-14T10:08:00Z',
                   steps=[{'number': i, 'name': name, 'conclusion': result, 'status': 'completed'}
                          for i, (name, result) in enumerate(
                              [(lab.RECORD, 'success'), (lab.BASELINE_UPLOAD, 'success'),
                               (lab.BARRIER, 'failure')], 8)])
        if copied:
            self.jobs += [dict(copy.deepcopy(job), id=job['id'] + 1000, run_attempt=2)
                          for job in self.jobs[:-1]]
        self.jobs.append(self.job(201, lab.CONSUMER, run_attempt=2,
                                  status='in_progress', conclusion=None,
                                  started_at='2026-09-14T11:00:00Z', completed_at=None))
        baseline_artifact = self.artifact(400, 'runtime-lab-p1-02-baseline-41')
        baseline_artifact['created_at'] = '2026-09-14T10:07:00Z'
        self.artifacts.append(baseline_artifact)
        self.env['GITHUB_RUN_ATTEMPT'] = '2'
        self.ctx = lab.context(self.env, self.event)
        return baseline

    def test_attempt_one_uses_real_gate_before_expected_failure(self):
        manifest = self.assess()
        self.assertTrue(manifest['gate']['passed'])
        self.assertFalse(manifest['gate']['reused'])
        code, result = lab.barrier(self.ctx, manifest)
        self.assertEqual(code, 42)
        self.assertEqual(result['status'], 'EXPECTED_LAB_FAILURE')

    def test_attempt_two_compares_copied_jobs_artifacts_and_layout_bytes(self):
        before = {str(p): p.read_bytes() for root in (self.layout, self.dev)
                  for p in root.rglob('*') if p.is_file()}
        baseline = self.retry()
        manifest = self.assess(baseline)
        self.assertEqual(manifest['status'], 'REUSE_OBSERVED')
        self.assertTrue(manifest['gate']['reused'])
        self.assertEqual(manifest['gate']['selected_attempt'], 1)
        self.assertEqual(manifest['gate']['latest_producer_attempt'], 2)
        self.assertEqual(lab.barrier(self.ctx, manifest)[0], 0)
        self.assertEqual(len(manifest['producer_comparison']), 5)
        self.assertEqual(before, {str(p): p.read_bytes() for root in (self.layout, self.dev)
                                  for p in root.rglob('*') if p.is_file()})

    def test_first_barrier_cli_emits_marker_and_exits_42(self):
        manifest = self.root / 'execution.json'
        manifest.write_text(json.dumps(self.assess()))
        event = self.root / 'event.json'
        event.write_text(json.dumps(self.event))
        result = subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.runtime.retry_lab',
                                 'barrier', '--manifest', str(manifest)], cwd=ROOT,
                                env=dict(os.environ, **self.env, GITHUB_EVENT_PATH=str(event)),
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'EXPECTED_LAB_FAILURE')

    def test_attempt_two_accepts_original_job_entries_when_not_copied(self):
        manifest = self.assess(self.retry(copied=False))
        self.assertEqual(manifest['gate']['latest_producer_attempt'], 1)
        self.assertEqual(lab.barrier(self.ctx, manifest)[0], 0)

    def test_invalid_inputs_events_repository_ref_and_revision_fail_closed(self):
        for key, value in [('GITHUB_EVENT_NAME', 'push'), ('GITHUB_EVENT_NAME', 'pull_request'),
                           ('GITHUB_REPOSITORY', 'other/fork'), ('GITHUB_REF', 'refs/heads/dev'),
                           ('GITHUB_WORKFLOW_REF', 'other/workflow'), ('GITHUB_SHA', 'short'),
                           ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('GITHUB_RUN_ATTEMPT', '0'),
                           ('GITHUB_RUN_ATTEMPT', '3')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                lab.context(dict(self.env, **{key: value}), self.event)
        for inputs in ({}, {'confirmation': 'do-not-run', 'reviewed-sha': REVISION},
                       dict(self.event['inputs'], destination='stable'),
                       dict(self.event['inputs'], **{'reviewed-sha': 'b' * 40})):
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                lab.context(self.env, {'inputs': inputs})

    def test_missing_or_failed_contract_cannot_reach_expected_barrier(self):
        path = self.reports / 'runtime-go1-26-amd64.json'
        report = json.loads(path.read_text())
        report['status'] = 'failed'
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            self.assess()
        with self.assertRaises((KeyError, ValueError)):
            lab.barrier(self.ctx, {'context': self.ctx, 'status': 'INVALID_SCENARIO'})

    def test_missing_dev_remains_a_real_gate_failure(self):
        self.dev = self.root / 'missing-dev'
        self.assertFalse(self.gate()['passed'])
        with self.assertRaises(ValueError):
            self.assess()

    def test_tampered_oci_and_invalid_report_cannot_be_reused(self):
        baseline = self.retry()
        path = self.reports / 'runtime-go1-26-arm64.json'
        original = path.read_bytes()
        path.write_text('{')
        with self.assertRaises(ValueError):
            self.assess(baseline)
        path.write_bytes(original)
        blob = self.layout / 'blobs/sha256' / self.expected['digest'][7:]
        blob.write_bytes(blob.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            self.assess(baseline)

    def test_newer_functional_failure_invalidates_old_pass(self):
        baseline = self.retry()
        runtime_job = next(j for j in self.jobs if j['run_attempt'] == 2
                           and j['name'].endswith('Runtime go1-26 (both architectures)'))
        runtime_job['conclusion'] = 'failure'
        self.assertFalse(self.gate()['passed'])
        with self.assertRaises(ValueError):
            self.assess(baseline)

    def test_other_run_or_framework_report_cannot_be_reused(self):
        baseline = self.retry()
        path = self.reports / 'runtime-go1-26-arm64.json'
        report = json.loads(path.read_text())
        for key, value in [('run_id', '42'), ('framework', 'go1-25')]:
            with self.subTest(key=key):
                path.write_text(json.dumps(dict(report, **{key: value})))
                self.assertFalse(self.gate()['passed'])
                with self.assertRaises(ValueError):
                    self.assess(baseline)

    def test_wrong_selection_or_status_only_gate_is_rejected(self):
        baseline = self.retry()
        original = self.gate()
        for key, value in [('selected_attempt', 2), ('reused', False), ('passed', None),
                           ('selected_artifact_id', 999), ('latest_producer_job_id', 999)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.assess(baseline, dict(original, **{key: value}))

    def test_rebuild_detected_even_with_identical_oci_digests(self):
        baseline = self.retry()
        job = next(j for j in self.jobs if j['run_attempt'] == 2
                   and j['name'].endswith('Validate go1-26'))
        self.assertTrue(self.gate()['passed'])
        job['started_at'] = '2026-09-14T10:00:01Z'
        with self.assertRaisesRegex(ValueError, 'producer executed again'):
            self.assess(baseline)

    def test_changed_producer_steps_are_not_inherited_evidence(self):
        baseline = self.retry()
        next(j for j in self.jobs if j['id'] == 1102)['steps'][0]['name'] = 'Different execution'
        with self.assertRaisesRegex(ValueError, 'producer executed again'):
            self.assess(baseline)

    def test_incomplete_or_late_producer_execution_metadata_is_rejected(self):
        self.jobs[0]['completed_at'] = '2026-09-14T10:09:00Z'
        with self.assertRaisesRegex(ValueError, 'before consumer'):
            self.assess()
        self.jobs[0]['completed_at'] = '2026-09-14T10:05:00Z'
        self.jobs[0]['steps'] = []
        with self.assertRaisesRegex(ValueError, 'missing producer steps'):
            self.assess()

    def test_artifact_replacement_or_metadata_change_fails_even_when_gate_passes(self):
        baseline = self.retry()
        for field, value in [('id', 999), ('digest', 'sha256:' + 'f' * 64),
                             ('created_at', '2026-09-14T10:06:00Z')]:
            original = self.artifacts[0][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'artifact overwritten'):
                self.artifacts[0][field] = value
                self.assess(baseline)
            self.artifacts[0][field] = original

    def test_missing_expired_or_conflicting_baseline_fails(self):
        baseline = self.retry()
        with self.assertRaises(ValueError):
            self.assess(None)
        original = copy.deepcopy(self.artifacts)
        for records in (original[:-1], original + [dict(original[-1], id=401)]):
            self.artifacts = records
            with self.assertRaises(ValueError):
                self.assess(baseline)
        self.artifacts = original
        self.artifacts[-1]['expired'] = True
        with self.assertRaises(ValueError):
            self.assess(baseline)

    def test_failure_before_or_instead_of_barrier_is_not_an_accepted_scenario(self):
        baseline = self.retry()
        failed = next(j for j in self.jobs if j['id'] == 200)
        failed['steps'][-1]['name'] = 'Download failed'
        with self.assertRaisesRegex(ValueError, 'solely at the controlled barrier'):
            self.assess(baseline)

    def test_baseline_after_barrier_and_other_context_are_rejected(self):
        baseline = self.retry()
        bad = copy.deepcopy(baseline)
        bad['context']['head_sha'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'baseline context'):
            self.assess(bad)
        failed = next(j for j in self.jobs if j['id'] == 200)
        failed['steps'][1]['number'] = 20
        with self.assertRaisesRegex(ValueError, 'before barrier'):
            self.assess(baseline)

    def test_expired_or_incomplete_metadata_fails(self):
        self.artifacts[0]['expires_at'] = '2026-09-13T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.assess()
        with self.assertRaises(ValueError):
            lab.assess(self.ctx, self.gate(), {'total_count': 9, 'artifacts': []},
                       self.pages('jobs', self.jobs), now=NOW)

    def test_real_gate_and_lab_cli_across_attempts(self):
        baseline = self.assess()
        baseline_file = self.root / 'baseline.json'
        baseline_file.write_text(json.dumps(baseline))
        self.retry()
        self.gate()  # Persist actual fixture metadata for CLI.
        event_file = self.root / 'event.json'
        event_file.write_text(json.dumps(self.event))
        env = dict(os.environ, **self.env, GITHUB_EVENT_PATH=str(event_file))
        gate_path = self.root / 'gate.json'
        gate = subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.runtime.runtime_images',
                               str(self.layout), '--gate', 'go1-26', '--requested',
                               '["go1-26","go1-26-dev"]', '--reports', str(self.reports),
                               '--dev-layout', str(self.dev), '--artifact-metadata',
                               str(self.root / 'artifacts.json'), '--job-metadata',
                               str(self.root / 'jobs.json'), '--gate-output', str(gate_path)],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        manifest = self.root / 'execution.json'
        record = subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.runtime.retry_lab',
                                 'record', '--gate', str(gate_path), '--artifacts',
                                 str(self.root / 'artifacts.json'), '--jobs',
                                 str(self.root / 'jobs.json'), '--baseline', str(baseline_file),
                                 '--output', str(manifest)], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(record.returncode, 0, record.stdout + record.stderr)
        result = subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.runtime.retry_lab',
                                 'barrier', '--manifest', str(manifest)], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        env['GITHUB_EVENT_NAME'] = 'pull_request'
        rejected = subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.runtime.retry_lab',
                                   'guard'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(rejected.returncode, 1)
        self.assertEqual(json.loads(rejected.stdout)['status'], 'INVALID_SCENARIO')


class LabWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / lab.WORKFLOW
        self.raw = self.path.read_text()
        self.workflow = yaml.safe_load(self.raw)
        self.steps = self.workflow['jobs']['lab-retry']['steps']

    def test_only_explicit_dispatch_and_existing_local_callers(self):
        events = self.workflow.get('on', self.workflow.get(True))
        self.assertEqual(set(events), {'workflow_dispatch'})
        self.assertEqual(set(events['workflow_dispatch']['inputs']), {'confirmation', 'reviewed-sha'})
        self.assertEqual(events['workflow_dispatch']['inputs']['confirmation']['default'], 'do-not-run')
        jobs = self.workflow['jobs']
        self.assertEqual(set(jobs), {'request', 'lab-build', 'lab-contract', 'lab-retry'})
        self.assertIn("github.event_name == 'workflow_dispatch'", jobs['request']['if'])
        self.assertIn('retry_lab guard', jobs['request']['steps'][1]['run'])
        self.assertEqual(jobs['lab-build']['uses'], './.github/workflows/validate-base-images.yml')
        self.assertEqual(json.loads(jobs['lab-build']['with']['frameworks']), ['go1-26', 'go1-26-dev'])
        self.assertEqual(jobs['lab-contract']['uses'], './.github/workflows/test-runtime-images.yml')
        self.assertEqual(jobs['lab-contract']['with'], {'framework': 'go1-26'})
        self.assertEqual(jobs['lab-build']['needs'], 'request')
        self.assertEqual(jobs['lab-contract']['needs'], 'lab-build')
        self.assertEqual(jobs['lab-retry']['needs'], ['lab-build', 'lab-contract'])

    def test_barrier_order_and_scoped_downloads(self):
        names = [s.get('name') for s in self.steps]
        self.assertLess(names.index('Execute the real production functional gate'), names.index(lab.RECORD))
        self.assertLess(names.index(lab.RECORD), names.index(lab.BASELINE_UPLOAD))
        self.assertLess(names.index(lab.BASELINE_UPLOAD), names.index(lab.BARRIER))
        for step in self.steps:
            if step.get('uses', '').startswith('actions/download-artifact@'):
                self.assertEqual(step['with']['run-id'], '${{ github.run_id }}')
                self.assertEqual(step['with']['repository'], '${{ github.repository }}')
                self.assertEqual(step['with']['digest-mismatch'], 'error')
        commands = '\n'.join(s.get('run', '') for s in self.steps)
        self.assertIn('runtime_images image.oci --gate go1-26', commands)
        self.assertIn('--dev-layout runtime-dev.oci', commands)
        self.assertIn('--paginate --slurp', commands)
        self.assertIn('jobs?filter=all&per_page=100', commands)

    def test_no_publication_privileges_or_new_credentials(self):
        self.assertEqual(self.workflow['permissions'], {'contents': 'read'})
        for job in self.workflow['jobs'].values():
            self.assertNotIn('secrets', job)
            self.assertTrue(set(job.get('permissions', {})) <= {'contents', 'actions'})
            self.assertTrue(all(level == 'read' for level in job.get('permissions', {}).values()))
        for prohibited in ('stable', 'promote-stable', 'recover-stable', 'build-base-images.yml',
                           'id-token', 'attestations:', 'secrets.', 'secrets: inherit',
                           'aws-actions/', 'cosign', 'docker build', 'apko build', 'melange build'):
            self.assertNotIn(prohibited, self.raw)
        for line in self.raw.splitlines():
            if 'token' in line.lower():
                self.assertIn('${{ github.token }}', line)

    def test_normal_workflows_do_not_enable_lab_or_failure_injection(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            if path == self.path:
                continue
            self.assertNotIn('retry_lab', path.read_text())
            self.assertNotIn('partial-retry-lab.yml', path.read_text())

    def test_lab_evidence_retention_and_immutable_baseline(self):
        uploads = [s for s in self.steps if s.get('uses', '').startswith('actions/upload-artifact@')]
        self.assertEqual(len(uploads), 2)
        for step in uploads:
            self.assertTrue(step['with']['name'].startswith('runtime-lab-p1-02-'))
            self.assertEqual(step['with']['retention-days'], 30)
            self.assertFalse(step['with']['overwrite'])
            self.assertEqual(step['with']['if-no-files-found'], 'error')
        self.assertEqual(uploads[0]['if'], "github.run_attempt == '1'")


if __name__ == '__main__':
    unittest.main()
