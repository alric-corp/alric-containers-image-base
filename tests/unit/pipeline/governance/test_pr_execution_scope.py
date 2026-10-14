"""Independent path/profile tests for PR validation selection."""

import itertools
import os
from pathlib import Path
import subprocess
import tempfile
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


class BaseResolverTests(unittest.TestCase):
    """The profile comes from the base revision's resolver, not the PR's."""

    RESOLVER = 'scripts/pipeline/governance/pr_execution_scope.py'

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.script = workflow()['jobs']['pr_execution_scope']['steps'][1]['run']
        self.git('init', '-q')
        self.write(self.RESOLVER, (ROOT / self.RESOLVER).read_text())
        self.write('docs/a.md', 'a\n')
        self.base = self.commit()

    def git(self, *args):
        environment = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                           GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid')
        return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', *args],
                              cwd=self.root, env=environment, check=True, capture_output=True,
                              text=True).stdout.strip()

    def write(self, path, text):
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'change')
        return self.git('rev-parse', 'HEAD')

    def profile(self, base, head):
        output = self.root / 'github-output'
        output.write_text('')
        environment = dict(os.environ, BASE_SHA=base, HEAD_SHA=head, CHANGED_PATHS=str(self.root / 'paths'),
                           RESOLVER=str(self.root / 'resolver.py'), GITHUB_OUTPUT=str(output))
        subprocess.run(bash_command('-c', self.script), cwd=self.root, env=environment, check=True,
                       capture_output=True, text=True, timeout=30)
        return dict(line.split('=', 1) for line in output.read_text().splitlines())['profile']

    def test_a_pr_cannot_lower_its_own_profile_by_editing_the_resolver(self):
        self.write(self.RESOLVER, "print('profile=NONE')\nprint('frameworks=null')\n")
        self.write('scripts/pipeline/runtime/readiness.py', '# changed\n')
        self.assertEqual(self.profile(self.base, self.commit()), 'FULL')

    def test_base_resolver_still_skips_documentation_only_prs(self):
        self.write('docs/a.md', 'b\n')
        self.assertEqual(self.profile(self.base, self.commit()), 'NONE')

    def test_missing_base_resolver_or_history_selects_full(self):
        self.git('rm', '-q', self.RESOLVER)
        without = self.commit()
        self.write('docs/a.md', 'c\n')
        self.assertEqual(self.profile(without, self.commit()), 'FULL')
        self.assertEqual(self.profile('0' * 40, self.base), 'FULL')


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
        # A soft-failing gate would report success with the validation red.
        self.assertNotIn('continue-on-error', self.job)
        self.assertNotIn('continue-on-error', self.job['steps'][0])

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
