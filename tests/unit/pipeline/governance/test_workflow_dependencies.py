from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

from tests.helpers.subprocess_env import python3_test_environment
from scripts.pipeline.governance import workflow_dependencies as dependency

ROOT = dependency.ROOT
ALTERNATIVE = 'fixture-platform/factory-executors'


class DependencyTests(unittest.TestCase):
    """Real YAML/CLI; synthetic repositories never access a network.

    This only exercises the LOCAL half of the contract: this repository's own
    callers and their expected input bindings, its pinned SHA, its own action
    pins and its Dependabot grouping.
    The shared library's own implementation, inputs/outputs, hardening,
    actionlint and retention are covered by alric-containers-reusable-workflows'
    own test suite (tests/test_contracts.py there), not duplicated here.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shared-origin-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'caller'
        self.local = self.root / '.github/workflows'
        self.local.mkdir(parents=True)
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            shutil.copyfile(path, self.local / path.name)
        shutil.copyfile(ROOT / '.github/dependabot.yml', self.root / '.github/dependabot.yml')
        caller = self.read('validate-base-images.yml')['jobs']['validate']['uses']
        self.repository, self.sha = caller.split('/.github/workflows/')[0], caller.rsplit('@', 1)[1]
        self.policy = self.root / 'policies/governance/reusable-workflows.json'
        self.write_policy(self.repository)

    def write_policy(self, repository):
        self.policy.parent.mkdir(parents=True, exist_ok=True)
        self.policy.write_text(json.dumps({'schema_version': 1, 'repository': repository}))

    def read(self, name):
        return yaml.safe_load((self.local / name).read_text())

    def write(self, name, document):
        (self.local / name).write_text(yaml.safe_dump(document, sort_keys=False))

    def replace_local(self, old, new):
        for path in self.local.glob('*.yml'):
            path.write_text(path.read_text().replace(old, new))
        path = self.root / '.github/dependabot.yml'
        path.write_text(path.read_text().replace(old, new))

    def migrate(self, repository):
        self.replace_local(self.repository, repository)
        self.write_policy(repository)
        self.repository = repository

    def call(self, extra_env=None):
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        with python3_test_environment(env) as shimmed_env:
            return subprocess.run(
                ['python3', '-B', '-m', 'scripts.pipeline.governance.workflow_dependencies',
                 '--root', str(self.root)], cwd=ROOT, env=shimmed_env,
                capture_output=True, text=True)

    def rejected(self):
        result = self.call()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, '', 'Failure must not print a successful result')
        return result

    def change_caller(self, name='test-runtime-images.yml', job='runtime', **changes):
        document = self.read(name)
        document['jobs'][job].update(changes)
        self.write(name, document)

    def change_tool(self, name='promote-stable.yml', job='promote', transform=lambda step: None):
        document = self.read(name)
        matches = [step for step in document['jobs'][job]['steps']
                   if step.get('name') == 'Install Trivy']
        self.assertEqual(len(matches), 1)
        transform(matches[0])
        self.write(name, document)

    def test_clean_fixture_passes_and_reports_two_dependencies(self):
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(dependency.dependencies(self.root)), 2)

    def test_alternative_origin_migration_is_coherent_through_real_cli(self):
        self.migrate(ALTERNATIVE)
        self.assertEqual(dependency.approved_repository(self.root), ALTERNATIVE)
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(all(entry['repository'] == ALTERNATIVE
                            for entry in dependency.dependencies(self.root)))

    def test_missing_or_invalid_approved_origin_fails_before_cli_output(self):
        self.policy.unlink()
        self.rejected()
        for document in ('{', '[]', '{}', '{"schema_version": 2, "repository": "a/b"}',
                         '{"schema_version": 1, "repository": "a/b", "extra": true}',
                         '{"schema_version": 1, "repository": "a/b", "repository": "c/d"}'):
            with self.subTest(document=document):
                self.policy.write_text(document)
                with self.assertRaises(ValueError):
                    dependency.approved_repository(self.root)
                self.rejected()

    def test_unsafe_origin_values_are_rejected_without_output(self):
        for value in ('', 'repo-only', 'owner/repo/extra', '../repo', 'owner/..',
                      'owner/*', 'owner/repo@main', 'owner/repo?x',
                      'https://github.com/owner/repo', 'owner/repo\ninjected=value',
                      'owner/$(touch x)', 'owner/${{ vars.REPO }}', None, 123):
            with self.subTest(value=value):
                self.write_policy(value)
                with self.assertRaises(ValueError):
                    dependency.approved_repository(self.root)
                self.rejected()

    def test_mixed_caller_origin_reproduced_false_pass_is_now_rejected(self):
        uses = self.read('test-runtime-images.yml')['jobs']['runtime']['uses']
        self.change_caller(uses=uses.replace(self.repository, ALTERNATIVE))
        with self.assertRaises(ValueError):
            dependency.dependencies(self.root)
        self.rejected()

    def test_declaring_new_origin_does_not_implicitly_migrate_callers(self):
        self.write_policy(ALTERNATIVE)
        self.rejected()

    def test_migrated_origin_rejects_one_caller_left_at_old_origin(self):
        previous_origin = self.repository
        self.migrate(ALTERNATIVE)
        uses = self.read('test-runtime-images.yml')['jobs']['runtime']['uses']
        self.change_caller(uses=uses.replace(ALTERNATIVE, previous_origin))
        result = self.rejected()
        self.assertIn('test-runtime-images.yml/runtime', result.stderr)

    def test_missing_required_caller_job_is_not_reduced_coverage(self):
        for name, job in (('validate-base-images.yml', 'validate'), ('test-runtime-images.yml', 'runtime')):
            original = self.read(name)
            altered = self.read(name)
            del altered['jobs'][job]
            with self.subTest(name=name):
                self.write(name, altered)
                self.rejected()
            self.write(name, original)

    def test_missing_required_caller_file_is_rejected(self):
        (self.local / 'test-runtime-images.yml').unlink()
        self.rejected()

    def test_invalid_or_wrong_caller_reference_is_rejected(self):
        suffix = '/.github/workflows/test-runtime-images.yml@'
        for value in ('main', 'v1', 'a' * 39, 'a' * 41, 'g' * 40,
                      'a' * 40 + '/../../bad', '${{ vars.SHA }}'):
            with self.subTest(ref=value):
                self.change_caller(uses=self.repository + suffix + value)
                self.rejected()
        for uses in (self.repository + '/.github/workflows/other.yml@' + self.sha,
                     './.github/workflows/test-runtime-images.yml', None, 23):
            with self.subTest(uses=uses):
                self.change_caller(uses=uses)
                self.rejected()

    def test_mixed_shared_workflow_releases_are_rejected(self):
        uses = self.read('test-runtime-images.yml')['jobs']['runtime']['uses']
        self.change_caller(uses=uses.replace(self.sha, 'a' * 40))
        self.rejected()

    def test_missing_or_malformed_caller_inputs_mapping_is_rejected(self):
        for name, job in (('validate-base-images.yml', 'validate'),
                          ('test-runtime-images.yml', 'runtime')):
            original = self.read(name)
            altered = self.read(name)
            del altered['jobs'][job]['with']
            self.write(name, altered)
            with self.subTest(name=name, supplied='missing'):
                result = self.rejected()
                self.assertIn(f'{name}/{job}', result.stderr)
            for supplied in (None, [], '', {}, {1: 'invalid-key'}):
                with self.subTest(name=name, supplied=supplied):
                    self.change_caller(name, job, **{'with': supplied})
                    self.rejected()
            self.write(name, original)

    def test_each_required_caller_input_is_enforced(self):
        for name, job in (('validate-base-images.yml', 'validate'),
                          ('test-runtime-images.yml', 'runtime')):
            original = self.read(name)
            inputs = original['jobs'][job]['with']
            for missing in inputs:
                with self.subTest(name=name, missing=missing):
                    supplied = {key: value for key, value in inputs.items() if key != missing}
                    self.change_caller(name, job, **{'with': supplied})
                    result = self.rejected()
                    self.assertIn(f'missing=[{missing!r}]', result.stderr)
            self.write(name, original)

    def test_unknown_and_free_command_caller_inputs_are_rejected(self):
        for name, job in (('validate-base-images.yml', 'validate'),
                          ('test-runtime-images.yml', 'runtime')):
            original = self.read(name)
            for extra in ('unexpected-input', 'test-command'):
                with self.subTest(name=name, extra=extra):
                    supplied = dict(original['jobs'][job]['with'], **{extra: 'true'})
                    self.change_caller(name, job, **{'with': supplied})
                    result = self.rejected()
                    self.assertIn(f'unknown=[{extra!r}]', result.stderr)
            self.write(name, original)

    def test_locked_build_requires_literal_boolean_true(self):
        name, job = 'validate-base-images.yml', 'validate'
        inputs = self.read(name)['jobs'][job]['with']
        for value in (False, 'true', 'false', 1, 0, None, '${{ inputs.locked-build }}'):
            with self.subTest(value=value):
                self.change_caller(name, job, **{'with': dict(inputs, **{'locked-build': value})})
                result = self.rejected()
                self.assertIn('locked-build must retain its reviewed input binding and bool type',
                              result.stderr)

    def test_caller_forwarding_and_config_bindings_cannot_change(self):
        cases = (
            ('validate-base-images.yml', 'validate', 'frameworks', '[]'),
            ('validate-base-images.yml', 'validate', 'frameworks', []),
            ('validate-base-images.yml', 'validate', 'melange-config', 'other.yaml'),
            ('validate-base-images.yml', 'validate', 'melange-config', False),
            ('test-runtime-images.yml', 'runtime', 'framework', 'go1-26'),
            ('test-runtime-images.yml', 'runtime', 'framework', ['go1-26']),
            ('test-runtime-images.yml', 'runtime', 'artifact-run-id', '123'),
            ('test-runtime-images.yml', 'runtime', 'artifact-run-id', 123),
        )
        for name, job, field, value in cases:
            original = self.read(name)
            supplied = dict(original['jobs'][job]['with'], **{field: value})
            with self.subTest(name=name, field=field, value=value):
                self.change_caller(name, job, **{'with': supplied})
                result = self.rejected()
                self.assertIn(f'{field} must retain its reviewed input binding and str type',
                              result.stderr)
            self.write(name, original)

    def test_mixed_tool_origin_reproduced_false_pass_is_now_rejected(self):
        self.change_tool(transform=lambda step: step.update(uses=step['uses'].replace(self.repository, ALTERNATIVE)))
        with self.assertRaises(ValueError):
            dependency.tooling_consistency(dependency.local_workflows(self.root), root=self.root)
        self.rejected()

    def test_migrated_origin_rejects_one_action_left_at_old_origin(self):
        previous_origin = self.repository
        self.migrate(ALTERNATIVE)
        self.change_tool(transform=lambda step: step.update(
            uses=step['uses'].replace(ALTERNATIVE, previous_origin)))
        result = self.rejected()
        self.assertIn('promote-stable.yml/promote/Install Trivy', result.stderr)

    def test_missing_required_tool_step_is_rejected(self):
        document = self.read('recover-stable.yml')
        document['jobs']['recover']['steps'] = [step for step in document['jobs']['recover']['steps']
                                               if step.get('name') != 'Install Trivy']
        self.write('recover-stable.yml', document)
        self.rejected()

    def test_missing_tool_reference_or_run_replacement_is_rejected(self):
        def replace(step):
            step.pop('uses')
            step['run'] = 'echo unavailable'
        self.change_tool(transform=replace)
        self.rejected()

    def test_duplicate_required_tool_step_is_rejected(self):
        document = self.read('promote-stable.yml')
        step = next(step for step in document['jobs']['promote']['steps'] if step.get('name') == 'Install Trivy')
        document['jobs']['promote']['steps'].append(dict(step))
        self.write('promote-stable.yml', document)
        self.rejected()

    def test_tool_pin_must_be_full_sha_and_consistent(self):
        prefix = self.repository + '/actions/setup-trivy@'
        for ref in ('main', 'v1', 'a' * 39, 'z' * 40, 'a' * 40):
            with self.subTest(ref=ref):
                self.change_tool(transform=lambda step: step.update(uses=prefix + ref))
                self.rejected()

    def test_dependabot_group_origin_must_match_approval(self):
        path = self.root / '.github/dependabot.yml'
        path.write_text(path.read_text().replace(self.repository + '*', ALTERNATIVE + '*'))
        self.rejected()

    def test_additional_uninventoried_shared_dependency_is_rejected(self):
        document = self.read('test-runtime-images.yml')
        document['jobs']['extra'] = {'uses': self.repository + '/.github/workflows/extra.yml@' + self.sha}
        self.write('test-runtime-images.yml', document)
        self.rejected()

    def test_legitimate_third_party_reusable_and_action_are_preserved(self):
        document = self.read('test-runtime-images.yml')
        document['jobs']['third-party'] = {'uses': 'fixture-third-party/ci/.github/workflows/lint.yml@' + 'b' * 40}
        self.write('test-runtime-images.yml', document)
        document = self.read('promote-stable.yml')
        document['jobs']['promote']['steps'].append({'uses': 'fixture-third-party/action@' + 'c' * 40})
        self.write('promote-stable.yml', document)
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(dependency.dependencies(self.root)), 2)

    def test_malformed_or_wrong_shape_local_yaml_is_rejected(self):
        path = self.local / 'test-runtime-images.yml'
        for text in ('jobs: [', '- list\n', 'jobs: null\n', 'jobs: []\n',
                     'jobs: {}\njobs: {}\n'):
            with self.subTest(text=text):
                path.write_text(text)
                self.rejected()


class ProductIdentityTests(unittest.TestCase):
    def test_signing_identity_stays_in_the_product(self):
        document = yaml.safe_load((ROOT / '.github/workflows/build-base-images.yml').read_text())
        publisher = document['jobs']['build-push']
        self.assertNotIn('uses', publisher)
        steps = publisher['steps']
        self.assertTrue(any('cosign sign' in step.get('run', '') for step in steps))
        self.assertTrue(any(step.get('uses', '').startswith('actions/attest-build-provenance@')
                            for step in steps))


if __name__ == '__main__':
    unittest.main()
