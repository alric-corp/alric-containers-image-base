#!/usr/bin/env python3
"""Read-only SBOM bucket collision preflight and post-apply configuration proof.

No provisioning, IAM changes or object writes. Preserve a JSON diagnostic before
returning failure. Region null from GetBucketLocation means us-east-1.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import AwsCli, AwsError, BackendError, PUBLIC_ACCESS_BLOCK, validate_inputs
from ecr.verify_plan import verify, PROVENANCE
from readback import semantic_policy
from s3.contract import bucket_policy, SNAPSHOTS_PREFIX, RESULTS_PREFIX, unique_json


def observed_region(response):
    raw = response['LocationConstraint']
    if raw is not None and type(raw) is not str:
        raise ValueError('invalid region type')
    return 'us-east-1' if raw is None else raw


def preflight(plan, account, region, *, aws=None, bucket_name=None):
    scope = verify(plan, account_id=account, region=region, bucket_name=bucket_name)
    bucket = scope['bucket_name']
    aws = aws or AwsCli(region)
    if aws.call('sts', 'get-caller-identity').get('Account') != account:
        raise BackendError('ACCOUNT_MISMATCH', 'Session differs from independently configured account')
    creation = next(c['change']['actions'] for c in plan['resource_changes']
                    if c['address'] == 'module.sbom.aws_s3_bucket.sbom') == ['create']
    try:
        aws.call('s3api', 'head-bucket', bucket=bucket, expected_bucket_owner=account)
    except AwsError as exc:
        if exc.code not in ('404', 'NoSuchBucket'):
            raise
        if not creation:
            raise BackendError('MANAGED_BUCKET_MISSING', 'An existing state bucket is unavailable') from exc
        return dict(status='PREFLIGHT_VERIFIED', bucket=bucket, expected_bucket_owner=account,
                    region=region, bucket_state='ABSENT_AT_PREFLIGHT', cloud_writes=0)
    if creation:
        raise BackendError('BUCKET_NAME_COLLISION', 'Existing bucket will not be adopted, imported or modified')
    location = aws.call('s3api', 'get-bucket-location', bucket=bucket, expected_bucket_owner=account)
    if observed_region(location) != region:
        raise BackendError('REGION_MISMATCH', 'Existing bucket is not in the expected region')
    return dict(status='PREFLIGHT_VERIFIED', bucket=bucket, expected_bucket_owner=account,
                region=region, bucket_state='ALREADY_MANAGED', cloud_writes=0)


def readback(outputs, account, region, *, aws=None):
    values = {k: v.get('value') for k, v in outputs.items()}
    bucket = values.get('bucket_name')
    validate_inputs(bucket, region, account)
    expected_config = {'protocol_version': 1, 'destination': {
        'bucket': bucket, 'prefix': 'sbom-analytics/poc-v1', 'region': region,
        'expected_bucket_owner': account}}
    if (values.get('expected_bucket_owner') != account or values.get('bucket_region') != region
            or values.get('bucket_arn') != f'arn:aws:s3:::{bucket}'
            or values.get('snapshots_prefix') != SNAPSHOTS_PREFIX
            or values.get('query_results_prefix') != RESULTS_PREFIX
            or values.get('ingestion_config') != expected_config):
        raise BackendError('OUTPUT_IDENTITY_MISMATCH', 'Outputs do not match external account/region and ingestion contract')
    tags = values.get('bucket_tags')
    if not isinstance(tags, dict) or any(tags.get(k) != v for k, v in PROVENANCE.items()):
        raise BackendError('OUTPUT_TAGS_MISMATCH', 'Expected ownership tags are absent')
    aws = aws or AwsCli(region)
    identity = aws.call('sts', 'get-caller-identity')
    if identity.get('Account') != account:
        raise BackendError('ACCOUNT_MISMATCH', 'Session differs from independently configured account')
    target = dict(bucket=bucket, expected_bucket_owner=account)
    checks = []

    def check(name, operation, expected, extract, absent=None):
        try:
            response = aws.call('s3api', operation, **target)
            observed = extract(response)
            passed = observed == expected
            record = dict(check=name, expected=expected, observed=observed, result='PASS' if passed else 'FAIL')
        except AwsError as exc:
            if absent and exc.code == absent:
                record = dict(check=name, expected=expected, observed=None, result='PASS', absence_code=exc.code)
            else:
                record = dict(check=name, expected=expected, observed=None, result='ERROR', error=exc.code)
        except (KeyError, TypeError, ValueError) as exc:
            record = dict(check=name, expected=expected, observed=None, result='ERROR', error='INVALID_RESPONSE')
        checks.append(record)

    def ownership(r):
        return r['OwnershipControls']['Rules']

    def encryption(r):
        rules = r['ServerSideEncryptionConfiguration']['Rules']
        if len(rules) != 1 or rules[0].get('BucketKeyEnabled') is True:
            return rules
        return rules[0]['ApplyServerSideEncryptionByDefault']

    def policy(r):
        return semantic_policy(json.loads(r['Policy'], object_pairs_hook=unique_json), iam=True)

    def tag_map(r):
        items = r['TagSet']
        result = {item['Key']: item['Value'] for item in items}
        if len(result) != len(items):
            raise ValueError('duplicate tag')
        return result

    check('owner', 'head-bucket', True, lambda r: True)
    check('region', 'get-bucket-location', region, observed_region)
    check('public_access_block', 'get-public-access-block', PUBLIC_ACCESS_BLOCK, lambda r: r['PublicAccessBlockConfiguration'])
    check('ownership', 'get-bucket-ownership-controls', [{'ObjectOwnership': 'BucketOwnerEnforced'}], ownership)
    check('encryption', 'get-bucket-encryption', {'SSEAlgorithm': 'AES256'}, encryption)
    check('versioning', 'get-bucket-versioning', 'Enabled', lambda r: r['Status'])
    check('policy', 'get-bucket-policy', semantic_policy(bucket_policy(bucket), iam=True), policy)
    check('tags', 'get-bucket-tagging', tags, tag_map)
    check('lifecycle_absent', 'get-bucket-lifecycle-configuration', None, lambda r: r, 'NoSuchLifecycleConfiguration')
    check('object_lock_absent', 'get-object-lock-configuration', None, lambda r: r, 'ObjectLockConfigurationNotFoundError')
    complete = all(c['result'] == 'PASS' for c in checks)
    return dict(status='BUCKET_CONFIGURATION_VERIFIED' if complete else 'FAIL',
                bucket=bucket, account_id=account, region=region, checks=checks,
                object_operations='NOT_PROVEN', retention_worm='NOT_PROVEN', cloud_writes=0,
                ingestion_config=expected_config)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('preflight', 'readback'))
    p.add_argument('--plan', type=Path)
    p.add_argument('--outputs', type=Path)
    p.add_argument('--account-id', required=True)
    p.add_argument('--region', required=True)
    p.add_argument('--bucket-name')
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.operation == 'preflight':
            result = preflight(json.loads(args.plan.read_text(), object_pairs_hook=unique_json),
                               args.account_id, args.region, bucket_name=args.bucket_name)
        else:
            result = readback(json.loads(args.outputs.read_text(), object_pairs_hook=unique_json), args.account_id, args.region)
    except (BackendError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result = dict(status='FAIL', code=getattr(exc, 'code', 'INVALID_CONTRACT'),
                      stage=args.operation, account_id=args.account_id, region=args.region,
                      cloud_writes=0, expected={'account_id': args.account_id, 'region': args.region},
                      observed=None, complete=False)
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    except OSError:
        print(json.dumps(dict(status='FAIL', code='REPORT_WRITE_FAILED', original_status=result['status'])))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in ('PREFLIGHT_VERIFIED', 'BUCKET_CONFIGURATION_VERIFIED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
