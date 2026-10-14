"""Independent path/profile tests for PR validation selection."""

import itertools
from pathlib import Path
import subprocess
import unittest

import yaml

from scripts.pipeline.governance import pr_execution_scope as scope
from scripts.pipeline.governance.pr_execution_scope import profile_for_paths
from tests.helpers.subprocess_env import bash_command

ROOT = Path(__file__).resolve().parents[4]


def workflow():
    return yaml.safe_load((ROOT / '.github/workflows/workflow.yml').read_text())


class PRExecutionScopeTests(unittest.TestCase):
    def assert_profile(self, expected, *paths):
        self.assertEqual(profile_for_paths(paths), expected)

    def test_go_specific_framework_change_uses_p0_04(self):
        self.assert_profile('P0_04', 'frameworks/go1-26.yaml')
        self.assert_profile('P0_04', 'frameworks/go1-26-dev.yaml',
                            'tests/runtime/projects/go/main.go')

    def test_docs_next_to_p0_04_paths_remain_p0_04(self):
        self.assert_profile('P0_04', 'frameworks/go1-26.yaml', 'docs/repository-architecture.md',
                            'docs/corporate-production-readiness.md')

    def test_changes_outside_the_image_pipeline_need_no_image_validation(self):
        # Before the PR trigger lost its path filter these PRs never started
        # workflow.yml; NONE keeps that cost while the gate still reports.
        for paths in (('docs/repository-architecture.md',), ('README.md', 'CONTRIBUTING.md'),
                      ('tests/unit/pipeline/release/test_lifecycle.py',), ('infra/ecr/main.tf',),
                      ('.github/workflows/promote-stable.yml',), ('unknown/path',)):
            with self.subTest(paths=paths):
                self.assert_profile('NONE', *paths)

    def test_shared_workflow_and_pipeline_changes_use_full(self):
        self.assert_profile('FULL', '.github/workflows/build-base-images.yml')
        self.assert_profile('FULL', 'policies/governance/reusable-workflows.json')
        self.assert_profile('FULL', 'scripts/pipeline/runtime/runtime_images.py')

    def test_shared_composition_ca_scanner_and_trust_use_full(self):
        self.assert_profile('FULL', 'distroless/image-base.yaml')
        self.assert_profile('FULL', 'melange/image-base-ca-certificates.yaml')
        self.assert_profile('FULL', 'scripts/pipeline/artifacts/scan_images.py')
        self.assert_profile('FULL', 'scripts/pipeline/governance/wolfi_trust.py')

    def test_non_p0_framework_and_ambiguous_paths_fail_safe_to_full(self):
        for path in ('frameworks/java21.yaml', 'frameworks/nodejs22.yaml',
                     'frameworks/python3-13.yaml', 'frameworks/dotnet10.yaml',
                     'frameworks/go1-25.yaml', 'frameworks/go1-25-dev.yaml',
                     'Makefile'):
            with self.subTest(path=path):
                self.assert_profile('FULL', path)
        self.assert_profile('FULL', 'frameworks/go1-26.yaml', 'unknown/path')

    def test_missing_history_or_empty_diff_never_skips_validation(self):
        self.assert_profile('FULL')
        self.assert_profile('FULL', scope.UNKNOWN_PATH)
        self.assert_profile('FULL', 'docs/x.md', scope.UNKNOWN_PATH)

    def test_moving_a_product_file_out_of_the_pipeline_still_validates(self):
        # workflow.yml diffs with --no-renames, so both sides of a move appear.
        self.assert_profile('FULL', 'scripts/pipeline/runtime/readiness.py', 'docs/readiness.py')
        step = workflow()['jobs']['pr_execution_scope']['steps'][1]['run']
        self.assertIn('git diff --no-renames --name-only', step)
        self.assertIn(scope.UNKNOWN_PATH, step)

    def test_factory_allow_list_equals_the_push_trigger(self):
        events = workflow().get('on', workflow().get(True))
        expected = set(events['push']['paths'])
        actual = {prefix + '**' for prefix in scope.FACTORY_PREFIXES} | set(scope.FACTORY_FILES)
        self.assertEqual(actual, expected)
        self.assertEqual(events['pull_request'], {})


class PRValidationGateTests(unittest.TestCase):
    RESULTS = ('success', 'failure', 'cancelled', 'skipped')

    @classmethod
    def setUpClass(cls):
        cls.job = workflow()['jobs']['validation-gate']
        cls.script = cls.job['steps'][0]['run']

    def gate(self, scope_result, profile, p0_04, full):
        environment = {'SCOPE': scope_result, 'PROFILE': profile, 'P0_04': p0_04, 'FULL': full,
                       'PATH': '/usr/bin:/bin'}
        return subprocess.run(bash_command('-c', self.script), env=environment,
                              capture_output=True, text=True, timeout=10).returncode

    def test_gate_reports_on_every_pull_request_without_running_pr_code(self):
        self.assertEqual(self.job['name'], 'Factory PR validation gate')
        self.assertEqual(self.job['if'], "always() && github.event_name == 'pull_request'")
        self.assertEqual(self.job['needs'], ['pr_execution_scope', 'validate-pr', 'validate-pr-full'])
        self.assertNotIn('permissions', self.job)
        self.assertEqual(len(self.job['steps']), 1)
        self.assertNotIn('uses', self.job['steps'][0])

    def test_gate_passes_only_when_the_selected_validation_succeeded(self):
        allowed = {('success', 'NONE', 'skipped', 'skipped'),
                   ('success', 'P0_04', 'success', 'skipped'),
                   ('success', 'FULL', 'skipped', 'success')}
        for combination in itertools.product(self.RESULTS, ('NONE', 'P0_04', 'FULL', '', 'BOGUS'),
                                             self.RESULTS, self.RESULTS):
            with self.subTest(combination=combination):
                self.assertEqual(self.gate(*combination) == 0, combination in allowed)


if __name__ == '__main__':
    unittest.main()
