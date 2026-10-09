#!/usr/bin/env python3
"""Read-only pre-plan guard for the existing root, backend and selected state.

Consumes local backend metadata and `terraform show -json`; never edits state,
initializes another root, changes workspace, or calls AWS.
"""
import argparse
import json
from pathlib import Path
import sys

if __package__:
    from .verify_plan import catalog, expected_resources, managed_resources, S3_ADDRESSES
else:
    from verify_plan import catalog, expected_resources, managed_resources, S3_ADDRESSES


def verify(metadata, state, *, bucket, key, region, workspace, root):
    if Path(root).resolve() != Path(__file__).resolve().parent or workspace != 'default':
        raise ValueError('Only infra/ecr and the existing default workspace are authorized')
    backend = metadata.get('backend', {})
    config = backend.get('config', {})
    expected = dict(bucket=bucket, key=key, region=region, encrypt=True, use_lockfile=True)
    if backend.get('type') != 's3' or any(config.get(k) != v for k, v in expected.items()):
        raise ValueError('Backend bucket/key/region/encryption/locking differs from expected configuration')
    ecr = set(expected_resources(catalog(Path(root).parent.parent / 'frameworks')))
    addresses = [r.get('address') for r in managed_resources(state.get('values', {}).get('root_module', {}))]
    if (len(set(addresses)) != len(addresses) or ecr - set(addresses)
            or set(addresses) - ecr - set(S3_ADDRESSES)):
        raise ValueError('Selected state is missing an ECR address or contains an unexpected managed address')
    return dict(status='STATE_BOUNDARY_VERIFIED', workspace=workspace,
                backend=expected, ecr_managed_count=len(ecr),
                s3_managed_count=len(set(addresses) & set(S3_ADDRESSES)),
                managed_addresses=sorted(addresses))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--bucket', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--region', required=True)
    p.add_argument('--workspace', required=True)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = p.parse_args(argv)
    try:
        result = verify(json.loads(args.metadata.read_text()), json.loads(args.state.read_text()),
                        bucket=args.bucket, key=args.key, region=args.region,
                        workspace=args.workspace, root=args.root)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = dict(status='FAIL', code='STATE_BOUNDARY_REJECTED', message=str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'STATE_BOUNDARY_VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
