from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts.pipeline.governance import workflow_dependencies as dependency

ROOT = dependency.ROOT
WORKFLOWS = ('validate-apko-images.yml', 'test-runtime-images.yml')
ALTERNATIVE = 'fixture-platform/factory-executors'


class DependencyTests(unittest.TestCase):
    """Real YAML/commits/CLI; synthetic repositories never access a network."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shared-origin-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'caller'
        self.shared = self.root / '.reusable-workflows'
        self.local = self.root / '.github/workflows'
        self.local.mkdir(parents=True)
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            if path.name != 'cve-triage.lock.yml':
                shutil.copyfile(path, self.local / path.name)
        shutil.copyfile(ROOT / '.github/dependabot.yml', self.root / '.github/dependabot.yml')
        caller = self.read('validate-base-images.yml')['jobs']['validate']['uses']
        self.repository, original_sha = caller.split('/.github/workflows/')[0], caller.rsplit('@', 1)[1]
        self.policy = self.root / 'policies/governance/reusable-workflows.json'
        self.write_policy(self.repository)
        (self.shared / '.github/workflows').mkdir(parents=True)
        # Unit tests stay independent of the optional shared checkout. The
        # integration suite reads the actual pinned release and its full API.
        action = next(step['uses'] for step in self.read('promote-stable.yml')['jobs']['promote']['steps']
                      if step.get('name') == 'Install Trivy')
        fixture_inputs = (
            {'frameworks': {'type': 'string', 'required': True},
             'melange-config': {'type': 'string'}, 'locked-build': {'type': 'boolean'}},
            {'framework': {'type': 'string', 'required': True},
             'artifact-run-id': {'type': 'string'}},
        )
        for name, inputs in zip(WORKFLOWS, fixture_inputs):
            steps = [{'uses': 'actions/upload-artifact@' + 'a' * 40,
                      'with': {'name': 'validated-oci-example', 'retention-days': 3}}]
            if name == 'validate-apko-images.yml':
                steps.insert(0, {'name': 'Install Trivy', 'uses': action})
            fixture = {'on': {'workflow_call': {'inputs': inputs}},
                       'permissions': {'contents': 'read'},
                       'jobs': {'validate': {'runs-on': 'ubuntu-latest',
                                             'timeout-minutes': 10, 'steps': steps}}}
            (self.shared / '.github/workflows' / name).write_text(yaml.safe_dump(fixture))
        self.git('init', '-q')
        self.git('remote', 'add', 'origin', f'https://github.com/{self.repository}.git')
        self.sha = self.commit_shared()
        self.replace_local(original_sha, self.sha)
        self.remote = self.shared / '.github/workflows/validate-apko-images.yml'
        self.output = self.root / 'github-output.txt'

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.shared), *args], check=True,
                              capture_output=True, text=True).stdout

    def commit_shared(self):
        self.git('add', *('.github/workflows/' + name for name in WORKFLOWS))
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD').strip()

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
        old = self.repository
        self.replace_local(old, repository)
        for name in WORKFLOWS:
            path = self.shared / '.github/workflows' / name
            path.write_text(path.read_text().replace(old, repository))
        previous_sha = self.sha
        self.sha = self.commit_shared()
        self.replace_local(previous_sha, self.sha)
        self.git('remote', 'set-url', 'origin', f'https://github.com/{repository}.git')
        self.write_policy(repository)
        self.repository = repository

    def call(self, mode='lint', extra_env=None):
        env = os.environ.copy()
        env.pop('REUSABLE_WORKFLOWS_PATH', None)
        env.pop('GITHUB_OUTPUT', None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ['python3', '-B', '-m', 'scripts.pipeline.governance.workflow_dependencies',
             mode, '--root', str(self.root)], cwd=ROOT, env=env,
            capture_output=True, text=True)

    def rejected(self, mode='lint'):
        self.output.write_text('existing=value\n')
        result = self.call(mode, {'GITHUB_OUTPUT': str(self.output)})
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.output.read_text(), 'existing=value\n',
                         'Failure must not publish partial checkout outputs')
        self.assertEqual(result.stdout, '', 'Failure must not print a successful lint result')
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

    def test_sandbox_origin_fixture_resolves_through_cli_and_reads_actual_uploaders(self):
        result = self.call('checkout')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'repository={self.repository}\nref={self.sha}\n')
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(dependency.dependencies(self.root)), 2)
        paths = dependency.workflow_files(self.root, self.shared)
        self.assertIn(self.remote, paths)
        self.assertIn(self.shared / '.github/workflows/test-runtime-images.yml', paths)
        document = yaml.safe_load(self.remote.read_text())
        uploads = [step for job in document['jobs'].values() for step in job.get('steps', [])
                   if step.get('uses', '').startswith('actions/upload-artifact@')]
        self.assertTrue(any(step.get('with', {}).get('retention-days') == 3 for step in uploads))

    def test_alternative_origin_migration_is_coherent_through_real_cli(self):
        self.migrate(ALTERNATIVE)
        self.assertEqual(dependency.approved_repository(self.root), ALTERNATIVE)
        result = self.call('checkout', {'GITHUB_OUTPUT': str(self.output)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.output.read_text(), f'repository={ALTERNATIVE}\nref={self.sha}\n')
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(all(entry['repository'] == ALTERNATIVE
                            for entry in dependency.dependencies(self.root)))

    def test_missing_or_invalid_approved_origin_fails_before_cli_output(self):
        self.policy.unlink()
        self.rejected('checkout')
        for document in ('{', '[]', '{}', '{"schema_version": 2, "repository": "a/b"}',
                         '{"schema_version": 1, "repository": "a/b", "extra": true}',
                         '{"schema_version": 1, "repository": "a/b", "repository": "c/d"}'):
            with self.subTest(document=document):
                self.policy.write_text(document)
                with self.assertRaises(ValueError):
                    dependency.approved_repository(self.root)
                self.rejected('checkout')

    def test_unsafe_origin_values_are_rejected_without_output(self):
        for value in ('', 'repo-only', 'owner/repo/extra', '../repo', 'owner/..',
                      'owner/*', 'owner/repo@main', 'owner/repo?x',
                      'https://github.com/owner/repo', 'owner/repo\ninjected=value',
                      'owner/$(touch x)', 'owner/${{ vars.REPO }}', None, 123):
            with self.subTest(value=value):
                self.write_policy(value)
                with self.assertRaises(ValueError):
                    dependency.approved_repository(self.root)
                self.rejected('checkout')

    def test_environment_does_not_override_reviewed_origin(self):
        result = self.call('checkout', {'REUSABLE_WORKFLOWS_REPOSITORY': ALTERNATIVE,
                                        'REUSABLE_WORKFLOWS_SHA': 'a' * 40})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f'repository={self.repository}\nref={self.sha}\n')

    def test_mixed_caller_origin_reproduced_false_pass_is_now_rejected(self):
        uses = self.read('test-runtime-images.yml')['jobs']['runtime']['uses']
        self.change_caller(uses=uses.replace(self.repository, ALTERNATIVE))
        with self.assertRaises(ValueError):
            dependency.dependencies(self.root)
        self.rejected('checkout')

    def test_declaring_new_origin_does_not_implicitly_migrate_callers(self):
        self.write_policy(ALTERNATIVE)
        self.rejected('checkout')

    def test_migrated_origin_rejects_one_caller_left_at_old_origin(self):
        previous_origin = self.repository
        self.migrate(ALTERNATIVE)
        uses = self.read('test-runtime-images.yml')['jobs']['runtime']['uses']
        self.change_caller(uses=uses.replace(ALTERNATIVE, previous_origin))
        result = self.rejected('checkout')
        self.assertIn('test-runtime-images.yml/runtime', result.stderr)

    def test_missing_required_caller_job_is_not_reduced_coverage(self):
        for name, job in (('validate-base-images.yml', 'validate'), ('test-runtime-images.yml', 'runtime')):
            original = self.read(name)
            altered = self.read(name)
            del altered['jobs'][job]
            with self.subTest(name=name):
                self.write(name, altered)
                self.rejected('checkout')
            self.write(name, original)

    def test_missing_required_caller_file_is_rejected(self):
        (self.local / 'test-runtime-images.yml').unlink()
        self.rejected('checkout')

    def test_invalid_or_wrong_caller_reference_is_rejected(self):
        suffix = '/.github/workflows/test-runtime-images.yml@'
        for value in ('main', 'v1', 'a' * 39, 'a' * 41, 'g' * 40,
                      'a' * 40 + '/../../bad', '${{ vars.SHA }}'):
            with self.subTest(ref=value):
                self.change_caller(uses=self.repository + suffix + value)
                self.rejected('checkout')
        for uses in (self.repository + '/.github/workflows/other.yml@' + self.sha,
                     './.github/workflows/test-runtime-images.yml', None, 23):
            with self.subTest(uses=uses):
                self.change_caller(uses=uses)
                self.rejected('checkout')

    def test_mixed_shared_workflow_releases_are_rejected(self):
        uses = self.read('test-runtime-images.yml')['jobs']['runtime']['uses']
        self.change_caller(uses=uses.replace(self.sha, 'a' * 40))
        self.rejected('checkout')

    def test_mixed_tool_origin_reproduced_false_pass_is_now_rejected(self):
        self.change_tool(transform=lambda step: step.update(uses=step['uses'].replace(self.repository, ALTERNATIVE)))
        with self.assertRaises(ValueError):
            dependency.tooling_consistency(dependency.workflow_files(self.root, self.shared), root=self.root)
        self.rejected('checkout')

    def test_migrated_origin_rejects_one_action_left_at_old_origin(self):
        previous_origin = self.repository
        self.migrate(ALTERNATIVE)
        self.change_tool(transform=lambda step: step.update(
            uses=step['uses'].replace(ALTERNATIVE, previous_origin)))
        result = self.rejected('checkout')
        self.assertIn('promote-stable.yml/promote/Install Trivy', result.stderr)

    def test_missing_required_tool_step_is_rejected(self):
        document = self.read('recover-stable.yml')
        document['jobs']['recover']['steps'] = [step for step in document['jobs']['recover']['steps']
                                               if step.get('name') != 'Install Trivy']
        self.write('recover-stable.yml', document)
        self.rejected('checkout')

    def test_missing_tool_reference_or_run_replacement_is_rejected(self):
        def replace(step):
            step.pop('uses')
            step['run'] = 'echo unavailable'
        self.change_tool(transform=replace)
        self.rejected('checkout')

    def test_duplicate_required_tool_step_is_rejected(self):
        document = self.read('promote-stable.yml')
        step = next(step for step in document['jobs']['promote']['steps'] if step.get('name') == 'Install Trivy')
        document['jobs']['promote']['steps'].append(dict(step))
        self.write('promote-stable.yml', document)
        self.rejected('checkout')

    def test_tool_pin_must_be_full_sha_and_consistent(self):
        prefix = self.repository + '/actions/setup-trivy@'
        for ref in ('main', 'v1', 'a' * 39, 'z' * 40, 'a' * 40):
            with self.subTest(ref=ref):
                self.change_tool(transform=lambda step: step.update(uses=prefix + ref))
                self.rejected('checkout')

    def test_tool_pin_is_distinct_from_shared_release_when_consistent(self):
        # Fixture commit hashes the actual workflows; the action pin stays independent.
        document = self.read('promote-stable.yml')
        ref = next(step['uses'].rsplit('@', 1)[1] for step in document['jobs']['promote']['steps']
                   if step.get('name') == 'Install Trivy')
        self.assertNotEqual(ref, self.sha)
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_internal_tool_origin_in_reviewed_release_is_rejected(self):
        previous_sha = self.sha
        self.remote.write_text(self.remote.read_text().replace(
            self.repository + '/actions/setup-trivy@', ALTERNATIVE + '/actions/setup-trivy@'))
        self.sha = self.commit_shared()
        self.replace_local(previous_sha, self.sha)
        result = self.rejected()
        self.assertIn('validate-apko-images.yml', result.stderr)

    def test_internal_tool_pin_divergence_in_reviewed_release_is_rejected(self):
        previous_sha = self.sha
        document = yaml.safe_load(self.remote.read_text())
        step = next(step for step in document['jobs']['validate']['steps'] if step.get('name') == 'Install Trivy')
        step['uses'] = self.repository + '/actions/setup-trivy@' + 'a' * 40
        self.remote.write_text(yaml.safe_dump(document, sort_keys=False))
        self.sha = self.commit_shared()
        self.replace_local(previous_sha, self.sha)
        self.rejected()

    def test_missing_internal_tool_step_in_reviewed_release_is_rejected(self):
        previous_sha = self.sha
        document = yaml.safe_load(self.remote.read_text())
        document['jobs']['validate']['steps'] = [step for step in document['jobs']['validate']['steps']
                                                if step.get('name') != 'Install Trivy']
        self.remote.write_text(yaml.safe_dump(document, sort_keys=False))
        self.sha = self.commit_shared()
        self.replace_local(previous_sha, self.sha)
        result = self.rejected()
        self.assertIn('validate-apko-images.yml', result.stderr)

    def test_dependabot_group_origin_must_match_approval(self):
        path = self.root / '.github/dependabot.yml'
        path.write_text(path.read_text().replace(self.repository + '*', ALTERNATIVE + '*'))
        self.rejected('checkout')

    def test_fast_check_checkout_cannot_override_resolved_origin_or_pin(self):
        original = self.read('test-promotion.yml')
        for field, value in (('repository', ALTERNATIVE), ('ref', 'main'), ('persist-credentials', True)):
            document = self.read('test-promotion.yml')
            step = next(step for step in document['jobs']['test']['steps']
                        if step.get('name') == 'Checkout reusable workflows at the caller SHA')
            step['with'][field] = value
            with self.subTest(field=field):
                self.write('test-promotion.yml', document)
                self.rejected('checkout')
            self.write('test-promotion.yml', original)

    def test_additional_uninventoried_shared_dependency_is_rejected(self):
        document = self.read('test-runtime-images.yml')
        document['jobs']['extra'] = {'uses': self.repository + '/.github/workflows/extra.yml@' + self.sha}
        self.write('test-runtime-images.yml', document)
        self.rejected('checkout')

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

    def test_missing_checkout_fails_instead_of_omitting_shared_artifacts(self):
        with self.assertRaises(ValueError):
            dependency.shared_workflows(self.root, self.shared / 'missing')
        self.rejected_with_checkout_path(self.shared / 'missing')

    def rejected_with_checkout_path(self, path):
        result = self.call('lint', {'REUSABLE_WORKFLOWS_PATH': str(path)})
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_checkout_directory_override_does_not_override_revision(self):
        for name, job in (('validate-base-images.yml', 'validate'), ('test-runtime-images.yml', 'runtime')):
            document = self.read(name)
            document['jobs'][job]['uses'] = document['jobs'][job]['uses'].replace(self.sha, 'a' * 40)
            self.write(name, document)
        self.rejected_with_checkout_path(self.shared)

    def test_checkout_origin_mismatch_or_missing_remote_is_rejected(self):
        for value in (f'https://github.com/{ALTERNATIVE}.git', 'https://unapproved.invalid/a/b.git',
                      f'https://user:password@github.com/{self.repository}.git',
                      f'https://github.com/{self.repository}.git?extra=1'):
            with self.subTest(origin=value):
                self.git('remote', 'set-url', 'origin', value)
                self.rejected_with_checkout_path(self.shared)
        self.git('remote', 'remove', 'origin')
        self.rejected_with_checkout_path(self.shared)

    def test_supported_git_origin_spellings_match_one_approved_identity(self):
        for value in (f'https://github.com/{self.repository}', f'https://github.com/{self.repository}.git',
                      f'git@github.com:{self.repository}.git', f'ssh://git@github.com/{self.repository}.git'):
            with self.subTest(origin=value):
                self.git('remote', 'set-url', 'origin', value)
                result = self.call()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_edited_workflow_cannot_mask_pinned_retention(self):
        self.remote.write_text(self.remote.read_text().replace('retention-days: 3', 'retention-days: 9'))
        self.rejected()

    def test_missing_checkout_workflow_cannot_reduce_coverage(self):
        (self.shared / '.github/workflows/test-runtime-images.yml').unlink()
        self.rejected()

    def test_shared_required_and_unknown_inputs_are_rejected(self):
        original = self.read('validate-base-images.yml')
        for supplied in ({}, {'frameworks': '[]', 'test-command': 'true'}):
            document = self.read('validate-base-images.yml')
            document['jobs']['validate']['with'] = supplied
            with self.subTest(supplied=supplied):
                self.write('validate-base-images.yml', document)
                self.rejected()
            self.write('validate-base-images.yml', original)

    def test_malformed_or_wrong_shape_local_yaml_is_rejected(self):
        path = self.local / 'test-runtime-images.yml'
        for text in ('jobs: [', '- list\n', 'jobs: null\n', 'jobs: []\n',
                     'jobs: {}\njobs: {}\n'):
            with self.subTest(text=text):
                path.write_text(text)
                self.rejected('checkout')

    def test_invalid_git_head_response_fails_closed(self):
        real_run = subprocess.run
        def malformed(command, *args, **kwargs):
            if command[0] == 'git' and 'rev-parse' in command:
                return subprocess.CompletedProcess(command, 0, stdout=b'not-a-commit\n', stderr=b'')
            return real_run(command, *args, **kwargs)
        with patch.object(dependency.subprocess, 'run', side_effect=malformed):
            with self.assertRaises(ValueError):
                dependency.shared_workflows(self.root, self.shared)

    def test_git_execution_failure_has_no_fallback(self):
        with patch.object(dependency.subprocess, 'run', side_effect=subprocess.CalledProcessError(128, ['git'])):
            with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                dependency.shared_workflows(self.root, self.shared)


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
