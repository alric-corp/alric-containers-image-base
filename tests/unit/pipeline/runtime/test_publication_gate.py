"""Publication authorizes the tested runtime/build pair, including either target."""
import copy
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.pipeline.runtime import runtime_images as runtime
from tests.unit.pipeline.runtime import test_contract_evidence as fixtures


PAIR = ['go1-26', 'go1-26-dev']


class PublicationPlanTests(unittest.TestCase):
    def test_every_compiled_catalog_pair_resolves_one_contract_for_both_targets(self):
        compiled = [name for name in runtime.contracts() if runtime.supported(name) == 'compiled']
        self.assertTrue({'go1-25', 'go1-26', 'java21', 'java25', 'dotnet10'} <= set(compiled))
        for framework in compiled:
            dev = runtime.project(framework)[1]
            for target, role, counterpart in ((framework, 'runtime', dev), (dev, 'dev', framework)):
                with self.subTest(target=target):
                    result = runtime.publication_contract(target, [framework, dev])
                    self.assertIs(result['required'], True)
                    self.assertEqual(result['publication_framework'], target)
                    self.assertEqual(result['contract_framework'], framework)
                    self.assertEqual(result['runtime_framework'], framework)
                    self.assertEqual(result['dev_framework'], dev)
                    self.assertEqual(result['target_role'], role)
                    self.assertEqual(result['counterpart_framework'], counterpart)

    def test_incomplete_compiled_pairs_cannot_become_optional(self):
        for target in PAIR:
            with self.subTest(target=target), self.assertRaises(ValueError):
                runtime.publication_contract(target, [target])

    def test_target_outside_requested_batch_is_rejected(self):
        with self.assertRaises(ValueError):
            runtime.publication_contract('go1-26-dev', ['python3-13'])

    def test_interpreted_contract_resolves_directly_without_a_counterpart(self):
        result = runtime.publication_contract('python3-13', ['python3-13'])
        self.assertIs(result['required'], True)
        self.assertEqual(result['contract_framework'], 'python3-13')
        self.assertEqual(result['runtime_framework'], 'python3-13')
        self.assertEqual(result['target_role'], 'runtime')
        self.assertEqual(result['dev_framework'], '')
        self.assertEqual(result['counterpart_framework'], '')

    def test_functional_planning_still_produces_one_compiled_contract(self):
        planned, skipped = runtime.plan(PAIR)
        self.assertEqual(planned, ['go1-26'])
        self.assertIn('go1-26-dev', skipped)
        # Planning/reporting may still explain why an incomplete pair cannot run.
        self.assertEqual(runtime.plan(['go1-26'])[0], [])

    def test_cli_plan_exposes_dev_to_runtime_contract_mapping(self):
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'scripts.pipeline.runtime.runtime_images',
             '--publication-plan', 'go1-26-dev', '--requested', json.dumps(PAIR)],
            cwd=runtime.ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['contract_framework'], 'go1-26')
        self.assertEqual(plan['counterpart_framework'], 'go1-26')
        self.assertEqual(plan['target_role'], 'dev')

    def test_cli_rejects_planning_and_publication_gate_together(self):
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'scripts.pipeline.runtime.runtime_images',
             '--publication-plan', 'go1-26-dev', '--publication-gate', 'go1-26-dev',
             '--requested', json.dumps(PAIR)],
            cwd=runtime.ROOT, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('not allowed with argument', result.stderr)

    def test_cli_requires_explicit_true_even_if_a_gate_regresses_to_not_required(self):
        argv = ['runtime_images', '--publication-gate', 'go1-26-dev',
                '--requested', json.dumps(PAIR)]
        for result in ({'passed': None, 'status': 'not_required'}, {'passed': 'true'}):
            with self.subTest(result=result), patch.object(sys, 'argv', argv), \
                    patch.object(sys, 'stdout', new_callable=io.StringIO), \
                    patch.object(runtime, 'publication_gate', return_value=result):
                self.assertNotEqual(runtime.main(), 0)


class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing fixture helpers without inheriting its test suite.
        self.fixture = fixtures.ContractEvidenceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.framework = 'go1-26'

    def add_pair(self, attempt=1):
        return self.fixture.add(attempt, dev_expected=self.fixture.dev_expected)

    def call(self, target, runtime_layout=None, dev_layout=None, requested=None, **overrides):
        fixture = self.fixture
        runtime_layout = runtime_layout or fixture.layout
        dev_layout = dev_layout or fixture.dev_layout
        artifacts, jobs = fixture.metadata()
        is_dev = target.endswith('-dev')
        options = dict(layout=dev_layout if is_dev else runtime_layout,
                       counterpart_layout=runtime_layout if is_dev else dev_layout,
                       artifact_metadata=artifacts, job_metadata=jobs,
                       run_id='41', attempt=str(fixture.attempt),
                       repository=fixtures.REPOSITORY, revision=fixtures.REVISION)
        options.update(overrides)
        return runtime.publication_gate(fixture.reports, target,
                                        PAIR if requested is None else requested, **options)

    def assert_pair_blocked(self, fragment=None, **overrides):
        for target in PAIR:
            with self.subTest(target=target):
                result = self.call(target, **overrides)
                self.assertIs(result['passed'], False, result)
                self.assertNotEqual(result.get('status'), 'not_required', result)
                if fragment:
                    self.assertIn(fragment, result['error'])

    def cli(self, target, mode='--publication-gate', requested=None):
        fixture = self.fixture
        artifacts, jobs = fixture.metadata()
        output = fixture.root / 'runtime-gate-result.json'
        is_dev = target.endswith('-dev')
        args = [sys.executable, '-B', '-m', 'scripts.pipeline.runtime.runtime_images',
                str(fixture.dev_layout if is_dev else fixture.layout), mode, target,
                '--reports', str(fixture.reports),
                '--requested', json.dumps(PAIR if requested is None else requested),
                '--run-id', '41', '--run-attempt', str(fixture.attempt),
                '--repository', fixtures.REPOSITORY, '--revision', fixtures.REVISION,
                '--artifact-metadata', str(artifacts), '--job-metadata', str(jobs),
                '--gate-output', str(output)]
        if mode == '--publication-gate':
            args += ['--counterpart-layout', str(fixture.layout if is_dev else fixture.dev_layout)]
        result = subprocess.run(args, cwd=runtime.ROOT, capture_output=True, text=True, timeout=15)
        return result, json.loads(output.read_text())

    def test_both_targets_select_the_same_successful_pair_evidence(self):
        self.add_pair()
        for target in PAIR:
            with self.subTest(target=target):
                result = self.call(target)
                self.assertIs(result['passed'], True, result)
                self.assertEqual(result['publication_framework'], target)
                self.assertEqual(result['contract_framework'], 'go1-26')
                self.assertEqual(result['runtime_framework'], 'go1-26')
                self.assertEqual(result['dev_framework'], 'go1-26-dev')
                self.assertEqual(result['selected_artifact'], 'runtime-go1-26-1')
                self.assertEqual(result['selected_artifact_id'], 101)
                self.assertEqual(result['selected_attempt'], 1)
                self.assertEqual(result['index_digest'], self.fixture.expected['digest'])
                self.assertEqual(result['platforms'], self.fixture.expected['platforms'])
                self.assertEqual(result['dev_index_digest'], self.fixture.dev_expected['digest'])
                self.assertEqual(result['dev_platforms'], self.fixture.dev_expected['platforms'])

    def test_missing_functional_evidence_blocks_both_targets(self):
        self.fixture.job(1)
        self.assert_pair_blocked('missing functional contract artifact')

    def test_exact_dev_missing_evidence_cli_regression_is_nonzero(self):
        self.fixture.job(1)
        # Generic reporting retains its gradual-coverage behavior. It is not the
        # publication command and cannot substitute for pair authorization.
        generic, optional = self.cli('go1-26-dev', mode='--gate')
        self.assertEqual(generic.returncode, 0, generic.stdout + generic.stderr)
        self.assertIsNone(optional['passed'])
        self.assertEqual(optional['status'], 'not_required')
        result, evidence = self.cli('go1-26-dev')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIs(evidence['passed'], False)
        self.assertEqual(evidence['publication_framework'], 'go1-26-dev')
        self.assertEqual(evidence['contract_framework'], 'go1-26')
        self.assertIn('missing functional contract artifact', evidence['error'])

    def test_dev_cli_records_exact_canonical_pair_on_success(self):
        self.add_pair()
        result, evidence = self.cli('go1-26-dev')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIs(evidence['passed'], True)
        self.assertEqual(evidence['contract_framework'], 'go1-26')
        self.assertEqual(evidence['index_digest'], self.fixture.expected['digest'])
        self.assertEqual(evidence['dev_index_digest'], self.fixture.dev_expected['digest'])

    def test_failed_pair_producer_blocks_both_targets(self):
        self.add_pair()
        self.fixture.jobs[0]['conclusion'] = 'failure'
        self.assert_pair_blocked('latest functional producer did not succeed')

    def test_latest_failed_producer_cannot_fall_back_to_an_older_pair_pass(self):
        self.add_pair()
        self.fixture.attempt = 2
        self.fixture.job(2, 'failure')
        self.assert_pair_blocked('latest functional producer did not succeed')

    def test_latest_failed_pair_report_cannot_fall_back_to_an_older_pass(self):
        self.add_pair()
        directory = self.add_pair(2)
        self.fixture.attempt = 2
        path = self.fixture.report(directory)
        report = json.loads(path.read_text())
        path.write_text(json.dumps(dict(report, status='failed')))
        self.assert_pair_blocked('no fallback to an older PASS')

    def test_changed_runtime_candidate_blocks_both_targets(self):
        self.add_pair()
        other = self.fixture.root / 'runtime-b.oci'
        fixtures.layout_fixture(other, 'runtime-b')
        self.assert_pair_blocked('no functional evidence matches', runtime_layout=other)

    def test_changed_dev_candidate_blocks_both_targets(self):
        self.add_pair()
        other = self.fixture.root / 'dev-b.oci'
        fixtures.layout_fixture(other, 'dev-b')
        self.assert_pair_blocked('no functional evidence matches', dev_layout=other)

    def test_each_runtime_and_dev_platform_digest_is_required(self):
        directory = self.add_pair()
        for arch in ('amd64', 'arm64'):
            path = self.fixture.report(directory, arch)
            original = json.loads(path.read_text())
            for field, error in (('manifest_digest', 'functional manifest'),
                                 ('dev_manifest_digest', 'functional build manifest')):
                with self.subTest(arch=arch, field=field):
                    path.write_text(json.dumps(dict(original, **{field: 'sha256:' + 'b' * 64})))
                    self.assert_pair_blocked(error)
                    path.write_text(json.dumps(original))

    def test_one_byte_tampering_in_either_current_layout_blocks_both_targets(self):
        self.add_pair()
        for layout, expected in ((self.fixture.layout, self.fixture.expected),
                                 (self.fixture.dev_layout, self.fixture.dev_expected)):
            with self.subTest(layout=layout.name):
                blob = layout / 'blobs/sha256' / expected['digest'][7:]
                original = blob.read_bytes()
                blob.write_bytes(original + b' ')
                self.assert_pair_blocked('blob OCI alterado')
                blob.write_bytes(original)

    def test_incomplete_requested_pair_blocks_even_with_valid_pair_evidence(self):
        self.add_pair()
        for target in PAIR:
            with self.subTest(target=target):
                result = self.call(target, requested=[target])
                self.assertIs(result['passed'], False, result)
                self.assertNotEqual(result.get('status'), 'not_required')

    def test_missing_current_counterpart_blocks_both_targets(self):
        self.add_pair()
        self.assert_pair_blocked(counterpart_layout=None)

    def test_wrong_report_run_revision_or_build_framework_blocks_both_targets(self):
        directory = self.add_pair()
        path = self.fixture.report(directory)
        original = json.loads(path.read_text())
        for field, value in (('run_id', '42'), ('revision', 'b' * 40),
                             ('dev_framework', 'go1-25-dev')):
            with self.subTest(field=field):
                path.write_text(json.dumps(dict(original, **{field: value})))
                self.assert_pair_blocked()
                path.write_text(json.dumps(original))

    def test_wrong_artifact_run_or_revision_blocks_both_targets(self):
        self.add_pair()
        artifact = self.fixture.artifacts[0]
        original = dict(artifact['workflow_run'])
        for field, value in (('id', 42), ('head_sha', 'b' * 40)):
            with self.subTest(field=field):
                artifact['workflow_run'] = dict(original, **{field: value})
                self.assert_pair_blocked()
        artifact['workflow_run'] = original

    def test_wrong_producer_run_or_revision_blocks_both_targets(self):
        self.add_pair()
        original = copy.deepcopy(self.fixture.jobs)
        for field, value in (('run_id', 42), ('head_sha', 'b' * 40)):
            with self.subTest(field=field):
                self.fixture.jobs = [dict(original[0], **{field: value})]
                self.assert_pair_blocked()

    def test_duplicate_artifact_identity_blocks_both_targets(self):
        self.add_pair()
        self.fixture.artifacts.append(dict(self.fixture.artifacts[0], id=999))
        self.assert_pair_blocked('duplicate/conflicting artifacts')

    def test_ambiguous_or_missing_producer_blocks_both_targets(self):
        self.add_pair()
        original = copy.deepcopy(self.fixture.jobs)
        for jobs in ([], original + [dict(original[0], id=900)]):
            with self.subTest(jobs=jobs):
                self.fixture.jobs = jobs
                self.assert_pair_blocked()

    def test_truncated_artifact_or_job_inventory_blocks_both_targets(self):
        self.add_pair()
        for key, values, flag in (('artifacts', self.fixture.artifacts, 'artifact_metadata'),
                                  ('jobs', self.fixture.jobs, 'job_metadata')):
            with self.subTest(key=key):
                path = self.fixture.root / f'truncated-{key}.json'
                path.write_text(json.dumps([{'total_count': 2, key: values}]))
                self.assert_pair_blocked(f'incomplete or duplicate {key}', **{flag: path})

    def test_failed_download_blocks_both_targets_despite_local_reports(self):
        self.add_pair()
        self.assert_pair_blocked('download failed', download_result='failure')

    def test_previous_attempt_reuse_requires_the_exact_current_pair_without_rebuild(self):
        self.add_pair()
        self.fixture.attempt = 2
        self.fixture.job(2)
        before = {str(path): path.read_bytes() for layout in
                  (self.fixture.layout, self.fixture.dev_layout)
                  for path in layout.rglob('*') if path.is_file()}
        with patch.object(runtime, 'command') as command, \
                patch.object(runtime, 'run_platform') as execute:
            for target in PAIR:
                with self.subTest(target=target):
                    result = self.call(target)
                    self.assertIs(result['passed'], True, result)
                    self.assertEqual(result['selected_attempt'], 1)
                    self.assertEqual(result['latest_producer_attempt'], 2)
                    self.assertTrue(result['reused'])
        command.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(before, {str(path): path.read_bytes() for layout in
                                 (self.fixture.layout, self.fixture.dev_layout)
                                 for path in layout.rglob('*') if path.is_file()})
        other = self.fixture.root / 'dev-b.oci'
        fixtures.layout_fixture(other, 'dev-b')
        self.assert_pair_blocked('no functional evidence matches', dev_layout=other)

    def test_latest_compatible_evidence_is_selected_for_both_targets(self):
        self.add_pair()
        self.add_pair(2)
        self.fixture.attempt = 2
        for target in PAIR:
            with self.subTest(target=target):
                result = self.call(target)
                self.assertIs(result['passed'], True, result)
                self.assertEqual(result['selected_attempt'], 2)
                self.assertFalse(result['reused'])

    def test_other_framework_failure_does_not_block_a_valid_pair(self):
        self.add_pair()
        self.fixture.job(1, 'failure', 'python3-13')
        for target in PAIR:
            with self.subTest(target=target):
                self.assertIs(self.call(target)['passed'], True)

    def test_interpreted_evidence_still_authorizes_without_counterpart_layout(self):
        self.fixture.framework = 'python3-13'
        self.fixture.add(1)
        result = self.call('python3-13', requested=['python3-13'], counterpart_layout=None)
        self.assertIs(result['passed'], True, result)
        self.assertEqual(result['contract_framework'], 'python3-13')
        self.assertEqual(result['index_digest'], self.fixture.expected['digest'])
        self.assertEqual(result['dev_framework'], '')
        self.assertIsNone(result['dev_index_digest'])


if __name__ == '__main__':
    unittest.main()
