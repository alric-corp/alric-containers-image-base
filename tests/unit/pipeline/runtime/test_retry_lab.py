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

    def publish_job(self, identifier, run_attempt, **overrides):
        """A 'Lab publish' GitHub job entry, as it appears in jobs?filter=all
        regardless of whether it ran, at any legitimate metadata state."""
        defaults = {'status': 'completed', 'conclusion': 'success',
                    'steps': [{'number': 1, 'name': 'Publish runtime image by digest',
                               'status': 'completed', 'conclusion': 'success',
                               'started_at': '2026-09-14T11:05:00Z',
                               'completed_at': '2026-09-14T11:06:00Z'}]}
        defaults.update(overrides)
        return self.job(identifier, lab.PUBLISHER, run_attempt=run_attempt, **defaults)

    def test_lab_publish_presence_in_any_state_never_changes_the_manifest_or_becomes_a_producer(self):
        # A-H: queued/in_progress/skipped/success/failure Lab publish metadata
        # is legitimate at attempt 1, but must never alter the manifest,
        # latest_producer_attempt, selected_attempt or reused, and must never
        # appear in the producers dict.
        baseline_manifest = self.assess()
        states = [
            {'status': 'queued', 'conclusion': None, 'steps': [],
             'started_at': None, 'completed_at': None},
            {'status': 'in_progress', 'conclusion': None, 'steps': [],
             'started_at': '2026-09-14T10:02:00Z', 'completed_at': None},
            {'status': 'completed', 'conclusion': 'skipped', 'steps': [],
             'started_at': None, 'completed_at': None},
            {'status': 'completed', 'conclusion': 'success'},
            {'status': 'completed', 'conclusion': 'failure', 'steps': [
                {'number': 1, 'name': 'Publish runtime image by digest', 'status': 'completed',
                 'conclusion': 'failure', 'started_at': '2026-09-14T11:05:00Z',
                 'completed_at': '2026-09-14T11:06:00Z'}]},
        ]
        for state in states:
            with self.subTest(state=state):
                self.jobs.append(self.publish_job(500, 1, **state))
                manifest = self.assess()
                self.jobs.pop()
                self.assertEqual(manifest, baseline_manifest)
                self.assertNotIn(lab.PUBLISHER, manifest['producers'])
        # K: attempt 1 controlled-barrier behavior is unaffected.
        code, result = lab.barrier(self.ctx, baseline_manifest)
        self.assertEqual(code, 42)
        self.assertEqual(result['status'], 'EXPECTED_LAB_FAILURE')

    def test_lab_publish_present_during_valid_reuse_does_not_change_producer_selection_or_reuse(self):
        # L: a valid attempt-2 reuse still resolves selected_attempt=1,
        # reused=true, with the real (copied) attempt-2 producer attempt,
        # whether or not Lab publish is present in the job inventory.
        baseline = self.retry()
        self.jobs.append(self.publish_job(501, 2, status='completed', conclusion='success'))
        manifest = self.assess(baseline)
        self.assertEqual(manifest['status'], 'REUSE_OBSERVED')
        self.assertTrue(manifest['gate']['reused'])
        self.assertEqual(manifest['gate']['selected_attempt'], 1)
        self.assertEqual(manifest['gate']['latest_producer_attempt'], 2)
        self.assertNotIn(lab.PUBLISHER, manifest['producers'])
        self.assertEqual(lab.barrier(self.ctx, manifest)[0], 0)

    def test_newer_producer_failure_still_invalidates_reuse_even_with_lab_publish_present(self):
        # I: Lab publish presence must never rescue a rebuild/newer-failure
        # scenario that the contract requires to invalidate reuse.
        baseline = self.retry()
        self.jobs.append(self.publish_job(502, 2, status='completed', conclusion='success'))
        runtime_job = next(j for j in self.jobs if j['run_attempt'] == 2
                           and j['name'].endswith('Runtime go1-26 (both architectures)'))
        runtime_job['conclusion'] = 'failure'
        self.assertFalse(self.gate()['passed'])
        with self.assertRaises(ValueError):
            self.assess(baseline)

    def test_unknown_lab_job_names_still_fail_closed(self):
        # J: the fix must not become a permissive wildcard; only the exact
        # known control/producer names are ever accepted.
        for bad_name in ('Lab unknown', 'Lab publisher', 'Lab publish unexpected',
                         'Random job', 'Build go1-26', 'Lab security bypass'):
            with self.subTest(name=bad_name):
                self.jobs.append(self.job(600, bad_name, status='completed',
                                          conclusion='skipped', steps=[]))
                with self.assertRaisesRegex(ValueError, 'unexpected job in laboratory run'):
                    self.assess()
                self.jobs.pop()


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
        self.assertEqual(set(jobs),
                         {'request', 'lab-build', 'lab-contract', 'lab-retry', 'lab-publish'})
        self.assertIn("github.event_name == 'workflow_dispatch'", jobs['request']['if'])
        self.assertIn('retry_lab guard', jobs['request']['steps'][1]['run'])
        self.assertEqual(jobs['lab-build']['uses'], './.github/workflows/validate-base-images.yml')
        self.assertEqual(json.loads(jobs['lab-build']['with']['frameworks']), ['go1-26', 'go1-26-dev'])
        self.assertEqual(jobs['lab-contract']['uses'], './.github/workflows/test-runtime-images.yml')
        self.assertEqual(jobs['lab-contract']['with'], {'framework': 'go1-26'})
        self.assertEqual(jobs['lab-build']['needs'], 'request')
        self.assertEqual(jobs['lab-contract']['needs'], 'lab-build')
        self.assertEqual(jobs['lab-retry']['needs'], ['lab-build', 'lab-contract'])
        # Publication continues only from lab-retry, and only once it is green;
        # there is no path that lets attempt 1 (or a failed attempt 2) publish.
        self.assertEqual(jobs['lab-publish']['needs'], 'lab-retry')
        self.assertEqual(jobs['lab-publish']['if'],
                         "github.run_attempt == '2' && needs.lab-retry.result == 'success'")

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

    def test_no_publication_privileges_outside_lab_publish(self):
        self.assertEqual(self.workflow['permissions'], {'contents': 'read'})
        jobs = self.workflow['jobs']
        for name, job in jobs.items():
            self.assertNotIn('secrets', job)
            if name == 'lab-publish':
                continue
            self.assertTrue(set(job.get('permissions', {})) <= {'contents', 'actions'})
            self.assertTrue(all(level == 'read' for level in job.get('permissions', {}).values()))
        # Evidence-only jobs never gain AWS/signing capability, regardless of lab-publish.
        evidence_only_text = '\n'.join(json.dumps(jobs[name]) for name in
                                       ('request', 'lab-build', 'lab-contract', 'lab-retry'))
        for prohibited in ('id-token', 'attestations', 'aws-actions/', 'cosign',
                           'configure-aws-credentials', 'amazon-ecr-login'):
            self.assertNotIn(prohibited, evidence_only_text)
        for line in self.raw.splitlines():
            if 'token' in line.lower() and 'id-token' not in line.lower():
                self.assertIn('${{ github.token }}', line)

    def test_lab_publish_grants_exactly_the_minimum_publication_permissions(self):
        permissions = self.workflow['jobs']['lab-publish']['permissions']
        self.assertEqual(permissions, {'contents': 'read', 'actions': 'read',
                                       'id-token': 'write', 'attestations': 'write',
                                       'artifact-metadata': 'write'})
        self.assertNotIn('secrets', self.workflow['jobs']['lab-publish'])

    def test_lab_publish_never_touches_stable_promotion_or_the_product_publisher(self):
        # SKOPEO_IMAGE legitimately names quay.io/skopeo/stable (the tool image,
        # already pinned/reviewed); strip it so the check targets Docker tag
        # "stable" and the promotion/recovery/product-signer surface instead.
        job = copy.deepcopy(self.workflow['jobs']['lab-publish'])
        job.get('env', {}).pop('SKOPEO_IMAGE', None)
        publish_text = json.dumps(job)
        for prohibited in ('promote-stable', 'recover-stable', 'imagetools create',
                           'verify_stable', 'build-base-images.yml', 'signing-identities',
                           'secrets.', 'secrets: inherit', ':stable"', "'stable'",
                           'CreateRepository', 'PutImageTagMutability',
                           'PutImageScanningConfiguration', 'TagResource',
                           'image-base-'):
            self.assertNotIn(prohibited, publish_text)
        self.assertNotIn('stable', publish_text.replace('skopeo/stable', ''))

    def test_lab_publish_never_accepts_workflow_dispatch_tag_or_destination_input(self):
        events = self.workflow.get('on', self.workflow.get(True))
        inputs = events['workflow_dispatch']['inputs']
        self.assertEqual(set(inputs), {'confirmation', 'reviewed-sha'})
        publish_text = json.dumps(self.workflow['jobs']['lab-publish'])
        for forbidden_input in ('inputs.tag', 'inputs.repository', 'inputs.destination',
                                'inputs.role', 'inputs.framework'):
            self.assertNotIn(forbidden_input, publish_text)

    def test_lab_publish_reads_no_hardcoded_aws_credentials(self):
        publish_text = json.dumps(self.workflow['jobs']['lab-publish'])
        for literal_credential in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'aws_session_token'):
            self.assertNotIn(literal_credential, publish_text)
        auth_step = next(s for s in self.workflow['jobs']['lab-publish']['steps']
                         if s.get('uses', '').startswith('aws-actions/configure-aws-credentials@'))
        self.assertEqual(auth_step['with']['role-to-assume'], '${{ vars.LAB_AWS_ROLE_ARN }}')
        self.assertEqual(auth_step['with']['aws-region'], '${{ vars.LAB_AWS_REGION }}')

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

    def test_publication_binding_is_validated_before_any_aws_auth(self):
        publish_steps = self.workflow['jobs']['lab-publish']['steps']
        names = [s.get('name') for s in publish_steps]
        bind_index = names.index('Validate same-run retry/reuse binding before any AWS auth')
        revalidate_index = names.index('Revalidate OCI layouts locally before push')
        layout_binding_index = names.index(
            'Validate revalidated OCI digests against the retry/reuse gate')
        auth_index = next(i for i, s in enumerate(publish_steps)
                          if s.get('uses', '').startswith('aws-actions/configure-aws-credentials@'))
        preflight_index = names.index('Preflight lab repository configuration (read-only)')
        publish_index = names.index('Publish runtime image by digest')
        self.assertLess(bind_index, auth_index)
        # F1: the gate<->verified-OCI digest binding must sit strictly between
        # local revalidation and AWS auth — not merely somewhere before auth.
        self.assertLess(revalidate_index, layout_binding_index)
        self.assertLess(layout_binding_index, auth_index)
        self.assertLess(auth_index, preflight_index)
        self.assertLess(preflight_index, publish_index)
        download_names = {s['name'] for s in publish_steps
                          if s.get('uses', '').startswith('actions/download-artifact@')}
        self.assertLess(max(names.index(n) for n in download_names), bind_index)

    def test_layout_binding_step_uses_the_revalidated_digests_and_the_bound_gate_fail_closed(self):
        publish_steps = self.workflow['jobs']['lab-publish']['steps']
        by_name = {s.get('name'): s for s in publish_steps}
        step = by_name['Validate revalidated OCI digests against the retry/reuse gate']
        # No continue-on-error/if on this step: a failure here must stop the
        # job before the next step (AWS auth) can run at all.
        self.assertNotIn('continue-on-error', step)
        self.assertNotIn('if', step)
        # Hardening: values from a previous step's outputs must flow through
        # env, never be interpolated with ${{ }} directly inside run:.
        self.assertEqual(step['env'], {
            'RUNTIME_DIGEST': '${{ steps.verified.outputs.runtime_digest }}',
            'DEV_DIGEST': '${{ steps.verified.outputs.dev_digest }}'})
        text = step['run']
        self.assertNotIn('${{', text)
        self.assertIn('retry_lab_publish verify-layout-binding', text)
        self.assertIn('--gate lab-publish/gate.json', text)
        self.assertIn('"$RUNTIME_DIGEST"', text)
        self.assertIn('"$DEV_DIGEST"', text)
        self.assertIn('set -eu', text)

    def test_finalize_step_consumes_the_layout_binding(self):
        finalize_step = next(s for s in self.workflow['jobs']['lab-publish']['steps']
                             if s.get('name') == 'Finalize publication result')
        self.assertIn('--layout-binding lab-publish/layout-binding.json', finalize_step['run'])

    def test_lab_publish_reuses_the_productive_publication_verifier_directly(self):
        publish_text = json.dumps(self.workflow['jobs']['lab-publish'])
        self.assertEqual(publish_text.count('scripts.pipeline.release.verify_publication'), 2)
        self.assertEqual(publish_text.count('scripts.pipeline.release.publish_sboms'), 2)
        self.assertNotIn('retry_lab_publish verify-publication', publish_text)

    def test_job_inventory_control_and_producer_names_match_the_workflow_graph(self):
        # Drift detector: if the workflow's job `name:` fields ever diverge
        # from retry_lab's control/producer constants, this fails loudly
        # instead of job_inventory silently rejecting a legitimate job again.
        jobs = self.workflow['jobs']
        self.assertEqual(jobs['request']['name'], 'Lab request')
        self.assertEqual(jobs['lab-retry']['name'], lab.CONSUMER)
        self.assertEqual(jobs['lab-publish']['name'], lab.PUBLISHER)
        self.assertEqual(lab.PRODUCER_PREFIXES,
                         tuple(f"{jobs[key]['name']} / " for key in ('lab-build', 'lab-contract')))

    def test_lab_publish_evidence_artifact_retention_and_no_overwrite(self):
        upload = next(s for s in self.workflow['jobs']['lab-publish']['steps']
                     if s.get('uses', '').startswith('actions/upload-artifact@'))
        self.assertEqual(upload['with']['name'],
                         'runtime-lab-p1-02-publication-${{ github.run_id }}-${{ github.run_attempt }}')
        self.assertEqual(upload['with']['retention-days'], 30)
        self.assertFalse(upload['with']['overwrite'])
        self.assertEqual(upload['with']['if-no-files-found'], 'error')


if __name__ == '__main__':
    unittest.main()
