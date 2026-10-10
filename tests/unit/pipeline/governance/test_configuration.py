"""Configuration must select the right account and fail before AWS access."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts.pipeline.governance import configuration as config
from scripts.pipeline.release import lifecycle


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = config.configuration()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def load(self, cfg):
        path = self.directory / 'config.json'
        path.write_text(json.dumps(cfg))
        return config.configuration(path)

    def test_each_scope_selects_exact_account_role_and_backend(self):
        expected = {
            'DEV': ('712107929769', 'us-east-1', 'itau-github-repo-factory-distroless-v1'),
            'HOM': ('248908662184', 'sa-east-1', 'alric-image-base-factory-hom'),
            'INFRA_PLAN': ('712107929769', 'us-east-1', 'alric-github-repo-1360616627-infra-plan'),
            'INFRA_APPLY': ('712107929769', 'us-east-1', 'itau-github-repo-factory-distroless-v1'),
        }
        for scope, (account, region, role) in expected.items():
            with self.subTest(scope=scope):
                settings = config.settings(self.cfg, scope)
                self.assertEqual(settings['AWS_ACCOUNT_ID'], account)
                self.assertEqual(settings['AWS_REGION'], region)
                self.assertEqual(settings['AWS_ROLE_ARN'], f'arn:aws:iam::{account}:role/{role}')
                if scope.startswith('INFRA_'):
                    self.assertEqual(settings['TF_STATE_BUCKET'], '712107929769-alric-containers-image-base-tfstate')
                    self.assertEqual(settings['TF_BACKEND_REGION'], 'us-east-2')
                    self.assertEqual(settings['TF_STATE_KEY'], 'alric-containers-image-base/terraform.tfstate')

    def test_operational_role_configuration_is_required_and_strict(self):
        for value in (None, {}, {'operational_role_name': True},
                      {'operational_role_name': 'bad/name'},
                      {'operational_role_name': 'name\nINJECTED=true'},
                      {'operational_role_name': 'x' * 65},
                      {'operational_role_name': self.cfg['DEV']['role_name']},
                      {'operational_role_name': 'valid', 'role_arn': 'alternative'}):
            cfg = copy.deepcopy(self.cfg)
            cfg['factory'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load(cfg)
        cfg = copy.deepcopy(self.cfg)
        del cfg['factory']
        with self.assertRaises(ValueError):
            self.load(cfg)

    def test_enabling_privileged_pr_plan_fails_closed_at_load_and_resolution(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['infra']['plan_enabled'] = True
        with self.assertRaisesRegex(ValueError, 'separately reviewed'):
            self.load(cfg)
        for scope in ('INFRA_PLAN', 'INFRA_APPLY', 'DEV'):
            with self.subTest(scope=scope), self.assertRaisesRegex(ValueError, 'separately reviewed'):
                config.settings(cfg, scope)

    def test_pull_request_cannot_emit_privileged_settings(self):
        for event in ('pull_request', 'pull_request_target', 'pull_request_review'):
            for scope in ('DEV', 'INFRA_APPLY', 'HOM'):
                output = self.directory / 'output'
                env = self.directory / 'env'
                with self.subTest(event=event, scope=scope), patch.dict(os.environ, {
                        'GITHUB_EVENT_NAME': event, 'GITHUB_OUTPUT': str(output),
                        'GITHUB_ENV': str(env)}, clear=True), self.assertRaisesRegex(ValueError, 'forbidden'):
                    config.main(['--scope', scope])
                self.assertFalse(output.exists())
                self.assertFalse(env.exists())
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request'}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            config.main(['--scope', 'INFRA_PLAN'])
        result = json.loads(stdout.getvalue())
        self.assertEqual(result['INFRA_PLAN_ENABLED'], 'false')
        self.assertNotIn(self.cfg['factory']['operational_role_name'], result['AWS_ROLE_ARN'])

    def test_operational_arn_comes_only_from_versioned_field(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['factory']['operational_role_name'] = 'reviewed-external-role'
        self.load(cfg)
        with patch.object(config, 'configuration', return_value=cfg), patch.dict(os.environ, {
                'AWS_ROLE_ARN': 'wrong', 'FACTORY_OPERATIONAL_ROLE_NAME': 'wrong',
                'GITHUB_EVENT_NAME': 'push'}, clear=True), contextlib.redirect_stdout(io.StringIO()) as stdout:
            config.main(['--scope', 'DEV'])
        self.assertEqual(json.loads(stdout.getvalue())['AWS_ROLE_ARN'],
                         'arn:aws:iam::712107929769:role/reviewed-external-role')
        self.assertEqual(cfg['DEV']['role_name'], 'alric-image-base-factory-dev')
        self.assertEqual(config.settings(cfg, 'INFRA_APPLY')['AWS_ROLE_ARN'],
                         config.settings(cfg, 'DEV')['AWS_ROLE_ARN'])

    def test_protected_infra_plan_and_apply_share_operational_scope(self):
        doc = yaml.safe_load((config.ROOT / '.github/workflows/infra-apply.yml').read_text())
        self.assertEqual(doc['concurrency'], {'group': 'image-base-infra-state', 'cancel-in-progress': False})
        for name in ('plan', 'apply'):
            job = doc['jobs'][name]
            self.assertEqual(job['environment'], 'lab-image-base-infra')
            self.assertEqual(job['if'], "github.ref == 'refs/heads/develop'")
            loader = next(s for s in job['steps'] if s.get('id') == 'pipeline')
            self.assertIn('--scope INFRA_APPLY', loader['run'])
        pr = yaml.safe_load((config.ROOT / '.github/workflows/infra-pr.yml').read_text())
        self.assertEqual(pr['jobs']['checks']['permissions'], {'contents': 'read'})
        self.assertIn("needs.checks.outputs.infra_plan_enabled == 'true'", pr['jobs']['plan']['if'])

    def test_app_certification_sessions_remain_read_only(self):
        doc = yaml.safe_load((config.ROOT / '.github/workflows/app-certification.yml').read_text())
        expected = {'ecr:GetAuthorizationToken', 'ecr:DescribeImages', 'ecr:DescribeRepositories',
                    'ecr:BatchGetImage', 'ecr:GetDownloadUrlForLayer', 'ecr:BatchCheckLayerAvailability'}
        for name in ('inventory', 'applications'):
            job = doc['jobs'][name]
            self.assertEqual(job['environment'], 'DEV')
            action = next(s for s in job['steps'] if s.get('uses', '').startswith('aws-actions/configure-aws-credentials@'))
            policy = json.loads(action['with']['inline-session-policy'])
            self.assertEqual({a for s in policy['Statement'] for a in s['Action']}, expected)
            self.assertTrue(all(s['Effect'] == 'Allow' for s in policy['Statement']))
        self.assertIn("github.ref == 'refs/heads/develop'", doc['jobs']['inventory']['if'])
        self.assertIn("github.event_name == 'workflow_dispatch'", doc['jobs']['inventory']['if'])
        self.assertIn('inventory', doc['jobs']['applications']['needs'])

    def test_disabled_promotion_is_not_overridden_by_environment_variables(self):
        policy = dict(config.promotion_policy('HOM'), enabled=False)
        envfile = self.directory / 'env'
        outfile = self.directory / 'output'
        with patch.object(config, 'promotion_policy', return_value=policy), patch.dict(os.environ, {
                'STABLE_PROMOTION_AUTHORIZED': 'true', 'AWS_ACCOUNT_ID': '999999999999',
                'GITHUB_ENV': str(envfile), 'GITHUB_OUTPUT': str(outfile)}, clear=True):
            with self.assertRaisesRegex(ValueError, 'disabled'):
                config.main(['--scope', 'HOM', '--require-promotion'])
        self.assertFalse(envfile.exists())
        self.assertFalse(outfile.exists())

    def test_validated_json_overrides_conflicting_process_settings(self):
        envfile = self.directory / 'env'
        outfile = self.directory / 'output'
        with patch.dict(os.environ, {'AWS_REGION': 'wrong', 'AWS_ROLE_ARN': 'wrong',
                'GITHUB_ENV': str(envfile), 'GITHUB_OUTPUT': str(outfile)}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            config.main(['--scope', 'HOM'])
        self.assertEqual(envfile.read_text(), outfile.read_text())
        self.assertIn('AWS_REGION=sa-east-1\n', outfile.read_text())
        self.assertIn('AWS_ACCOUNT_ID=248908662184\n', outfile.read_text())
        self.assertNotIn('wrong', outfile.read_text())

    def test_missing_file_or_duplicate_keys_cannot_fall_back_to_vars(self):
        with self.assertRaises(OSError):
            config.configuration(self.directory / 'missing.json')
        path = self.directory / 'duplicate.json'
        path.write_text('{"promotion_authorized":false,"promotion_authorized":true}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            config.configuration(path)

    def test_invalid_destination_flags_and_soak_fail_closed(self):
        changes = [
            ('schema_version', True),
            ('branch', 'main'), ('subject_prefix', 'repo:other/repository'),
        ]
        for key, value in changes:
            cfg = copy.deepcopy(self.cfg)
            cfg[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.load(cfg)
        for key, value in [('account_id', '123'), ('region', 'sa-east-1\nAWS_ROLE_ARN=evil'),
                           ('role_name', 'role\nINJECTED=yes'), ('release_bucket', 'bucket/other')]:
            cfg = copy.deepcopy(self.cfg)
            cfg['HOM'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load(cfg)

    def test_account_and_permission_boundaries_cannot_collapse(self):
        for mutation in ('account', 'role', 'backend', 'plan_flag', 'unknown', 'missing'):
            cfg = copy.deepcopy(self.cfg)
            if mutation == 'account':
                cfg['HOM']['account_id'] = cfg['DEV']['account_id']
            elif mutation == 'role':
                cfg['infra']['apply_role_name'] = cfg['DEV']['role_name']
            elif mutation == 'backend':
                cfg['infra']['backend']['key'] = 'prefix/../state'
            elif mutation == 'plan_flag':
                cfg['infra']['plan_enabled'] = 'true'
            elif mutation == 'unknown':
                cfg['HOM']['role_arn'] = 'another-source-of-truth'
            else:
                del cfg['DEV']['region']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.load(cfg)

    def test_cli_rejects_wrong_repository_without_emitting_settings(self):
        outfile = self.directory / 'output'
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'other/repository',
                'GITHUB_OUTPUT': str(outfile)}, clear=True), self.assertRaisesRegex(ValueError, 'repository mismatch'):
            config.main(['--scope', 'DEV'])
        self.assertFalse(outfile.exists())

    def test_lifecycle_cli_blocks_disabled_promotion_before_orchestration(self):
        policy = dict(config.promotion_policy('HOM'), enabled=False)
        with patch.object(lifecycle, 'promotion_policy', return_value=policy), \
                patch.object(lifecycle, 'promote_hom') as promote, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(lifecycle.main(['promote-hom', '--reports', str(self.directory)]), 1)
        promote.assert_not_called()
        self.assertEqual(json.loads((self.directory / 'release-outcome.json').read_text())['status'], 'FAIL')

    def test_every_aws_workflow_loads_json_before_credentials_without_vars(self):
        for path in (config.ROOT / '.github/workflows').glob('*.yml'):
            content = path.read_text()
            self.assertNotIn('vars.', content, path.name)
            workflow = yaml.safe_load(content)
            for name, job in workflow['jobs'].items():
                steps = job.get('steps', [])
                for index, step in enumerate(steps):
                    if step.get('uses', '').startswith('aws-actions/configure-aws-credentials@'):
                        with self.subTest(workflow=path.name, job=name):
                            if path.name == 'factory-central-role-preflight.yml':
                                # Stage A tests an independently pinned identity before
                                # the operational resolver cutover. No vars/secrets source.
                                self.assertEqual(set(workflow['jobs']), {'dev', 'infra'})
                                self.assertEqual(step['with']['role-to-assume'],
                                                 'arn:aws:iam::712107929769:role/itau-github-repo-factory-distroless-v1')
                                self.assertEqual(step['with']['aws-region'], 'us-east-1')
                                self.assertEqual(step['with']['allowed-account-ids'], '712107929769')
                                continue
                            loaders = [s for s in steps[:index] if s.get('id') == 'pipeline']
                            self.assertEqual(len(loaders), 1)
                            self.assertIn('scripts.pipeline.governance.configuration --scope ', loaders[0]['run'])
                            for key, output in [('role-to-assume', 'AWS_ROLE_ARN'), ('aws-region', 'AWS_REGION'),
                                                ('allowed-account-ids', 'AWS_ACCOUNT_ID')]:
                                self.assertEqual(step['with'][key], '${{ steps.pipeline.outputs.' + output + ' }}')

    def test_disabled_promotion_is_checked_without_oidc_then_rechecked_before_hom(self):
        workflow = yaml.safe_load((config.ROOT / '.github/workflows/promote-stable.yml').read_text())
        read = workflow['jobs']['config']
        promote = workflow['jobs']['promote']
        self.assertEqual(read['permissions'], {'contents': 'read'})
        self.assertNotIn('environment', read)
        self.assertEqual(promote['needs'], 'config')
        self.assertIn("needs.config.outputs.promotion_authorized == 'true'", promote['if'])
        loader = next(s for s in promote['steps'] if s.get('id') == 'pipeline')
        self.assertIn('--require-promotion', loader['run'])
        execution = next(s for s in promote['steps'] if s.get('name') == 'Promote exact eligible release to HOM')
        self.assertEqual(execution['env']['SOAK_HOURS'],
                         '${{ inputs.soak-hours || steps.pipeline.outputs.MINIMUM_SOAK_HOURS }}')

    def test_lifecycle_default_soak_tracks_json_without_cli_override(self):
        policy = dict(config.promotion_policy('HOM'), enabled=True, soak_hours=12)
        with patch.object(lifecycle, 'promotion_policy', return_value=policy), patch.object(lifecycle, 'promote_hom') as promote:
            self.assertEqual(lifecycle.main(['promote-hom']), 0)
        self.assertEqual(promote.call_args.args[0].soak_hours, 12)

    def test_promotion_files_have_independent_defaults_and_frameworks(self):
        dev, hom = config.promotion_policy('DEV'), config.promotion_policy('HOM')
        self.assertEqual(dev['frameworks'], ['go1-26', 'go1-26-dev'])
        self.assertEqual(hom['frameworks'], dev['frameworks'])
        self.assertEqual((dev['soak_hours'], hom['soak_hours']), (0, 6))
        self.assertEqual((dev['enabled'], hom['enabled']), (True, False))
        self.assertNotIn('minimum_soak_hours', self.cfg)
        self.assertNotIn('promotion_authorized', self.cfg)

    def test_invalid_promotion_policies_cannot_authorize_partial_pairs_or_bad_soak(self):
        path = self.directory / 'promotion.json'
        for environment in ('DEV', 'HOM'):
            changes = [('enabled', 'true'), ('soak_hours', True), ('soak_hours', -1),
                       ('soak_hours', float('nan')), ('soak_hours', float('inf')),
                       ('frameworks', []), ('frameworks', ['go1-26']),
                       ('frameworks', ['nodejs22-dev']), ('frameworks', ['not-in-catalog']),
                       ('frameworks', ['go1-26', 'go1-26-dev', 'go1-26'])]
            if environment == 'HOM':
                changes += [('soak_hours', 0), ('soak_hours', 5.99)]
            for key, value in changes:
                policy = dict(config.promotion_policy(environment))
                policy[key] = value
                path.write_text(json.dumps(policy))
                with self.subTest(environment=environment, key=key, value=value), self.assertRaises(ValueError):
                    config.promotion_policy(environment, path)
        with self.assertRaises(OSError):
            config.promotion_policy('DEV', self.directory / 'missing.json')
        path.write_text('{"enabled":false,"enabled":true}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            config.promotion_policy('HOM', path)

    def test_dev_promotion_schedule_shares_lock_and_consumes_exact_validated_candidates(self):
        workflow = yaml.safe_load((config.ROOT / '.github/workflows/dev-stable.yml').read_text())
        jobs = workflow['jobs']
        self.assertEqual(jobs['config']['permissions'], {'contents': 'read'})
        self.assertEqual(jobs['promote']['concurrency'], jobs['approve']['concurrency'])
        self.assertEqual(jobs['promote']['environment'], 'DEV')
        self.assertIn('inputs.frameworks !=', jobs['approve']['if'])
        self.assertIn('inputs.frameworks ==', jobs['config']['if'])
        commands = '\n'.join(s.get('run', '') for s in jobs['promote']['steps'])
        self.assertIn('lifecycle promote-dev', commands)
        self.assertNotIn('build_image', commands)


if __name__ == '__main__':
    unittest.main()
