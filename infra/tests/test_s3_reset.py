"""Replacement of the POC analytics bucket: transition, removal and their limits.

Offline Terraform JSON only. The phase is derived from the reviewed
configuration and prior state; there is no flag that widens the boundary.
"""
import copy
import json
import re
import unittest

from infra.ecr import verify_state
from infra.s3.contract import (LEGACY_ADDRESSES, LEGACY_SNAPSHOTS_PREFIX, bucket_policy, legacy_bucket_name)
from infra.tests.test_ecr_plan import valid_plan, verify, verifier, ACCOUNT, REGION, BUCKET, ROOT

LEGACY = legacy_bucket_name(ACCOUNT, REGION)


def legacy_values(force_destroy):
    values = {
        'aws_s3_bucket': {'bucket': LEGACY, 'force_destroy': force_destroy, 'object_lock_enabled': False,
                          'tags': dict(verifier.PROVENANCE)},
        'aws_s3_bucket_public_access_block': {'block_public_acls': True, 'ignore_public_acls': True,
                                              'block_public_policy': True, 'restrict_public_buckets': True},
        'aws_s3_bucket_ownership_controls': {'rule': [{'object_ownership': 'BucketOwnerEnforced'}]},
        'aws_s3_bucket_versioning': {'versioning_configuration': [{'status': 'Enabled'}], 'expected_bucket_owner': ACCOUNT},
        'aws_s3_bucket_server_side_encryption_configuration': {
            'rule': [{'apply_server_side_encryption_by_default': [{'sse_algorithm': 'AES256'}]}],
            'expected_bucket_owner': ACCOUNT},
        'aws_s3_bucket_policy': {'policy': json.dumps(bucket_policy(LEGACY, LEGACY_SNAPSHOTS_PREFIX))},
    }
    for kind, item in values.items():
        item.update(region=REGION, bucket=LEGACY)
    return values


def legacy_resource(kind):
    address = next(a for a, k in LEGACY_ADDRESSES.items() if k == kind)
    return {'address': address, 'mode': 'managed', 'type': kind, 'provider_name': verifier.PROVIDER}


def transition_plan(new_action='create', applied=False):
    """First revision: new bucket created, the old one only gains force_destroy."""
    plan = valid_plan(new_action)
    before, after = legacy_values(applied), legacy_values(True)
    configuration, planned, prior = [], [], []
    for kind in before:
        resource = legacy_resource(kind)
        action = 'update' if kind == 'aws_s3_bucket' and not applied else 'no-op'
        plan['resource_changes'].append({**resource, 'change': {
            'actions': [action], 'before': copy.deepcopy(before[kind]), 'after': copy.deepcopy(after[kind])}})
        planned.append({**resource, 'values': copy.deepcopy(after[kind])})
        prior.append({**resource, 'values': copy.deepcopy(before[kind])})
        config = {'address': kind + '.sbom', 'mode': 'managed',
                  'expressions': {'bucket': {'references': ['aws_s3_bucket.sbom.id', 'aws_s3_bucket.sbom']}}}
        if kind == 'aws_s3_bucket_policy':
            config['depends_on'] = [k + '.sbom' for k in before if k not in ('aws_s3_bucket', 'aws_s3_bucket_policy')]
        configuration.append(config)
    plan['configuration']['root_module']['module_calls']['sbom'] = {
        'source': '../s3-legacy', 'module': {'resources': configuration}}
    plan['planned_values']['root_module']['child_modules'].append({'address': 'module.sbom', 'resources': planned})
    plan['prior_state']['values']['root_module']['child_modules'].append({'address': 'module.sbom', 'resources': prior})
    return plan


def removal_plan():
    """Second revision: the legacy block is gone; exactly its six addresses are deleted."""
    plan = valid_plan('no-op')
    prior = []
    for kind, values in legacy_values(True).items():
        resource = legacy_resource(kind)
        plan['resource_changes'].append({**resource, 'change': {
            'actions': ['delete'], 'before': copy.deepcopy(values), 'after': None}})
        prior.append({**resource, 'values': copy.deepcopy(values)})
    plan['prior_state']['values']['root_module']['child_modules'].append({'address': 'module.sbom', 'resources': prior})
    return plan


def change(plan, address):
    return next(c for c in plan['resource_changes'] if c['address'] == address)['change']


LEGACY_BUCKET = next(a for a, k in LEGACY_ADDRESSES.items() if k == 'aws_s3_bucket')
LEGACY_POLICY = next(a for a, k in LEGACY_ADDRESSES.items() if k == 'aws_s3_bucket_policy')


class TransitionTests(unittest.TestCase):
    def test_new_bucket_created_and_old_bucket_only_gains_force_destroy(self):
        result = verify(transition_plan())
        self.assertEqual(result['phase'], 'transition')
        self.assertEqual(result['actions'], {'no-op': 53, 'create': 6, 'update': 1})
        self.assertEqual((result['bucket_name'], result['legacy_bucket_name']), (BUCKET, LEGACY))

    def test_applied_transition_is_a_zero_drift_noop(self):
        result = verify(transition_plan('no-op', applied=True), mode='noop')
        self.assertEqual(result['actions'], {'no-op': 60})
        with self.assertRaisesRegex(verifier.PlanError, 'disallowed actions'):
            verify(transition_plan('no-op'), mode='noop')

    def test_any_other_change_to_the_old_bucket_is_rejected(self):
        for field, value in (('tags', {}), ('bucket', 'other-bucket'), ('object_lock_enabled', True)):
            with self.subTest(field=field):
                plan = transition_plan()
                change(plan, LEGACY_BUCKET)['after'][field] = value
                with self.assertRaises(verifier.PlanError):
                    verify(plan)

    def test_old_bucket_cannot_lose_protection_controls_or_be_deleted_early(self):
        for address in LEGACY_ADDRESSES:
            for actions in (['delete'], ['delete', 'create'], ['create', 'delete'], ['create']):
                with self.subTest(address=address, actions=actions):
                    plan = transition_plan(); change(plan, address)['actions'] = actions
                    with self.assertRaisesRegex(verifier.PlanError, 'disallowed actions'):
                        verify(plan)
        plan = transition_plan(); change(plan, LEGACY_POLICY)['actions'] = ['update']
        with self.assertRaisesRegex(verifier.PlanError, 'disallowed actions'):
            verify(plan)

    def test_old_policy_and_identity_must_match_their_contract(self):
        plan = transition_plan()
        item = change(plan, LEGACY_POLICY)
        item['after']['policy'] = item['before']['policy'] = json.dumps(bucket_policy(LEGACY))
        with self.assertRaisesRegex(verifier.PlanError, 'policy differs'):
            verify(plan)
        plan = transition_plan()
        for c in plan['resource_changes']:
            if c['address'] in LEGACY_ADDRESSES:
                c['change']['before']['bucket'] = 'someone-elses-bucket'
        with self.assertRaisesRegex(verifier.PlanError, 'exact identity'):
            verify(plan)

    def test_old_bucket_is_never_created_or_adopted(self):
        plan = transition_plan()
        plan['prior_state']['values']['root_module']['child_modules'].pop()
        with self.assertRaisesRegex(verifier.PlanError, 'never created or adopted'):
            verify(plan)

    def test_legacy_source_and_new_bucket_name_are_fixed(self):
        plan = transition_plan()
        plan['configuration']['root_module']['module_calls']['sbom']['source'] = '../s3'
        with self.assertRaisesRegex(verifier.PlanError, 'root/module source'):
            verify(plan)
        with self.assertRaisesRegex(verifier.PlanError, 'invalid expected bucket name'):
            verify(transition_plan(), bucket_name=LEGACY)

    def test_ecr_and_unrelated_resources_still_block_the_transition(self):
        plan = transition_plan(); plan['resource_changes'][0]['change']['actions'] = ['delete']
        with self.assertRaisesRegex(verifier.PlanError, 'disallowed actions'):
            verify(plan)
        plan = transition_plan()
        plan['resource_changes'].append({'address': 'module.sbom.aws_s3_bucket_lifecycle_configuration.sbom',
                                         'mode': 'managed', 'type': 'aws_s3_bucket_lifecycle_configuration',
                                         'change': {'actions': ['create']}})
        with self.assertRaisesRegex(verifier.PlanError, 'graph mismatch'):
            verify(plan)


class RemovalTests(unittest.TestCase):
    def test_exactly_the_six_old_addresses_are_deleted(self):
        result = verify(removal_plan())
        self.assertEqual(result['phase'], 'removal')
        self.assertEqual(result['actions'], {'no-op': 54, 'delete': 6})

    def test_removal_requires_the_applied_force_destroy(self):
        plan = removal_plan(); change(plan, LEGACY_BUCKET)['before']['force_destroy'] = False
        with self.assertRaisesRegex(verifier.PlanError, 'transitional force_destroy'):
            verify(plan)

    def test_noop_mode_cannot_leave_or_remove_the_old_bucket(self):
        with self.assertRaisesRegex(verifier.PlanError, 'cannot remove'):
            verify(removal_plan(), mode='noop')

    def test_partial_removal_new_bucket_deletion_and_kept_values_rejected(self):
        plan = removal_plan(); change(plan, LEGACY_POLICY)['actions'] = ['no-op']
        with self.assertRaisesRegex(verifier.PlanError, 'disallowed actions'):
            verify(plan)
        plan = removal_plan()
        plan['resource_changes'] = [c for c in plan['resource_changes'] if c['address'] != LEGACY_POLICY]
        with self.assertRaisesRegex(verifier.PlanError, 'graph mismatch'):
            verify(plan)
        plan = removal_plan()
        new_bucket = next(c for c in plan['resource_changes'] if c['address'] == 'module.sbom_analytics.aws_s3_bucket.sbom')
        new_bucket['change']['actions'] = ['delete']
        with self.assertRaisesRegex(verifier.PlanError, 'disallowed actions'):
            verify(plan)
        plan = removal_plan(); change(plan, LEGACY_BUCKET)['after'] = change(plan, LEGACY_BUCKET)['before']
        with self.assertRaisesRegex(verifier.PlanError, 'planned values'):
            verify(plan)

    def test_removal_cannot_target_another_bucket_or_policy(self):
        plan = removal_plan()
        for c in plan['resource_changes']:
            if c['address'] in LEGACY_ADDRESSES:
                c['change']['before']['bucket'] = '712107929769-alric-containers-image-base-tfstate'
        with self.assertRaisesRegex(verifier.PlanError, 'exact identity'):
            verify(plan)
        plan = removal_plan(); change(plan, LEGACY_POLICY)['before']['policy'] = '{}'
        with self.assertRaisesRegex(verifier.PlanError, 'policy differs'):
            verify(plan)


class StateAndSourceTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {'backend': {'type': 's3', 'config': dict(bucket='existing-state', key='existing/key',
                                                                  region='us-east-2', encrypt=True, use_lockfile=True)}}
        self.args = dict(bucket='existing-state', key='existing/key', region='us-east-2', workspace='default',
                         root=ROOT / 'infra/ecr')

    def test_state_may_hold_the_old_bucket_addresses_only(self):
        state = transition_plan('no-op', applied=True)['prior_state']
        result = verify_state.verify(self.metadata, state, **self.args)
        self.assertEqual((result['s3_managed_count'], result['legacy_s3_managed_count']), (6, 6))
        state['values']['root_module']['child_modules'][-1]['resources'][0]['address'] = 'module.sbom.aws_s3_bucket.other'
        with self.assertRaises(ValueError):
            verify_state.verify(self.metadata, state, **self.args)

    def test_only_the_transitional_module_enables_destruction(self):
        active = (ROOT / 'infra/s3/main.tf').read_text()
        self.assertRegex(active, r'force_destroy\s*=\s*false')
        self.assertRegex(active, r'prevent_destroy\s*=\s*true')
        legacy = (ROOT / 'infra/s3-legacy/main.tf').read_text()
        self.assertRegex(legacy, r'force_destroy\s*=\s*true')
        self.assertIn('"sbom-analytics/poc-v1/snapshots/"', legacy)
        root = (ROOT / 'infra/ecr/s3.tf').read_text()
        self.assertEqual(root.count('"../s3-legacy"'), 1)
        self.assertIn('module "sbom" {\n  source                = "../s3-legacy"\n'
                      '  bucket_name           = "alric-distroless-sbom-${var.expected_bucket_owner}-${var.aws_region}"', root)
        self.assertEqual(set(re.findall(r'resource "([^"]+)"', legacy)), set(LEGACY_ADDRESSES.values()))


if __name__ == '__main__':
    unittest.main()
