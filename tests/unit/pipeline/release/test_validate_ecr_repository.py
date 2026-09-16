"""Tests for the fail-closed Infra-owned ECR repository preflight."""

import copy
import unittest

from scripts.pipeline.release.validate_ecr_repository import validate_repository


ACCOUNT = '123456789012'
REGION = 'us-east-1'
NAME = 'image-base-go1-26'


def descriptor():
    return {'repositories': [{
        'repositoryName': NAME,
        'repositoryArn': f'arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{NAME}',
        'repositoryUri': f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{NAME}',
        'imageTagMutability': 'IMMUTABLE',
        'imageScanningConfiguration': {'scanOnPush': True},
        'encryptionConfiguration': {'encryptionType': 'AES256'},
    }]}


class ValidateEcrRepositoryTests(unittest.TestCase):
    def assert_rejected(self, document, message=None):
        with self.assertRaisesRegex(ValueError, message or '.+'):
            validate_repository(document, NAME, ACCOUNT, REGION)

    def test_preprovisioned_immutable_repository_passes(self):
        result = validate_repository(descriptor(), NAME, ACCOUNT, REGION)
        self.assertEqual(result['repositoryName'], NAME)
        self.assertEqual(result['imageTagMutability'], 'IMMUTABLE')
        self.assertEqual(result['imageTagMutabilityExclusionFilters'], [])
        self.assertTrue(result['scanOnPush'])
        self.assertEqual(result['encryptionType'], 'AES256')

    def test_missing_repository_fails(self):
        self.assert_rejected({'repositories': []}, 'exactly one')

    def test_wrong_repository_name_fails(self):
        document = descriptor()
        document['repositories'][0]['repositoryName'] = 'image-base-go1-25'
        self.assert_rejected(document, 'repositoryName')

    def test_account_or_arn_mismatch_fails(self):
        for field, value in (
                ('repositoryArn', f'arn:aws:ecr:{REGION}:999999999999:repository/{NAME}'),
                ('repositoryUri', f'999999999999.dkr.ecr.{REGION}.amazonaws.com/{NAME}')):
            with self.subTest(field=field):
                document = descriptor()
                document['repositories'][0][field] = value
                self.assert_rejected(document, field)

    def test_region_mismatch_fails(self):
        for field, value in (
                ('repositoryArn', f'arn:aws:ecr:eu-west-1:{ACCOUNT}:repository/{NAME}'),
                ('repositoryUri', f'{ACCOUNT}.dkr.ecr.eu-west-1.amazonaws.com/{NAME}')):
            with self.subTest(field=field):
                document = descriptor()
                document['repositories'][0][field] = value
                self.assert_rejected(document, field)

    def test_mutable_repository_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutability'] = 'MUTABLE'
        self.assert_rejected(document, 'must be IMMUTABLE')

    def test_historical_stable_exclusion_drift_fails(self):
        document = descriptor()
        repository = document['repositories'][0]
        repository['imageTagMutability'] = 'IMMUTABLE_WITH_EXCLUSION'
        repository['imageTagMutabilityExclusionFilters'] = [
            {'filterType': 'WILDCARD', 'filter': 'stable'}]
        self.assert_rejected(document, 'must be IMMUTABLE')

    def test_immutable_repository_with_exclusion_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = [
            {'filterType': 'WILDCARD', 'filter': 'stable'}]
        self.assert_rejected(document, 'exclusions are forbidden')

    def test_scan_on_push_false_fails(self):
        document = descriptor()
        document['repositories'][0]['imageScanningConfiguration']['scanOnPush'] = False
        self.assert_rejected(document, 'scanOnPush must be true')

    def test_non_aes256_encryption_fails(self):
        document = descriptor()
        document['repositories'][0]['encryptionConfiguration'] = {
            'encryptionType': 'KMS', 'kmsKey': 'alias/example'}
        self.assert_rejected(document, 'must be AES256')

    def test_empty_response_fails(self):
        self.assert_rejected({}, 'repositories list')

    def test_malformed_response_fails(self):
        for document in (None, [], {'repositories': 'invalid'},
                         {'repositories': [None]}):
            with self.subTest(document=document):
                self.assert_rejected(document)

    def test_multiple_repositories_fail(self):
        document = descriptor()
        document['repositories'].append(copy.deepcopy(document['repositories'][0]))
        self.assert_rejected(document, 'exactly one')


if __name__ == '__main__':
    unittest.main()
