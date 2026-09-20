"""Security and plan/apply continuity contracts for the Infra entrypoints."""

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / '.github' / 'workflows'


def load_workflow(name):
    # BaseLoader keeps GitHub's `on` key intact (YAML 1.1 treats it as bool).
    return yaml.load((WORKFLOWS / name).read_text(encoding='utf-8'),
                     Loader=yaml.BaseLoader)


def shell(job):
    return '\n'.join(step.get('run', '') for step in job['steps'])


def action_step(job, action):
    matches = [step for step in job['steps']
               if step.get('uses', '').startswith(action + '@')]
    if len(matches) != 1:
        raise AssertionError(f'Expected one {action}, found {len(matches)}')
    return matches[0]


def step_index(job, token):
    matches = [index for index, step in enumerate(job['steps'])
               if token in step.get('run', '') or token in step.get('uses', '')]
    if len(matches) != 1:
        raise AssertionError(f'Expected one step matching {token!r}: {matches}')
    return matches[0]


class InfraWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pr = load_workflow('infra-pr.yml')
        cls.apply = load_workflow('infra-apply.yml')

    def test_only_pr_and_explicit_main_dispatch_can_run_infra(self):
        self.assertEqual(set(self.pr['on']), {'pull_request'})
        self.assertEqual(set(self.apply['on']), {'workflow_dispatch'})
        self.assertTrue({'infra/**', 'frameworks/**'}.issubset(
            self.pr['on']['pull_request']['paths']))
        for job in self.apply['jobs'].values():
            self.assertEqual(job['if'], "github.ref == 'refs/heads/main'")
        self.assertEqual(self.apply['concurrency']['cancel-in-progress'], 'false')
        self.assertNotIn('${{', self.apply['concurrency']['group'])
        self.assertEqual(self.pr['concurrency'], self.apply['concurrency'])

    def test_forks_receive_checks_without_oidc_and_pr_never_applies(self):
        checks = self.pr['jobs']['checks']
        plan = self.pr['jobs']['plan']
        self.assertEqual(checks['permissions'], {'contents': 'read'})
        self.assertEqual(plan['needs'], 'checks')
        self.assertEqual(plan['if'],
                         'github.event.pull_request.head.repo.full_name == github.repository')
        self.assertNotIn('environment', plan)
        self.assertIn('unittest discover -s infra/tests', shell(checks))
        self.assertFalse(any(step.get('uses', '').startswith(
            'aws-actions/configure-aws-credentials@') for step in checks['steps']))
        for job in self.pr['jobs'].values():
            self.assertNotRegex(shell(job), r'terraform[^\n]*\bapply\b')

    def test_permissions_are_job_local_and_roles_are_infra_specific(self):
        for workflow in (self.pr, self.apply):
            self.assertEqual(workflow['permissions'], {})
            for job in workflow['jobs'].values():
                self.assertTrue(set(job['permissions']).issubset(
                    {'contents', 'id-token'}))
                if job['permissions'].get('id-token') == 'write':
                    credentials = action_step(job, 'aws-actions/configure-aws-credentials')
                    role = credentials['with']['role-to-assume']
                    self.assertIn(role, ('${{ vars.INFRA_PLAN_ROLE_ARN }}',
                                         '${{ vars.INFRA_APPLY_ROLE_ARN }}'))
                    self.assertNotIn('aws-access-key-id', credentials['with'])
                    self.assertNotIn('aws-secret-access-key', credentials['with'])
        pr_credentials = action_step(self.pr['jobs']['plan'],
                                     'aws-actions/configure-aws-credentials')
        self.assertEqual(pr_credentials['with']['role-to-assume'],
                         '${{ vars.INFRA_PLAN_ROLE_ARN }}')
        for job in self.apply['jobs'].values():
            self.assertEqual(job['environment'], 'lab-image-base-infra')
            credentials = action_step(job, 'aws-actions/configure-aws-credentials')
            self.assertEqual(credentials['with']['role-to-assume'],
                             '${{ vars.INFRA_APPLY_ROLE_ARN }}')
            self.assertLess(step_index(job, 'unittest discover -s infra/tests'),
                            step_index(job, 'aws-actions/configure-aws-credentials'))

    def test_every_backend_init_follows_independent_fail_closed_ensure(self):
        for workflow in (self.pr, self.apply):
            self.assertEqual(workflow['env']['TF_STATE_BUCKET'],
                             '${{ vars.INFRA_TF_STATE_BUCKET }}')
            self.assertEqual(workflow['env']['TF_STATE_KEY'],
                             'alric-containers-image-base/terraform.tfstate')
            self.assertEqual(workflow['env']['TF_BACKEND_REGION'],
                             '${{ vars.INFRA_BACKEND_REGION }}')
            for job in workflow['jobs'].values():
                if ' init ' not in shell(job):
                    continue
                ensure = step_index(job, 'python3 infra/backend.py ensure')
                init = step_index(job, 'terraform -chdir=infra/ecr init')
                self.assertLess(ensure, init)
                command = job['steps'][ensure]['run']
                self.assertIn('set -euo pipefail', command)
                for flag in ('--bucket "$TF_STATE_BUCKET"',
                             '--region "$TF_BACKEND_REGION"',
                             '--account-id "$AWS_ACCOUNT_ID"'):
                    self.assertIn(flag, command)
                self.assertNotIn('continue-on-error', job['steps'][ensure])
                self.assertNotIn('||', command)
                self.assertIn('-lockfile=readonly', job['steps'][init]['run'])
                self.assertIn('-backend-config="region=$TF_BACKEND_REGION"',
                              job['steps'][init]['run'])
                self.assertIn('set -euo pipefail', job['steps'][init]['run'])
                self.assertIn('| tee ', job['steps'][init]['run'])

    def test_apply_consumes_same_run_plan_and_revision_before_any_apply(self):
        plan = self.apply['jobs']['plan']
        apply = self.apply['jobs']['apply']
        self.assertEqual(apply['needs'], 'plan')
        artifact = plan['outputs']['plan-artifact']
        self.assertIn('github.run_id', artifact)
        self.assertIn('github.run_attempt', artifact)
        self.assertEqual(action_step(plan, 'actions/upload-artifact')['with']['name'],
                         artifact)
        self.assertEqual(action_step(apply, 'actions/download-artifact')['with']['name'],
                         '${{ needs.plan.outputs.plan-artifact }}')
        self.assertLess(step_index(plan, 'sha256sum infra.tfplan revision.txt'),
                        step_index(plan, 'actions/upload-artifact'))
        apply_index = step_index(apply, 'terraform -chdir=infra/ecr apply')
        self.assertLess(step_index(apply, 'sha256sum --check'), apply_index)
        self.assertLess(step_index(apply, 'verify_plan.py "$RUNNER_TEMP/verified-plan.json"'),
                        apply_index)
        self.assertIn('test "$(cat revision.txt)" = "$GITHUB_SHA"', shell(apply))
        command = apply['steps'][apply_index]['run']
        self.assertIn('"$RUNNER_TEMP/infra-plan/infra.tfplan"', command)
        self.assertNotIn('-auto-approve', command)
        for step in apply['steps'][:apply_index]:
            self.assertNotRegex(step.get('run', ''), r'terraform[^\n]*\bplan\s')
        for job in (plan, apply):
            self.assertEqual(action_step(job, 'actions/checkout')['with']['ref'],
                             '${{ github.sha }}')
            self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"', shell(job))

    def test_scope_gate_precedes_plan_upload_and_post_apply_requires_noop(self):
        for job in (self.pr['jobs']['plan'], self.apply['jobs']['plan']):
            self.assertLess(step_index(job, 'python3 infra/ecr/verify_plan.py'),
                            step_index(job, 'actions/upload-artifact'))
        apply = self.apply['jobs']['apply']
        drift = step_index(apply, '-detailed-exitcode')
        self.assertGreater(drift, step_index(apply, 'terraform -chdir=infra/ecr apply'))
        command = apply['steps'][drift]['run']
        self.assertIn('if [ "${drift_status:-0}" -ne 0 ]', command)
        self.assertIn('exit "${drift_status:-1}"', command)
        self.assertIn('--mode noop', command)
        self.assertNotIn('continue-on-error', apply['steps'][drift])

    def test_aws_readback_runs_after_noop_and_failure_evidence_is_retained(self):
        apply = self.apply['jobs']['apply']
        readback_index = step_index(apply, 'python3 infra/readback.py')
        self.assertGreater(readback_index, step_index(apply, '-detailed-exitcode'))
        command = apply['steps'][readback_index]['run']
        self.assertIn('set -euo pipefail', command)
        self.assertIn('--expect-empty', command)
        self.assertIn('--account-id "$AWS_ACCOUNT_ID"', command)
        self.assertIn('--region "$AWS_REGION"', command)
        self.assertNotIn('continue-on-error', apply['steps'][readback_index])
        for job in (self.pr['jobs']['plan'], *self.apply['jobs'].values()):
            upload = action_step(job, 'actions/upload-artifact')
            self.assertEqual(upload['if'], '${{ always() }}')
            ensure = job['steps'][step_index(job, 'python3 infra/backend.py ensure')]['run']
            self.assertIn('| tee ', ensure)
        evidence = action_step(apply, 'actions/upload-artifact')['with']['path']
        for path in ('backend-ensure-plan.json', 'infra-backend-ensure.json',
                     'init-plan.txt', 'infra-init.txt', 'plan.txt',
                     'post-apply.txt', 'infra-readback.json'):
            self.assertIn(path, evidence)
        pr_evidence = action_step(self.pr['jobs']['plan'], 'actions/upload-artifact')['with']['path']
        self.assertIn('infra-backend-ensure.json', pr_evidence)
        self.assertIn('infra-init.txt', pr_evidence)

    def test_all_actions_and_terraform_are_pinned(self):
        for workflow in (self.pr, self.apply):
            self.assertEqual(workflow['env']['TF_VERSION'], '1.15.8')
            for job in workflow['jobs'].values():
                self.assertIn('timeout-minutes', job)
                for step in job['steps']:
                    if 'uses' in step:
                        self.assertRegex(step['uses'], r'@[0-9a-f]{40}$')
                    if step.get('uses', '').startswith('actions/checkout@'):
                        self.assertEqual(step['with']['persist-credentials'], 'false')
                    self.assertIsNone(re.search(r'\$\{\{', step.get('run', '')))


if __name__ == '__main__':
    unittest.main()
