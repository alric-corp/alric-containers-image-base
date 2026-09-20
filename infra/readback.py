#!/usr/bin/env python3
"""Read AWS ECR back against the versioned product Infra contract.

This command only reads AWS. The CLI automatically paginates repository and
image listings; an exposed continuation token is rejected as incomplete proof.
Unrelated repository names are counted but never inspected beyond that listing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

if __package__:
    from .backend import AwsCli, BackendError
    from .ecr.verify_plan import PROVENANCE, catalog
else:
    from backend import AwsCli, BackendError
    from ecr.verify_plan import PROVENANCE, catalog


ROOT = Path(__file__).resolve().parent
POLICIES = ROOT / 'ecr' / 'policies'


class ReadbackError(BackendError):
    """The AWS response does not prove the checked-out Infra contract."""


def semantic_policy(value: Any, iam: bool = False, path: tuple = ()) -> Any:
    """Canonicalize unordered policy lists and IAM scalar/set equivalents.

IAM permits a scalar or an array for actions, resources, principal types and
condition values. Lifecycle structure stays strict; its rulePriority controls
evaluation, so the physical order of its rules carries no additional meaning.
    """
    scalar_or_set = iam and path and path[-1] != '[]' and (
        path[-1] in {'Action', 'NotAction', 'Resource', 'NotResource', 'Statement'}
        or len(path) >= 2 and path[-2] in {'Principal', 'NotPrincipal'}
        or 'Condition' in path and len(path) - path.index('Condition') >= 3
    )
    if scalar_or_set and not isinstance(value, list):
        value = [value]
    if isinstance(value, dict):
        return {key: semantic_policy(item, iam, path + (key,))
                for key, item in sorted(value.items())}
    if isinstance(value, list):
        # Mark a list element so scalar normalization is not repeated forever.
        normalized = [semantic_policy(item, iam, path + ('[]',)) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def policy_document(response: dict, key: str, label: str) -> dict:
    try:
        document = json.loads(response[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReadbackError('INVALID_POLICY', f'{label}: missing or invalid policy JSON') from exc
    if not isinstance(document, dict):
        raise ReadbackError('INVALID_POLICY', f'{label}: policy must be a JSON object')
    return document


def complete_list(response: dict, key: str, label: str) -> list:
    if response.get('nextToken') or response.get('NextToken'):
        raise ReadbackError('INCOMPLETE_LIST', f'{label}: pagination did not complete')
    values = response.get(key)
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        raise ReadbackError('INVALID_AWS_RESPONSE', f'{label}: expected a complete {key} list')
    return values


def verify_readback(account_id: str, region: str, *, expect_empty: bool = False,
                    frameworks_dir: Path = ROOT.parent / 'frameworks',
                    aws: AwsCli | None = None) -> dict:
    if not re.fullmatch(r'[0-9]{12}', account_id):
        raise ReadbackError('INVALID_ACCOUNT', 'Expected account ID must contain exactly 12 digits')
    if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-[0-9]+', region):
        raise ReadbackError('INVALID_REGION', 'An explicit AWS region is required')
    frameworks = catalog(frameworks_dir)
    expected = {f'image-base-{framework}' for framework in frameworks}
    lifecycle_expected = json.loads((POLICIES / 'ecr-lifecycle-7-days.json').read_text())
    repository_expected = json.loads((POLICIES / 'ecr-repository-org-pull.json').read_text())
    aws = aws or AwsCli(region)
    if aws.call('sts', 'get-caller-identity').get('Account') != account_id:
        raise ReadbackError('ACCOUNT_MISMATCH', 'AWS caller does not belong to the expected LAB account')
    listing = complete_list(aws.call('ecr', 'describe-repositories', registry_id=account_id),
                            'repositories', 'ECR repositories')
    repositories = {}
    for repository in listing:
        name = repository.get('repositoryName')
        if not isinstance(name, str):
            raise ReadbackError('INVALID_AWS_RESPONSE', 'ECR repository name is missing')
        if name.startswith('image-base-'):
            if name in repositories:
                raise ReadbackError('DUPLICATE_REPOSITORY', f'Duplicate repository: {name}')
            repositories[name] = repository
    if set(repositories) != expected:
        missing, extra = sorted(expected - set(repositories)), sorted(set(repositories) - expected)
        raise ReadbackError('CATALOG_MISMATCH', f'ECR catalog differs: missing={missing}, extra={extra}')
    proof = []
    for name, repository in sorted(repositories.items()):
        arn = repository.get('repositoryArn', '')
        if (repository.get('registryId') != account_id or not isinstance(arn, str)
                or not re.fullmatch(
                    rf'arn:aws(?:-us-gov|-cn)?:ecr:{re.escape(region)}:{account_id}:repository/{re.escape(name)}',
                    arn)):
            raise ReadbackError('REPOSITORY_IDENTITY_MISMATCH', f'{name}: incorrect account, region or ARN')
        required = {
            'imageTagMutability': 'IMMUTABLE_WITH_EXCLUSION',
            'imageTagMutabilityExclusionFilters': [{'filter': 'stable', 'filterType': 'WILDCARD'}],
            'imageScanningConfiguration': {'scanOnPush': True},
            'encryptionConfiguration': {'encryptionType': 'AES256'},
        }
        for key, value in required.items():
            if repository.get(key) != value:
                raise ReadbackError('REPOSITORY_CONTRACT_MISMATCH', f'{name}: unexpected {key}')
        target = {'registry_id': account_id, 'repository_name': name}
        lifecycle = policy_document(aws.call('ecr', 'get-lifecycle-policy', **target),
                                    'lifecyclePolicyText', name)
        policy = policy_document(aws.call('ecr', 'get-repository-policy', **target),
                                 'policyText', name)
        if semantic_policy(lifecycle) != semantic_policy(lifecycle_expected):
            raise ReadbackError('LIFECYCLE_MISMATCH', f'{name}: lifecycle differs from the versioned contract')
        if semantic_policy(policy, iam=True) != semantic_policy(repository_expected, iam=True):
            raise ReadbackError('REPOSITORY_POLICY_MISMATCH', f'{name}: repository policy differs from the versioned contract')
        tag_list = complete_list(aws.call('ecr', 'list-tags-for-resource', resource_arn=arn),
                                 'tags', name)
        tags = {}
        for tag in tag_list:
            key, value = tag.get('Key'), tag.get('Value')
            if not isinstance(key, str) or not isinstance(value, str) or key in tags:
                raise ReadbackError('INVALID_TAGS', f'{name}: duplicate or invalid resource tags')
            tags[key] = value
        if any(tags.get(key) != value for key, value in PROVENANCE.items()):
            raise ReadbackError('PROVENANCE_MISMATCH', f'{name}: incorrect Terraform ownership or Source tag')
        images = complete_list(aws.call('ecr', 'describe-images', **target), 'imageDetails', name)
        if expect_empty and images:
            raise ReadbackError('REPOSITORY_NOT_EMPTY', f'{name}: expected no images, found {len(images)}')
        proof.append({
            'name': name, 'arn': arn, **required, 'tags': tags,
            'lifecycle_policy': lifecycle, 'repository_policy': policy,
            'image_count': len(images), 'terraform_contract_match': True,
        })
    return {
        'status': 'PASS', 'account_id': account_id, 'region': region,
        'catalog': frameworks, 'catalog_count': len(frameworks),
        'aws_repository_count': len(repositories), 'catalog_sets_identical': True,
        'unrelated_repository_count': len(listing) - len(repositories),
        'expect_empty': expect_empty,
        'total_image_count': sum(item['image_count'] for item in proof),
        'repositories': proof,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--expect-empty', action='store_true',
                        help='Require zero images across the recreated catalog')
    parser.add_argument('--frameworks-dir', type=Path, default=ROOT.parent / 'frameworks')
    args = parser.parse_args(argv)
    try:
        result = verify_readback(args.account_id, args.region, expect_empty=args.expect_empty,
                                 frameworks_dir=args.frameworks_dir)
    except (BackendError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'FAIL', 'error': getattr(exc, 'code', 'INVALID_CONTRACT'),
                          'message': str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
