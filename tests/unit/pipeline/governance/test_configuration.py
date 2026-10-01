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
            'DEV': ('712107929769', 'us-east-1', 'alric-image-base-factory-dev'),
            'HOM': ('248908662184', 'sa-east-1', 'alric-image-base-factory-hom'),
            'INFRA_PLAN': ('712107929769', 'us-east-1', 'alric-github-repo-1360616627-infra-plan'),
            'INFRA_APPLY': ('712107929769', 'us-east-1', 'alric-github-repo-1360616627-infra-apply'),
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

    def test_disabled_promotion_is_not_overridden_by_environment_variables(self):
        self.cfg['promotion_authorized'] = False
        envfile = self.directory / 'env'
        outfile = self.directory / 'output'
        with patch.object(config, 'configuration', return_value=self.cfg), patch.dict(os.environ, {
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
            ('promotion_authorized', 'false'), ('promotion_authorized', 1),
            ('schema_version', True), ('minimum_soak_hours', 5),
            ('minimum_soak_hours', float('nan')), ('minimum_soak_hours', float('inf')),
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
        cfg = copy.deepcopy(self.cfg)
        cfg['promotion_authorized'] = False
        with patch.object(lifecycle, 'configuration', return_value=cfg), \
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
        cfg = copy.deepcopy(self.cfg)
        cfg.update(promotion_authorized=True, minimum_soak_hours=12)
        with patch.object(lifecycle, 'configuration', return_value=cfg), patch.object(lifecycle, 'promote_hom') as promote:
            self.assertEqual(lifecycle.main(['promote-hom']), 0)
        self.assertEqual(promote.call_args.args[0].soak_hours, 12)


if __name__ == '__main__':
    unittest.main()
