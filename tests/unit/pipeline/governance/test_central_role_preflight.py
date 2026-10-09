"""Stage A is manual, isolated, OIDC-only and restricted to identity inspection."""
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.pipeline.governance import configuration, lint_workflow_hardening


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / '.github/workflows/factory-central-role-preflight.yml'
ROLE = 'itau-github-repo-factory-distroless-v1'
ACCOUNT = '712107929769'
ROLE_ID = 'AROA2LTHQWCU2N3H2OE3L'
ACTION = 'aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd'
GUARD = ("github.repository == 'alric-corp/alric-containers-image-base' && "
         "github.ref == 'refs/heads/develop' && github.event_name == 'workflow_dispatch'")
CHANGED_PATHS = (
    '.github/workflows/factory-central-role-preflight.yml',
    'tests/unit/pipeline/governance/test_central_role_preflight.py',
    'tests/unit/pipeline/governance/test_configuration.py',
    'infra/tests/test_external_iam_contract.py',
    'docs/factory-central-role-preflight.md',
)


class CentralRolePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        cls.doc = yaml.safe_load(cls.text)

    def test_dispatch_only_without_inputs_or_automatic_triggers(self):
        self.assertEqual(self.doc.get('on', self.doc.get(True)), {'workflow_dispatch': {}})
        self.assertEqual(self.doc['permissions'], {})
        self.assertEqual(self.doc['concurrency'], {'group': 'factory-central-role-preflight', 'cancel-in-progress': False})

    def test_two_separate_guarded_environments_and_minimal_job_permissions(self):
        self.assertEqual(set(self.doc['jobs']), {'dev', 'infra'})
        for name, environment in [('dev', 'DEV'), ('infra', 'lab-image-base-infra')]:
            job = self.doc['jobs'][name]
            self.assertEqual(job['environment'], environment)
            self.assertEqual(job['if'], GUARD)
            self.assertEqual(job['runs-on'], 'ubuntu-latest')
            self.assertEqual(job['timeout-minutes'], 5)
            self.assertEqual(job['permissions'], {'contents': 'read', 'id-token': 'write'})
            self.assertNotIn('needs', job)
            self.assertNotIn('continue-on-error', job)

    def test_oidc_action_pin_and_no_credential_fallback(self):
        approved = yaml.safe_load((ROOT / '.github/workflows/infra-apply.yml').read_text())
        pins = {s['uses'] for j in approved['jobs'].values() for s in j.get('steps', [])
                if s.get('uses', '').startswith('aws-actions/configure-aws-credentials@')}
        self.assertEqual(pins, {ACTION})
        for job in self.doc['jobs'].values():
            self.assertEqual(len(job['steps']), 2)
            step = job['steps'][0]
            self.assertEqual(step['uses'], ACTION)
            self.assertNotIn('continue-on-error', step)
            self.assertNotIn('if', job['steps'][1])  # do not run proof after auth failure
            self.assertEqual(step['with'], {
                'role-to-assume': 'arn:aws:iam::' + ACCOUNT + ':role/' + ROLE,
                'aws-region': 'us-east-1', 'allowed-account-ids': ACCOUNT,
                'audience': 'sts.amazonaws.com', 'role-session-name': '${{ env.ROLE_SESSION_NAME }}',
                'role-duration-seconds': 900, 'unset-current-credentials': True,
                'use-existing-credentials': False, 'force-skip-oidc': False, 'role-chaining': False,
                'translate-env-variables': False, 'output-credentials': False, 'action-timeout-s': 120,
                'inline-session-policy': '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"sts:GetCallerIdentity","Resource":"*"}]}',
            })
        for forbidden in ('secrets.', 'vars.', 'Tomas-Instructor', 'aws-access-key-id:',
                          'aws-secret-access-key:', 'web-identity-token-file:', 'aws-profile:'):
            self.assertNotIn(forbidden, self.text)

    def test_trust_has_exact_subject_for_each_job_and_no_new_wildcard(self):
        trust = json.loads((ROOT / 'policies/aws/factory-distroless-v1.trust.json').read_text())
        statement = trust['Statement'][0]
        self.assertEqual(len(trust['Statement']), 1)
        self.assertEqual(statement['Action'], 'sts:AssumeRoleWithWebIdentity')
        self.assertEqual(statement['Principal'], {'Federated': f'arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com'})
        self.assertEqual(statement['Condition'], {'StringEquals': {
            'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
            'token.actions.githubusercontent.com:repository_id': '1360616627',
            'token.actions.githubusercontent.com:repository_owner_id': '178685987',
            'token.actions.githubusercontent.com:sub': [
                'repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:lab-image-base-infra',
                'repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:DEV',
            ],
        }})

    def test_no_mutable_commands_and_no_reusable_or_auxiliary_action(self):
        for job in self.doc['jobs'].values():
            self.assertNotIn('uses', job)
            script = job['steps'][1]['run']
            self.assertEqual([line.strip() for line in script.splitlines() if line.strip().startswith('aws ')], [
                'aws sts get-caller-identity --region us-east-1 --output json --no-cli-pager > "$RUNNER_TEMP/central-role-identity.json"'])
            for forbidden in ('terraform', 'docker', 's3 ', 'ecr ', 'iam ', 'curl ', 'wget ', 'eval ', 'exec('):
                self.assertNotIn(forbidden, script)
        self.assertEqual(lint_workflow_hardening.check(WORKFLOW.name, self.doc), [])

    def test_preflight_changes_do_not_match_publication_paths_but_cutover_will(self):
        publisher = yaml.safe_load((ROOT / '.github/workflows/workflow.yml').read_text())
        events = publisher.get('on', publisher.get(True))
        for event in ('push', 'pull_request'):
            patterns = events[event]['paths']
            for name in CHANGED_PATHS:
                self.assertFalse(any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns), (event, name))
            for name in ('scripts/pipeline/governance/configuration.py', 'policies/pipeline/config.json'):
                self.assertTrue(any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns), name)

    def test_operational_resolution_stays_legacy_until_stage_b(self):
        cfg = configuration.configuration()
        self.assertNotIn('factory', cfg)
        self.assertFalse(cfg['infra']['plan_enabled'])
        self.assertEqual(configuration.settings(cfg, 'DEV')['AWS_ROLE_ARN'],
                         f'arn:aws:iam::{ACCOUNT}:role/alric-image-base-factory-dev')
        self.assertEqual(configuration.settings(cfg, 'INFRA_APPLY')['AWS_ROLE_ARN'],
                         f'arn:aws:iam::{ACCOUNT}:role/alric-github-repo-1360616627-infra-apply')
        self.assertEqual(configuration.settings(cfg, 'HOM')['AWS_ROLE_ARN'],
                         'arn:aws:iam::248908662184:role/alric-image-base-factory-hom')

    def execute_proof(self, job_name='dev', changes=None, aws_exit=0):
        job = self.doc['jobs'][job_name]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            fake = path / 'aws'
            fake.write_text('#!' + sys.executable + '\nimport os,sys\n'
                            'assert sys.argv[1:] == ["sts","get-caller-identity","--region","us-east-1","--output","json","--no-cli-pager"]\n'
                            'print(os.environ["FAKE_STS_RESPONSE"])\n'
                            'sys.exit(int(os.environ["FAKE_AWS_EXIT"]))\n')
            fake.chmod(0o700)
            session = 'factory-preflight-123-1-' + job_name
            identity = {'Account': ACCOUNT, 'Arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}/{session}',
                        'UserId': ROLE_ID + ':' + session}
            identity.update(changes or {})
            env = dict(os.environ, **job['env'])
            env.update(PATH=str(path) + os.pathsep + os.environ['PATH'], RUNNER_TEMP=directory,
                       ROLE_SESSION_NAME=session, GITHUB_STEP_SUMMARY=str(path / 'summary'),
                       GITHUB_REPOSITORY='alric-corp/alric-containers-image-base', GITHUB_SHA='a' * 40,
                       GITHUB_REF='refs/heads/develop', GITHUB_EVENT_NAME='workflow_dispatch',
                       GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1',
                       FAKE_STS_RESPONSE=json.dumps(identity), FAKE_AWS_EXIT=str(aws_exit))
            result = subprocess.run(['bash', '-c', job['steps'][1]['run']], env=env, capture_output=True, text=True)
            report = json.loads(result.stdout) if result.stdout.strip() else None
            return result.returncode, report

    def test_identity_positive_for_both_contexts(self):
        for name, environment in [('dev', 'DEV'), ('infra', 'lab-image-base-infra')]:
            code, report = self.execute_proof(name)
            self.assertEqual(code, 0)
            self.assertEqual(report['result'], 'PASS')
            self.assertEqual(report['environment'], environment)
            self.assertFalse(report['cutover_executed'])
            self.assertEqual(report['source_sha'], 'a' * 40)

    def test_wrong_account_role_id_role_arn_or_session_fails(self):
        for change in ({'Account': '000000000000'}, {'Arn': f'arn:aws:iam::{ACCOUNT}:user/Tomas-Instructor'},
                       {'UserId': 'ANOTHER_ROLE:factory-preflight-123-1-dev'},
                       {'Arn': f'arn:aws:sts::{ACCOUNT}:assumed-role/{ROLE}/another-session'}):
            with self.subTest(change=change):
                code, report = self.execute_proof(changes=change)
                self.assertNotEqual(code, 0)
                self.assertEqual(report['result'], 'FAIL')

    def test_sts_failure_never_reports_pass(self):
        code, report = self.execute_proof(aws_exit=42)
        self.assertEqual(code, 42)
        self.assertIsNone(report)


if __name__ == '__main__':
    unittest.main()
