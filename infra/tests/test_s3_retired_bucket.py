"""The bucket replaced by Distroless SBOM Analytics stays retired.

It was destroyed by the approved removal apply (Infra - Apply run 38319342150,
2026-10-12). Offline Terraform JSON only: no module, address, state entry or
bucket name of that bucket is accepted again, and the analytics bucket and the
shared infrastructure keep their boundaries.
"""
import copy
import re
import unittest

from infra.ecr import verify_state
from infra.s3.contract import RESOURCE_TYPES, retired_bucket_name
from infra.tests.test_ecr_plan import valid_plan, verify, verifier, ACCOUNT, REGION, ROOT

RETIRED = retired_bucket_name(ACCOUNT, REGION)
OLD_ADDRESSES = {f'module.sbom.{kind}.sbom': kind for kind in RESOURCE_TYPES}


def change(plan, address):
    return next(c for c in plan['resource_changes'] if c['address'] == address)['change']


def old_resource(address, kind, values=None):
    return {'address': address, 'mode': 'managed', 'type': kind, 'provider_name': verifier.PROVIDER,
            'values': copy.deepcopy(values or {'bucket': RETIRED, 'region': REGION})}


class RetiredBucketTests(unittest.TestCase):
    def test_only_the_active_graph_is_accepted(self):
        result = verify(valid_plan('no-op'), mode='noop')
        self.assertEqual(result['phase'], 'steady')
        self.assertEqual(result['actions'], {'no-op': 54})
        self.assertNotIn('legacy_bucket_name', result)

    def test_reintroduced_old_module_is_rejected_whatever_its_source(self):
        for source in ('../s3-legacy', '../s3', '../s3-retired'):
            plan = valid_plan('no-op')
            plan['configuration']['root_module']['module_calls']['sbom'] = {'source': source, 'module': {'resources': []}}
            with self.subTest(source=source), self.assertRaisesRegex(verifier.PlanError, 'root/module source'):
                verify(plan)

    def test_old_addresses_are_rejected_for_every_action(self):
        for address, kind in OLD_ADDRESSES.items():
            for actions in (['create'], ['no-op'], ['update'], ['delete'], ['forget'], ['delete', 'create']):
                plan = valid_plan('no-op')
                plan['resource_changes'].append({**old_resource(address, kind), 'change': {
                    'actions': actions, 'before': {'bucket': RETIRED}, 'after': None}})
                with self.subTest(address=address, actions=actions), \
                        self.assertRaisesRegex(verifier.PlanError, 'graph mismatch'):
                    verify(plan)

    def test_old_addresses_in_prior_state_block_the_plan(self):
        plan = valid_plan('no-op')
        plan['prior_state']['values']['root_module']['child_modules'].append(
            {'address': 'module.sbom', 'resources': [old_resource(a, k) for a, k in OLD_ADDRESSES.items()]})
        with self.assertRaisesRegex(verifier.PlanError, 'no unexpected resources'):
            verify(plan, mode='noop')

    def test_retired_name_is_never_the_analytics_bucket(self):
        with self.assertRaisesRegex(verifier.PlanError, 'exact analytics bucket name'):
            verify(valid_plan('create'), bucket_name=RETIRED)


class RetiredStateAndSourceTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {'backend': {'type': 's3', 'config': dict(bucket='existing-state', key='existing/key',
                                                                  region='us-east-2', encrypt=True, use_lockfile=True)}}
        self.args = dict(bucket='existing-state', key='existing/key', region='us-east-2', workspace='default',
                         root=ROOT / 'infra/ecr')

    def test_state_with_old_addresses_is_rejected(self):
        state = valid_plan('no-op')['prior_state']
        result = verify_state.verify(self.metadata, state, **self.args)
        self.assertEqual(result['s3_managed_count'], 6)
        self.assertNotIn('legacy_s3_managed_count', result)
        state['values']['root_module']['child_modules'].append(
            {'address': 'module.sbom', 'resources': [old_resource(a, k) for a, k in OLD_ADDRESSES.items()]})
        with self.assertRaisesRegex(ValueError, 'unexpected managed address'):
            verify_state.verify(self.metadata, state, **self.args)

    def test_root_declares_only_the_active_bucket(self):
        active = (ROOT / 'infra/s3/main.tf').read_text()
        self.assertRegex(active, r'force_destroy\s*=\s*false')
        self.assertRegex(active, r'prevent_destroy\s*=\s*true')
        self.assertFalse((ROOT / 'infra/s3-legacy').exists())
        root = ''.join(path.read_text() for path in sorted((ROOT / 'infra/ecr').glob('*.tf')))
        tests = ''.join(path.read_text() for path in sorted((ROOT / 'infra/ecr/tests').glob('*.hcl')))
        self.assertEqual(set(re.findall(r'^module "([^"]+)"', root, re.M)), {'ecr', 'sbom_analytics'})
        for text in (root, tests):
            self.assertNotIn('s3-legacy', text)
            self.assertNotIn('alric-distroless-sbom-', text)
            self.assertNotIn('poc-v1', text)
            self.assertNotRegex(text, r'module\.sbom\b(?!_)')
        self.assertIn('module "sbom_analytics" {\n  source                = "../s3"\n'
                      '  bucket_name           = var.sbom_bucket_name\n', root)


class SharedInfrastructureTests(unittest.TestCase):
    """Only the analytics bucket may be created; shared identity never enters the plan."""

    PHASES = {
        'adoption': lambda: valid_plan('create'),
        'steady': lambda: valid_plan('no-op'),
    }
    SHARED = (
        ('aws_iam_role', 'aws_iam_role.central'),
        ('aws_iam_role_policy', 'aws_iam_role_policy.factory_distroless_v1'),
        ('aws_iam_openid_connect_provider', 'aws_iam_openid_connect_provider.github'),
        ('aws_s3_bucket', 'aws_s3_bucket.terraform_state'),
        ('aws_s3_object', 'aws_s3_object.terraform_state_lock'),
        ('aws_s3_bucket', 'module.sbom_analytics.aws_s3_bucket.state'),
        ('aws_ecr_repository', 'aws_ecr_repository.unmanaged'),
    )

    def test_iam_oidc_state_and_unknown_resources_are_rejected_in_every_phase(self):
        for phase, build in self.PHASES.items():
            self.assertEqual(verify(build())['phase'], 'steady')
            for kind, address in self.SHARED:
                for action in (['create'], ['update'], ['delete'], ['no-op'], ['delete', 'create']):
                    plan = build()
                    plan['resource_changes'].append({'address': address, 'mode': 'managed', 'type': kind,
                                                     'provider_name': verifier.PROVIDER,
                                                     'change': {'actions': action, 'before': {}, 'after': {}}})
                    with self.subTest(phase=phase, address=address, action=action), \
                            self.assertRaisesRegex(verifier.PlanError, 'graph mismatch'):
                        verify(plan)

    def test_shared_resources_in_prior_state_block_every_phase(self):
        for phase, build in self.PHASES.items():
            for kind, address in self.SHARED[:5]:
                plan = build()
                plan['prior_state']['values']['root_module'].setdefault('resources', []).append(
                    {'address': address, 'mode': 'managed', 'type': kind, 'provider_name': verifier.PROVIDER,
                     'values': {}})
                with self.subTest(phase=phase, address=address), self.assertRaises(verifier.PlanError):
                    verify(plan)

    def test_every_ecr_change_is_rejected_in_every_phase(self):
        for phase, build in self.PHASES.items():
            ecr = [c['address'] for c in build()['resource_changes'] if c['address'].startswith('module.ecr[')]
            self.assertTrue(ecr)
            for address in (ecr[0], ecr[1], ecr[2]):
                for action in (['update'], ['delete'], ['create'], ['delete', 'create'], ['create', 'delete']):
                    plan = build()
                    change(plan, address)['actions'] = action
                    with self.subTest(phase=phase, address=address, action=action), \
                            self.assertRaisesRegex(verifier.PlanError, 'disallowed actions'):
                        verify(plan)
            plan = build()
            change(plan, ecr[0])['after'] = dict(change(plan, ecr[0])['after'] or {}, image_tag_mutability='MUTABLE')
            with self.subTest(phase=phase, drift='no-op with different values'), self.assertRaises(verifier.PlanError):
                verify(plan)

    def test_backend_variables_and_module_sources_cannot_be_redirected(self):
        for phase, build in self.PHASES.items():
            for name, value in (('aws_region', 'us-east-2'), ('expected_bucket_owner', '999999999999'),
                                ('sbom_bucket_name', '712107929769-alric-containers-image-base-tfstate')):
                plan = build(); plan['variables'][name] = {'value': value}
                with self.subTest(phase=phase, variable=name), self.assertRaisesRegex(verifier.PlanError, 'external identity'):
                    verify(plan)
            for module, source in (('ecr', '../ecr-fork'), ('sbom_analytics', '../s3-legacy'), ('iam', '../iam')):
                plan = build()
                calls = plan['configuration']['root_module']['module_calls']
                if module in calls:
                    calls[module]['source'] = source
                else:
                    calls[module] = {'source': source, 'module': {'resources': []}}
                with self.subTest(phase=phase, module=module), self.assertRaises(verifier.PlanError):
                    verify(plan)


if __name__ == '__main__':
    unittest.main()
