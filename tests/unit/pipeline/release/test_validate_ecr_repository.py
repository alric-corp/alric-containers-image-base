"""Tests for the fail-closed Infra-owned ECR repository preflight.

RFC-013/ADR-0005: the accepted contract is exactly `IMMUTABLE_WITH_EXCLUSION`
with exactly one exclusion filter, `{filterType: WILDCARD, filter: stable}`.
"""

import copy
import unittest

from scripts.pipeline.release.validate_ecr_repository import validate_repository


ACCOUNT = '123456789012'
REGION = 'us-east-1'
NAME = 'image-base-go1-26'
STABLE_EXCLUSION = {'filterType': 'WILDCARD', 'filter': 'stable'}


def descriptor():
    return {'repositories': [{
        'repositoryName': NAME,
        'repositoryArn': f'arn:aws:ecr:{REGION}:{ACCOUNT}:repository/{NAME}',
        'repositoryUri': f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{NAME}',
        'imageTagMutability': 'IMMUTABLE_WITH_EXCLUSION',
        'imageTagMutabilityExclusionFilters': [dict(STABLE_EXCLUSION)],
        'imageScanningConfiguration': {'scanOnPush': True},
        'encryptionConfiguration': {'encryptionType': 'AES256'},
    }]}


class ValidateEcrRepositoryTests(unittest.TestCase):
    def assert_rejected(self, document, message=None):
        with self.assertRaisesRegex(ValueError, message or '.+'):
            validate_repository(document, NAME, ACCOUNT, REGION)

    def test_preprovisioned_immutable_with_stable_exclusion_passes(self):
        result = validate_repository(descriptor(), NAME, ACCOUNT, REGION)
        self.assertEqual(result['repositoryName'], NAME)
        self.assertEqual(result['imageTagMutability'], 'IMMUTABLE_WITH_EXCLUSION')
        self.assertEqual(result['imageTagMutabilityExclusionFilters'], [STABLE_EXCLUSION])
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

    # Seção 4 do realinhamento RFC-013: exemplos que devem falhar, um a um.

    def test_mutable_repository_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutability'] = 'MUTABLE'
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = []
        self.assert_rejected(document, 'must be IMMUTABLE_WITH_EXCLUSION')

    def test_plain_immutable_without_exclusion_fails(self):
        # O contrato anterior (P0-04) -- agora insuficiente por si só.
        document = descriptor()
        document['repositories'][0]['imageTagMutability'] = 'IMMUTABLE'
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = []
        self.assert_rejected(document, 'must be IMMUTABLE_WITH_EXCLUSION')

    def test_immutable_with_exclusion_but_no_filters_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = []
        self.assert_rejected(document, 'exactly')

    def test_immutable_with_exclusion_but_latest_instead_of_stable_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = [
            {'filterType': 'WILDCARD', 'filter': 'latest'}]
        self.assert_rejected(document, 'exactly')

    def test_immutable_with_exclusion_stable_plus_another_filter_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = [
            dict(STABLE_EXCLUSION), {'filterType': 'WILDCARD', 'filter': 'latest'}]
        self.assert_rejected(document, 'exactly')

    def test_wildcard_star_exclusion_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = [
            {'filterType': 'WILDCARD', 'filter': '*'}]
        self.assert_rejected(document, 'exactly')

    def test_build_prefix_exclusion_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = [
            {'filterType': 'WILDCARD', 'filter': 'build*'}]
        self.assert_rejected(document, 'exactly')

    def test_different_filter_type_for_stable_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = [
            {'filterType': 'EXACT', 'filter': 'stable'}]
        self.assert_rejected(document, 'exactly')

    def test_extra_key_in_exclusion_object_fails(self):
        document = descriptor()
        document['repositories'][0]['imageTagMutabilityExclusionFilters'] = [
            {'filterType': 'WILDCARD', 'filter': 'stable', 'extra': 'x'}]
        self.assert_rejected(document, 'exactly')

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
