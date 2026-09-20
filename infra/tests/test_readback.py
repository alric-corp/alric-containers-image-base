"""ECR readback proof from mock AWS responses; no credentials or network."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from infra import readback


ACCOUNT = '123456789012'
REGION = 'us-east-1'


class FakeAws:
    def __init__(self):
        self.account = ACCOUNT
        self.calls = []
        self.frameworks = readback.catalog(readback.ROOT.parent / 'frameworks')
        self.repositories = [self.repository(f'image-base-{framework}')
                             for framework in self.frameworks]
        self.lifecycle = json.loads((readback.POLICIES / 'ecr-lifecycle-7-days.json').read_text())
        self.policy = json.loads((readback.POLICIES / 'ecr-repository-org-pull.json').read_text())
        self.tags = [{'Key': key, 'Value': value} for key, value in readback.PROVENANCE.items()]
        self.images = []
        self.failures = {}
        self.overrides = {}

    @staticmethod
    def repository(name):
        return {
            'repositoryName': name, 'registryId': ACCOUNT,
            'repositoryArn': f'arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{name}',
            'imageTagMutability': 'IMMUTABLE_WITH_EXCLUSION',
            'imageTagMutabilityExclusionFilters': [{'filter': 'stable', 'filterType': 'WILDCARD'}],
            'imageScanningConfiguration': {'scanOnPush': True},
            'encryptionConfiguration': {'encryptionType': 'AES256'},
        }

    def call(self, service, operation, **parameters):
        self.calls.append((service, operation, parameters))
        if operation in self.failures:
            raise readback.BackendError(self.failures[operation], 'Mock AWS error')
        if operation in self.overrides:
            return copy.deepcopy(self.overrides[operation])
        if service == 'sts':
            assert operation == 'get-caller-identity'
            return {'Account': self.account}
        assert service == 'ecr'
        if operation != 'list-tags-for-resource':
            assert parameters['registry_id'] == ACCOUNT
        if operation == 'describe-repositories':
            return {'repositories': copy.deepcopy(self.repositories)}
        if operation == 'list-tags-for-resource':
            assert parameters['resource_arn'].startswith(f'arn:aws:ecr:{REGION}:{ACCOUNT}:repository/image-base-')
            return {'tags': copy.deepcopy(self.tags)}
        assert parameters['repository_name'] in {f'image-base-{name}' for name in self.frameworks}
        if operation == 'get-lifecycle-policy':
            return {'lifecyclePolicyText': json.dumps(self.lifecycle)}
        if operation == 'get-repository-policy':
            return {'policyText': json.dumps(self.policy)}
        assert operation == 'describe-images'
        return {'imageDetails': copy.deepcopy(self.images)}


class ReadbackTests(unittest.TestCase):
    def verify(self, fake, **kwargs):
        return readback.verify_readback(ACCOUNT, REGION, aws=fake, **kwargs)

    def assert_rejected(self, fake, code, **kwargs):
        with self.assertRaises(readback.BackendError) as caught:
            self.verify(fake, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_exact_catalog_produces_read_only_empty_repository_proof(self):
        fake = FakeAws()
        proof = self.verify(fake, expect_empty=True)
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual(proof['catalog_count'], len(fake.frameworks))
        self.assertEqual(proof['aws_repository_count'], len(fake.frameworks))
        self.assertTrue(proof['catalog_sets_identical'])
        self.assertEqual(proof['total_image_count'], 0)
        self.assertEqual(len(proof['repositories']), len(fake.frameworks))
        self.assertEqual(len(fake.calls), 2 + 4 * len(fake.frameworks))
        self.assertTrue(all(operation.startswith(('get-', 'describe-', 'list-'))
                            for _, operation, _ in fake.calls))

    def test_unrelated_repository_is_only_listed(self):
        fake = FakeAws()
        fake.repositories.append({'repositoryName': 'unrelated-product'})
        proof = self.verify(fake)
        self.assertEqual(proof['unrelated_repository_count'], 1)
        self.assertFalse(any(parameters.get('repository_name') == 'unrelated-product'
                             for _, _, parameters in fake.calls))

    def test_wrong_account_stops_before_any_ecr_call(self):
        fake = FakeAws()
        fake.account = '999999999999'
        self.assert_rejected(fake, 'ACCOUNT_MISMATCH')
        self.assertEqual(len(fake.calls), 1)

    def test_missing_extra_and_duplicate_catalog_entries_are_rejected(self):
        for change, code in (
            (lambda entries: entries.pop(), 'CATALOG_MISMATCH'),
            (lambda entries: entries.append(FakeAws.repository('image-base-unexpected')), 'CATALOG_MISMATCH'),
            (lambda entries: entries.append(copy.deepcopy(entries[0])), 'DUPLICATE_REPOSITORY'),
        ):
            with self.subTest(code=code):
                fake = FakeAws()
                change(fake.repositories)
                self.assert_rejected(fake, code)
                self.assertEqual(len(fake.calls), 2)

    def test_incomplete_lists_and_malformed_responses_fail_closed(self):
        for operation, response, code in (
            ('describe-repositories', {'repositories': [], 'nextToken': 'more'}, 'INCOMPLETE_LIST'),
            ('describe-repositories', {}, 'INVALID_AWS_RESPONSE'),
            ('describe-images', {'imageDetails': [], 'NextToken': 'more'}, 'INCOMPLETE_LIST'),
            ('describe-images', {'imageDetails': None}, 'INVALID_AWS_RESPONSE'),
            ('get-lifecycle-policy', {'lifecyclePolicyText': 'broken'}, 'INVALID_POLICY'),
            ('get-repository-policy', {'policyText': '[]'}, 'INVALID_POLICY'),
        ):
            with self.subTest(operation=operation, response=response):
                fake = FakeAws()
                fake.overrides[operation] = response
                self.assert_rejected(fake, code)

    def test_wrong_repository_account_region_or_arn_is_rejected(self):
        for key, value in (
            ('registryId', '999999999999'),
            ('repositoryArn', f'arn:aws:ecr:us-east-2:{ACCOUNT}:repository/image-base-dotnet10'),
            ('repositoryArn', 'arn:aws:ecr:us-east-1:999999999999:repository/image-base-dotnet10'),
        ):
            fake = FakeAws()
            fake.repositories[0][key] = value
            self.assert_rejected(fake, 'REPOSITORY_IDENTITY_MISMATCH')

    def test_mutability_stable_scan_and_encryption_are_checked(self):
        for key, value in (
            ('imageTagMutability', 'MUTABLE'),
            ('imageTagMutabilityExclusionFilters', [{'filter': '*', 'filterType': 'WILDCARD'}]),
            ('imageTagMutabilityExclusionFilters', []),
            ('imageScanningConfiguration', {'scanOnPush': False}),
            ('encryptionConfiguration', {'encryptionType': 'KMS', 'kmsKey': 'unexpected'}),
        ):
            with self.subTest(key=key, value=value):
                fake = FakeAws()
                fake.repositories[0][key] = value
                self.assert_rejected(fake, 'REPOSITORY_CONTRACT_MISMATCH')

    def test_policy_order_and_iam_scalar_set_equivalents_are_accepted(self):
        fake = FakeAws()
        fake.lifecycle['rules'].reverse()
        statement = fake.policy['Statement'][0]
        statement['Action'].reverse()
        statement['Principal']['AWS'] = ['*']
        statement['Condition']['StringEquals']['aws:PrincipalOrgID'] = 'o-5gqr9v3h2q'
        fake.policy['Statement'] = statement
        self.assertEqual(self.verify(fake)['status'], 'PASS')

    def test_policy_permission_or_condition_widening_is_rejected(self):
        for change in (
            lambda statement: statement['Action'].append('ecr:PutImage'),
            lambda statement: statement.pop('Condition'),
            lambda statement: statement['Condition']['StringEquals'].update({'aws:PrincipalOrgID': ['o-other']}),
        ):
            fake = FakeAws()
            change(fake.policy['Statement'][0])
            self.assert_rejected(fake, 'REPOSITORY_POLICY_MISMATCH')

    def test_lifecycle_changed_retention_or_invalid_structure_is_rejected(self):
        fake = FakeAws()
        fake.lifecycle['rules'][1]['selection']['countNumber'] = 1
        self.assert_rejected(fake, 'LIFECYCLE_MISMATCH')
        fake = FakeAws()
        fake.lifecycle['rules'][0]['selection']['tagPatternList'] = 'stable'
        self.assert_rejected(fake, 'LIFECYCLE_MISMATCH')

    def test_legacy_source_missing_owner_and_duplicate_tags_are_rejected(self):
        for tags, code in (
            ([{'Key': 'Source', 'Value': 'alric-containers-registry'}], 'PROVENANCE_MISMATCH'),
            ([{'Key': 'Source', 'Value': readback.PROVENANCE['Source']}], 'PROVENANCE_MISMATCH'),
            ([{'Key': 'Source', 'Value': 'one'}, {'Key': 'Source', 'Value': 'two'}], 'INVALID_TAGS'),
        ):
            fake = FakeAws()
            fake.tags = tags
            self.assert_rejected(fake, code)

    def test_images_are_counted_and_optional_empty_guard_rejects_them(self):
        fake = FakeAws()
        fake.images = [{'imageDigest': 'sha256:example', 'imageTags': ['stable']}]
        proof = self.verify(fake)
        self.assertEqual(proof['total_image_count'], len(fake.frameworks))
        self.assert_rejected(fake, 'REPOSITORY_NOT_EMPTY', expect_empty=True)

    def test_aws_read_error_is_not_interpreted_as_empty(self):
        fake = FakeAws()
        fake.failures['describe-images'] = 'AccessDeniedException'
        self.assert_rejected(fake, 'AccessDeniedException', expect_empty=True)

    def test_invalid_cli_inputs_do_not_contact_aws(self):
        fake = FakeAws()
        for account, region in (('invalid', REGION), (ACCOUNT, '')):
            with self.assertRaises(readback.BackendError):
                readback.verify_readback(account, region, aws=fake)
        self.assertEqual(fake.calls, [])

    def test_cli_returns_json_proof_and_nonzero_json_failure(self):
        output = io.StringIO()
        with patch.object(readback, 'AwsCli', return_value=FakeAws()), redirect_stdout(output):
            self.assertEqual(readback.main(['--account-id', ACCOUNT, '--region', REGION,
                                            '--expect-empty']), 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'PASS')
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(readback.main(['--account-id', 'invalid', '--region', REGION]), 1)
        self.assertEqual(json.loads(output.getvalue())['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
