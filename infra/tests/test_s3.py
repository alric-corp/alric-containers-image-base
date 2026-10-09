"""Shared-root, strict plan, collision and read-back probes; never contact AWS."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from infra.ecr import verify_state
from infra.s3 import readback
from infra.s3.contract import bucket_policy, ADDRESSES, SNAPSHOTS_PREFIX, RESULTS_PREFIX
from infra.tests.test_ecr_plan import valid_plan, verify, verifier, ACCOUNT, REGION, BUCKET, ROOT
from infra.tests.test_workflows import load_workflow, shell, step_index
from scripts.pipeline.analytics.ingestion_types import Destination


def s3_change(plan, kind):
    return next(c for c in plan['resource_changes'] if c['type'] == kind)


def outputs():
    config = dict(protocol_version=1, destination=dict(bucket=BUCKET, prefix='sbom-analytics/poc-v1',
                  region=REGION, expected_bucket_owner=ACCOUNT))
    return {k: {'value': v} for k, v in dict(bucket_name=BUCKET, bucket_arn=f'arn:aws:s3:::{BUCKET}',
        bucket_region=REGION, expected_bucket_owner=ACCOUNT, snapshots_prefix=SNAPSHOTS_PREFIX,
        query_results_prefix=RESULTS_PREFIX, ingestion_config=config, bucket_tags=verifier.PROVENANCE).items()}


class PlanTests(unittest.TestCase):
    def reject_after(self, kind, field, value):
        p = valid_plan()
        s3_change(p, kind)['change']['after'][field] = value
        with self.assertRaises(verifier.PlanError):
            verify(p)

    def test_unknown_computed_bucket_id_requires_the_exact_dependency(self):
        p = valid_plan()
        kind = 'aws_s3_bucket_versioning'
        c = s3_change(p, kind)['change']
        c['after'].pop('bucket'); c['after_unknown'] = {'bucket': True}
        values = p['planned_values']['root_module']['child_modules'][-1]['resources']
        next(r for r in values if r['type'] == kind)['values'].pop('bucket')
        verify(p)
        cfg = p['configuration']['root_module']['module_calls']['sbom']['module']['resources']
        next(r for r in cfg if r['address'] == kind + '.sbom')['expressions']['bucket']['references'] = ['aws_s3_bucket.other.id']
        with self.assertRaisesRegex(verifier.PlanError, 'dependency'):
            verify(p)

    def test_missing_unknown_marker_is_not_proof(self):
        self.reject_after('aws_s3_bucket_versioning', 'bucket', None)

    def test_unknown_security_value_rejected_even_if_a_value_is_present(self):
        p = valid_plan()
        s3_change(p, 'aws_s3_bucket_public_access_block')['change']['after_unknown'] = {'block_public_acls': True}
        with self.assertRaisesRegex(verifier.PlanError, 'unknown'):
            verify(p)

    def test_computed_kms_response_requires_explicit_empty_key_and_known_aes_input(self):
        p = valid_plan(); kind = 'aws_s3_bucket_server_side_encryption_configuration'
        c = s3_change(p, kind)['change']
        c['after_unknown'] = {'rule': [{'apply_server_side_encryption_by_default': [{'kms_master_key_id': True}], 'blocked_encryption_types': True}]}
        cfg = next(r for r in p['configuration']['root_module']['module_calls']['sbom']['module']['resources'] if r['address'] == kind + '.sbom')
        with self.assertRaisesRegex(verifier.PlanError, 'empty configuration'):
            verify(p)
        cfg['expressions']['rule'] = [{'apply_server_side_encryption_by_default': [{'kms_master_key_id': {'constant_value': ''}, 'sse_algorithm': {'constant_value': 'AES256'}}]}]
        verify(p)
        cfg['expressions']['rule'][0]['apply_server_side_encryption_by_default'][0]['kms_master_key_id']['constant_value'] = 'untrusted-key'
        with self.assertRaises(verifier.PlanError):
            verify(p)

    def test_default_owner_acl_grant_does_not_mean_acl_authority_is_enabled(self):
        p = valid_plan('no-op')
        c = s3_change(p, 'aws_s3_bucket')['change']
        c['before']['grant'] = c['after']['grant'] = [{'permissions': ['FULL_CONTROL'], 'type': 'CanonicalUser', 'id': 'owner'}]
        verify(p, mode='noop')
        cfg = next(r for r in p['configuration']['root_module']['module_calls']['sbom']['module']['resources'] if r['address'] == 'aws_s3_bucket.sbom')
        cfg['expressions']['grant'] = {'constant_value': c['after']['grant']}
        with self.assertRaisesRegex(verifier.PlanError, 'forbidden S3 grant'):
            verify(p)

    def test_all_four_public_blocks_and_boolean_types_are_required(self):
        for key in ('block_public_acls', 'ignore_public_acls', 'block_public_policy', 'restrict_public_buckets'):
            for value in (False, None, 1, 'true'):
                with self.subTest(key=key, value=value):
                    self.reject_after('aws_s3_bucket_public_access_block', key, value)

    def test_ownership_acl_enforcement_cannot_be_relaxed(self):
        self.reject_after('aws_s3_bucket_ownership_controls', 'rule', [{'object_ownership': 'ObjectWriter'}])

    def test_force_destroy_object_lock_and_tags_rejected(self):
        for key, value in (('force_destroy', True), ('force_destroy', 0), ('object_lock_enabled', True),
                           ('tags', {}), ('acl', 'public-read'), ('lifecycle_rule', [{'enabled': True}])):
            with self.subTest(key=key):
                self.reject_after('aws_s3_bucket', key, value)

    def test_versioning_and_owner_must_match(self):
        for key, value in (('versioning_configuration', [{'status': 'Suspended'}]), ('expected_bucket_owner', '999999999999')):
            self.reject_after('aws_s3_bucket_versioning', key, value)

    def test_sse_s3_and_no_kms_are_required(self):
        for value in ([{'apply_server_side_encryption_by_default': [{'sse_algorithm': 'aws:kms'}]}],
                      [{'apply_server_side_encryption_by_default': [{'sse_algorithm': 'AES256', 'kms_master_key_id': 'key'}]}], []):
            self.reject_after('aws_s3_bucket_server_side_encryption_configuration', 'rule', value)

    def test_noop_cannot_disguise_a_changed_resource(self):
        p = valid_plan('no-op')
        s3_change(p, 'aws_s3_bucket')['change']['before']['tags'] = {}
        with self.assertRaisesRegex(verifier.PlanError, 'before and after'):
            verify(p, mode='noop')

    def test_noop_requires_all_six_resources_in_prior_state(self):
        p = valid_plan('no-op')
        p['prior_state']['values']['root_module']['child_modules'].pop()
        with self.assertRaisesRegex(verifier.PlanError, 'prior state'):
            verify(p, mode='noop')

    def test_s3_update_delete_replacement_import_and_move_rejected(self):
        for kind in ADDRESSES.values():
            for actions in (['update'], ['delete'], ['delete', 'create'], ['create', 'delete']):
                with self.subTest(kind=kind, actions=actions):
                    p = valid_plan(); s3_change(p, kind)['change']['actions'] = actions
                    with self.assertRaises(verifier.PlanError):
                        verify(p)
        for field in ('previous_address', 'importing'):
            p = valid_plan(); item = s3_change(p, 'aws_s3_bucket')
            (item if field == 'previous_address' else item['change'])[field] = 'existing'
            with self.assertRaises(verifier.PlanError):
                verify(p)

    def test_wrong_bucket_region_and_root_source_are_rejected(self):
        self.reject_after('aws_s3_bucket', 'bucket', 'unrelated-bucket')
        self.reject_after('aws_s3_bucket', 'region', 'us-east-2')
        p = valid_plan(); p['configuration']['root_module']['module_calls']['sbom']['source'] = '../sbom-analytics'
        with self.assertRaisesRegex(verifier.PlanError, 'root/module source'):
            verify(p)

    def test_existing_ecr_module_pin_cannot_change(self):
        p = valid_plan()
        p['configuration']['root_module']['module_calls']['ecr']['version_constraint'] = 'latest'
        with self.assertRaisesRegex(verifier.PlanError, 'source/version'):
            verify(p)

    def test_external_account_and_region_are_independent_of_plan_variables(self):
        for name, value in (('aws_region', 'us-east-2'), ('expected_bucket_owner', '999999999999')):
            p = valid_plan(); p['variables'][name]['value'] = value
            with self.assertRaisesRegex(verifier.PlanError, 'external identity'):
                verify(p)

    def test_extra_acl_resource_and_wrong_s3_address_rejected(self):
        for address in ('module.sbom.aws_s3_bucket_acl.sbom', 'module.other.aws_s3_bucket.sbom'):
            p = valid_plan(); s3_change(p, 'aws_s3_bucket')['address'] = address
            with self.assertRaisesRegex(verifier.PlanError, 'graph mismatch'):
                verify(p)

    def test_policy_cannot_grant_access_widen_prefix_or_omit_tls(self):
        for mutate in (lambda d: d['Statement'].pop(0),
                       lambda d: d['Statement'][1].update(Resource=f'arn:aws:s3:::{BUCKET}/*'),
                       lambda d: d['Statement'][1].update(Effect='Allow'),
                       lambda d: d['Statement'][1]['Condition'].pop('Bool')):
            p = valid_plan(); doc = bucket_policy(BUCKET); mutate(doc)
            s3_change(p, 'aws_s3_bucket_policy')['change']['after']['policy'] = json.dumps(doc)
            with self.assertRaisesRegex(verifier.PlanError, 'policy differs'):
                verify(p)

    def test_policy_duplicate_keys_and_unknown_policy_rejected(self):
        for value in (None, '{"Version":"2012-10-17","Version":"other"}'):
            self.reject_after('aws_s3_bucket_policy', 'policy', value)

    def test_policy_must_follow_all_four_security_controls(self):
        p = valid_plan()
        cfg = p['configuration']['root_module']['module_calls']['sbom']['module']['resources']
        next(r for r in cfg if r['address'] == 'aws_s3_bucket_policy.sbom')['depends_on'].pop()
        with self.assertRaisesRegex(verifier.PlanError, 'all four'):
            verify(p)

    def test_results_prefix_has_no_conditional_statement(self):
        doc = bucket_policy(BUCKET)
        self.assertTrue(all(s['Effect'] == 'Deny' for s in doc['Statement']))
        conditional = doc['Statement'][1:]
        self.assertTrue(all(s['Resource'] == f'arn:aws:s3:::{BUCKET}/{SNAPSHOTS_PREFIX}*' for s in conditional))
        self.assertNotIn(RESULTS_PREFIX, json.dumps(conditional))


class StructureTests(unittest.TestCase):
    def test_child_is_local_and_has_no_backend_provider_credentials_or_lockfile(self):
        child = ROOT / 'infra/s3'
        text = '\n'.join(p.read_text() for p in child.glob('*.tf'))
        self.assertNotRegex(text, r'backend\s+"|provider\s+"aws"|access_key\s*=|secret_key\s*=|profile\s*=')
        self.assertFalse((child / '.terraform.lock.hcl').exists())
        self.assertIn('source                = "../s3"', (ROOT / 'infra/ecr/s3.tf').read_text())
        self.assertNotIn('712107929769', text)
        self.assertNotIn('us-east-1', text)

    def test_destroy_safeguard_and_no_accessory_resources(self):
        text = (ROOT / 'infra/s3/main.tf').read_text()
        self.assertRegex(text, r'prevent_destroy\s*=\s*true')
        import re
        self.assertEqual(set(re.findall(r'resource "([^"]+)"', text)), set(ADDRESSES.values()))

    def test_same_gate_modes_state_and_preflight_protect_both_workflows(self):
        for name in ('infra-pr.yml', 'infra-apply.yml'):
            wf = load_workflow(name)
            for job in wf['jobs'].values():
                s = shell(job)
                if 'configure-aws-credentials' not in str(job):
                    continue
                self.assertIn('verify_state.py', s)
                self.assertIn('--mode sbom-adoption --account-id "$AWS_ACCOUNT_ID" --region "$AWS_REGION"', s)
                self.assertNotIn('--allow-noop', s)
                self.assertIn('infra/s3/readback.py preflight', s)
                self.assertNotIn('-target', s)
                self.assertNotIn('-lock=false', s)
                upload = next(st['with']['path'] for st in job['steps'] if st.get('uses', '').startswith('actions/upload-artifact'))
                self.assertNotIn('infra-selected-state.json', upload)

    def test_credential_free_ci_exercises_native_root_and_child(self):
        job = load_workflow('infra-pr.yml')['jobs']['checks']
        self.assertIn('terraform -chdir=infra/ecr validate', shell(job))
        self.assertIn('terraform -chdir=infra/ecr test', shell(job))
        self.assertNotIn('id-token', job['permissions'])

    def test_ingestion_output_is_consumable_without_changing_adapter(self):
        cfg = outputs()['ingestion_config']['value']
        d = Destination(**cfg['destination'])
        self.assertEqual(d.snapshot_prefix('a' * 64), SNAPSHOTS_PREFIX + 'a' * 64 + '/')
        self.assertEqual(cfg['protocol_version'], 1)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {'backend': {'type': 's3', 'config': dict(bucket='existing-state', key='existing/key', region='us-east-2', encrypt=True, use_lockfile=True)}}
        self.state = valid_plan()['prior_state']
        self.args = dict(bucket='existing-state', key='existing/key', region='us-east-2', workspace='default', root=ROOT / 'infra/ecr')

    def test_existing_state_and_addresses_are_preserved(self):
        result = verify_state.verify(self.metadata, self.state, **self.args)
        self.assertEqual(result['ecr_managed_count'], 48)
        self.assertEqual(result['s3_managed_count'], 0)

    def test_backend_key_workspace_root_and_locking_changes_rejected(self):
        for key, value in (('bucket', 'other'), ('key', 'other'), ('region', 'us-east-1'), ('encrypt', False), ('use_lockfile', False)):
            m = copy.deepcopy(self.metadata); m['backend']['config'][key] = value
            with self.assertRaises(ValueError):
                verify_state.verify(m, self.state, **self.args)
        for key, value in (('workspace', 'other'), ('root', ROOT / 'infra/s3')):
            with self.assertRaises(ValueError):
                verify_state.verify(self.metadata, self.state, **{**self.args, key: value})

    def test_missing_existing_and_unexpected_state_addresses_rejected(self):
        for mutate in (lambda s: s['values']['root_module']['child_modules'].pop(),
                       lambda s: s['values']['root_module']['child_modules'][0]['resources'][0].update(address='aws_s3_bucket.backend')):
            state = copy.deepcopy(self.state); mutate(state)
            with self.assertRaises(ValueError):
                verify_state.verify(self.metadata, state, **self.args)


class FakeAws:
    def __init__(self):
        self.calls = []
        self.responses = {
            'get-caller-identity': {'Account': ACCOUNT}, 'head-bucket': {},
            'get-bucket-location': {'LocationConstraint': None},
            'get-public-access-block': {'PublicAccessBlockConfiguration': readback.PUBLIC_ACCESS_BLOCK},
            'get-bucket-ownership-controls': {'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]}},
            'get-bucket-encryption': {'ServerSideEncryptionConfiguration': {'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}},
            'get-bucket-versioning': {'Status': 'Enabled'}, 'get-bucket-policy': {'Policy': json.dumps(bucket_policy(BUCKET))},
            'get-bucket-tagging': {'TagSet': [{'Key': k, 'Value': v} for k,v in verifier.PROVENANCE.items()]},
        }
        self.errors = {'get-bucket-lifecycle-configuration': 'NoSuchLifecycleConfiguration', 'get-object-lock-configuration': 'ObjectLockConfigurationNotFoundError'}

    def call(self, service, operation, **parameters):
        self.calls.append((service, operation, parameters))
        if service == 's3api':
            assert parameters['expected_bucket_owner'] == ACCOUNT
            assert parameters['bucket'] == BUCKET
        if operation in self.errors:
            raise readback.AwsError(self.errors[operation], 'simulated error')
        return copy.deepcopy(self.responses[operation])


class ReadbackTests(unittest.TestCase):
    def test_all_controls_are_observed_and_null_is_us_east_1(self):
        f = FakeAws(); r = readback.readback(outputs(), ACCOUNT, REGION, aws=f)
        self.assertEqual(r['status'], 'BUCKET_CONFIGURATION_VERIFIED')
        self.assertEqual(len(r['checks']), 10)
        self.assertEqual(r['object_operations'], 'NOT_PROVEN')
        self.assertTrue(all(op.startswith(('get-', 'head-')) for _,op,_ in f.calls))

    def test_unsafe_control_retains_prior_checks_and_reports_failure(self):
        f = FakeAws(); f.responses['get-bucket-versioning'] = {'Status': 'Suspended'}
        r = readback.readback(outputs(), ACCOUNT, REGION, aws=f)
        self.assertEqual(r['status'], 'FAIL')
        self.assertEqual(len(r['checks']), 10)
        self.assertEqual(next(c for c in r['checks'] if c['check'] == 'versioning')['result'], 'FAIL')

    def test_wrong_region_policy_tags_encryption_and_ownership_rejected(self):
        for operation, response in (
            ('get-bucket-location', {'LocationConstraint': 'us-east-2'}),
            ('get-bucket-policy', {'Policy': '{}'}), ('get-bucket-tagging', {'TagSet': []}),
            ('get-bucket-encryption', {'ServerSideEncryptionConfiguration': {'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'aws:kms'}}]}}),
            ('get-bucket-ownership-controls', {'OwnershipControls': {'Rules': [{'ObjectOwnership': 'ObjectWriter'}]}})):
            f = FakeAws(); f.responses[operation] = response
            self.assertEqual(readback.readback(outputs(), ACCOUNT, REGION, aws=f)['status'], 'FAIL')

    def test_access_denied_is_not_absence_of_lifecycle_or_object_lock(self):
        f = FakeAws(); f.errors['get-bucket-lifecycle-configuration'] = 'AccessDenied'
        self.assertEqual(readback.readback(outputs(), ACCOUNT, REGION, aws=f)['status'], 'FAIL')

    def test_false_or_missing_region_cannot_be_normalized_to_us_east_1(self):
        for value in ({'LocationConstraint': False}, {}):
            f = FakeAws(); f.responses['get-bucket-location'] = value
            self.assertEqual(readback.readback(outputs(), ACCOUNT, REGION, aws=f)['status'], 'FAIL')

    def test_actual_lifecycle_or_object_lock_is_outside_contract(self):
        for op in ('get-bucket-lifecycle-configuration', 'get-object-lock-configuration'):
            f = FakeAws(); f.errors.pop(op); f.responses[op] = {'Enabled': True}
            self.assertEqual(readback.readback(outputs(), ACCOUNT, REGION, aws=f)['status'], 'FAIL')

    def test_wrong_external_account_stops_before_any_s3_call(self):
        f = FakeAws(); f.responses['get-caller-identity']['Account'] = '999999999999'
        with self.assertRaises(readback.BackendError):
            readback.readback(outputs(), ACCOUNT, REGION, aws=f)
        self.assertEqual(len(f.calls), 1)

    def test_invalid_output_does_not_contact_aws(self):
        f = FakeAws(); o = outputs(); o['ingestion_config']['value']['destination']['prefix'] = 'query-results/poc-v1'
        with self.assertRaises(readback.BackendError):
            readback.readback(o, ACCOUNT, REGION, aws=f)
        self.assertEqual(f.calls, [])

    def test_absent_create_bucket_is_only_observed_not_created(self):
        f = FakeAws(); f.errors['head-bucket'] = '404'
        r = readback.preflight(valid_plan(), ACCOUNT, REGION, aws=f)
        self.assertEqual(r['bucket_state'], 'ABSENT_AT_PREFLIGHT')
        self.assertEqual(len(f.calls), 2)

    def test_existing_name_and_denied_probe_cannot_authorize_creation(self):
        f = FakeAws()
        with self.assertRaises(readback.BackendError) as e:
            readback.preflight(valid_plan(), ACCOUNT, REGION, aws=f)
        self.assertEqual(e.exception.code, 'BUCKET_NAME_COLLISION')
        f.errors['head-bucket'] = '403'
        with self.assertRaises(readback.BackendError) as e:
            readback.preflight(valid_plan(), ACCOUNT, REGION, aws=f)
        self.assertEqual(e.exception.code, '403')

    def test_managed_bucket_cannot_be_recreated_when_absent(self):
        f = FakeAws(); f.errors['head-bucket'] = '404'
        with self.assertRaises(readback.BackendError) as e:
            readback.preflight(valid_plan('no-op'), ACCOUNT, REGION, aws=f)
        self.assertEqual(e.exception.code, 'MANAGED_BUCKET_MISSING')

    def test_noop_managed_bucket_is_read_only(self):
        r = readback.preflight(valid_plan('no-op'), ACCOUNT, REGION, aws=FakeAws())
        self.assertEqual(r['bucket_state'], 'ALREADY_MANAGED')

    def test_failure_json_is_written_before_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); (p/'outputs.json').write_text(json.dumps(outputs()))
            f = FakeAws(); f.errors['get-bucket-versioning'] = 'AccessDenied'
            with patch.object(readback, 'AwsCli', return_value=f), redirect_stdout(io.StringIO()):
                code = readback.main(['readback', '--outputs', str(p/'outputs.json'), '--account-id', ACCOUNT, '--region', REGION, '--report', str(p/'report.json')])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads((p/'report.json').read_text())['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
