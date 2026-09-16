#!/usr/bin/env python3
"""Validate an Infra-owned, pre-provisioned ECR repository descriptor.

RFC-013/ADR-0005 contract: exactly `IMMUTABLE_WITH_EXCLUSION` with exactly
one exclusion filter, `{filterType: WILDCARD, filter: stable}` -- `stable`
is mutable/movable, every other tag (including the immutable build tag)
stays immutable. Infra (`alric-containers-registry`) owns this
configuration via Terraform; this module only ever reads it back and fails
closed on any divergence -- plain `IMMUTABLE`, `MUTABLE`, a different or
additional exclusion filter, all rejected.
"""

import argparse
import json
from pathlib import Path
import re
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_repository(document, expected_name, expected_account, expected_region):
    """Return reviewed repository identity or fail without changing AWS state."""
    require(isinstance(document, dict), 'response must be a JSON object')
    repositories = document.get('repositories')
    require(isinstance(repositories, list), 'response must contain repositories list')
    require(len(repositories) == 1,
            'response must contain exactly one pre-provisioned repository')
    repository = repositories[0]
    require(isinstance(repository, dict), 'repository descriptor must be an object')

    require(isinstance(expected_name, str) and expected_name,
            'expected repository name is required')
    require(re.fullmatch(r'[0-9]{12}', expected_account or '') is not None,
            'expected AWS account must contain 12 digits')
    require(isinstance(expected_region, str) and expected_region,
            'expected AWS region is required')

    require(repository.get('repositoryName') == expected_name,
            'repositoryName does not match the requested destination')

    arn = repository.get('repositoryArn')
    require(isinstance(arn, str), 'repositoryArn is required')
    arn_parts = arn.split(':', 5)
    require(len(arn_parts) == 6 and arn_parts[0] == 'arn'
            and arn_parts[2] == 'ecr'
            and arn_parts[3] == expected_region
            and arn_parts[4] == expected_account
            and arn_parts[5] == f'repository/{expected_name}',
            'repositoryArn does not match account, region and repository')

    uri = repository.get('repositoryUri')
    require(isinstance(uri, str), 'repositoryUri is required')
    uri_pattern = (rf'{re.escape(expected_account)}\.dkr\.ecr\.'
                   rf'{re.escape(expected_region)}\.[^/]+/{re.escape(expected_name)}')
    require(re.fullmatch(uri_pattern, uri) is not None,
            'repositoryUri does not match account, region and repository')

    # RFC-013/ADR-0005: stable é a única exclusão de mutabilidade aceita, e
    # precisa ser exatamente essa -- não uma entre outras, não com filterType
    # diferente, não combinada com qualquer segunda exclusão (latest, *,
    # build* ou qualquer outra). Comparação por igualdade estrutural exata:
    # uma lista com um único dict, só essas duas chaves, só esses dois
    # valores. Qualquer divergência falha fechado.
    require(repository.get('imageTagMutability') == 'IMMUTABLE_WITH_EXCLUSION',
            'imageTagMutability must be IMMUTABLE_WITH_EXCLUSION')
    exclusions = repository.get('imageTagMutabilityExclusionFilters')
    require(exclusions == [{'filterType': 'WILDCARD', 'filter': 'stable'}],
            'imageTagMutabilityExclusionFilters must be exactly '
            '[{filterType: WILDCARD, filter: stable}]')

    scanning = repository.get('imageScanningConfiguration')
    require(isinstance(scanning, dict) and scanning.get('scanOnPush') is True,
            'imageScanningConfiguration.scanOnPush must be true')
    encryption = repository.get('encryptionConfiguration')
    require(isinstance(encryption, dict)
            and encryption.get('encryptionType') == 'AES256',
            'encryptionConfiguration.encryptionType must be AES256')

    return {
        'repositoryName': expected_name,
        'repositoryArn': arn,
        'repositoryUri': uri,
        'account': expected_account,
        'region': expected_region,
        'imageTagMutability': 'IMMUTABLE_WITH_EXCLUSION',
        'imageTagMutabilityExclusionFilters': [{'filterType': 'WILDCARD', 'filter': 'stable'}],
        'scanOnPush': True,
        'encryptionType': 'AES256',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('descriptor', type=Path)
    parser.add_argument('repository')
    parser.add_argument('account')
    parser.add_argument('region')
    args = parser.parse_args()
    try:
        result = validate_repository(json.loads(args.descriptor.read_text()),
                                     args.repository, args.account, args.region)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
        print(f'ECR repository preflight failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
