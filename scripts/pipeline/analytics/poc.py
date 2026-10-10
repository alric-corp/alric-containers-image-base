"""Thin explicit-client POC orchestration; offline commands never discover AWS credentials."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

from scripts.pipeline.analytics.catalog import catalog_plan
from scripts.pipeline.analytics.demo import demonstrate
from scripts.pipeline.analytics.ingest import publish_reported
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError, Limits, check
from scripts.pipeline.analytics.normalize import read_completed
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import load_plan, read_snapshot, recover_snapshot
from scripts.pipeline.analytics.spdx import canonical, document, fields, packages, read_local, sha256, LIMITS

PACKAGE_LIMIT = 2 * 1024 * 1024


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value) + b'\n'
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(raw)
        name = temporary.name
    os.replace(name, path)


def config(path):
    value = document(read_local(Path(path), 65536))
    fields(value, ('protocol_version', 'destination', 'expected_role_arn', 'expected_role_id',
                   'batch_id', 'snapshot_id', 'payload_objects', 'payload_bytes', 'golden'))
    check(type(value['protocol_version']) is int and value['protocol_version'] == 1, 'UNSUPPORTED_POC_CONFIG')
    Destination(**value['destination'])
    check(re.fullmatch(r'arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_-]{1,64}', value['expected_role_arn']), 'INVALID_ROLE')
    check(re.fullmatch(r'AROA[A-Z0-9]+', value['expected_role_id']), 'INVALID_ROLE_ID')
    for key in ('batch_id', 'snapshot_id'):
        check(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]), 'INVALID_HASH')
    for key in ('payload_objects', 'payload_bytes'):
        check(type(value[key]) is int and value[key] > 0, 'INVALID_POC_COUNT')
    fields(value['golden'], ('observations', 'packages', 'runtime_framework', 'dev_framework',
                            'platform_components', 'comparison', 'component'))
    return value


def check_plan(plan, expected):
    check(plan.destination == Destination(**expected['destination']) and plan.batch_id == expected['batch_id']
          and plan.snapshot_id == expected['snapshot_id'], 'FROZEN_PLAN_IDENTITY_DIFFERS')
    check(len(plan.objects) == expected['payload_objects']
          and sum(len(o.body) for o in plan.objects) == expected['payload_bytes'], 'FROZEN_PLAN_INVENTORY_DIFFERS')
    return plan


def unpack(package, descriptor, output, expected):
    """Only data from a hash-authorized, bounded ZIP; no code is executed."""
    descriptor = document(read_local(Path(descriptor), 65536))
    fields(descriptor, ('schema_version', 'package_sha256', 'package_bytes', 'plan_sha256', 'origin'))
    check(type(descriptor['schema_version']) is int and descriptor['schema_version'] == 1, 'UNSUPPORTED_PACKAGE')
    raw = read_local(Path(package), PACKAGE_LIMIT)
    check(sha256(raw) == descriptor['package_sha256'] and len(raw) == descriptor['package_bytes'], 'PACKAGE_BYTES_DIFFER')
    output = Path(output)
    check(not output.exists() and not output.is_symlink(), 'PREPARATION_DESTINATION_EXISTS')
    import io
    from scripts.pipeline.analytics.ingestion_types import material_path
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        check(0 < len(infos) <= 64 and len({i.filename for i in infos}) == len(infos), 'PACKAGE_MEMBERS_INVALID')
        total = 0
        members = {}
        for info in infos:
            name = info.filename
            check(not info.is_dir() and not info.flag_bits & 1 and info.compress_type == zipfile.ZIP_STORED,
                  'PACKAGE_MEMBER_TYPE')
            mode = info.external_attr >> 16
            check(stat.S_IFMT(mode) in (0, stat.S_IFREG), 'PACKAGE_MEMBER_TYPE')
            if name != 'plan.json':
                check(name.startswith('batch/'), 'PACKAGE_MEMBER_PATH')
                material_path(name[6:])
            check(0 <= info.file_size <= 1024 * 1024, 'PACKAGE_EXPANSION_LIMIT')
            with archive.open(info) as stream:
                body = stream.read(1024 * 1024 + 1)
            total += len(body)
            check(len(body) == info.file_size and total <= PACKAGE_LIMIT, 'PACKAGE_EXPANSION_LIMIT')
            members[name] = body
    check('plan.json' in members and sha256(members['plan.json']) == descriptor['plan_sha256'], 'PLAN_BYTES_DIFFER')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.poc-package-') as temporary:
        stage = Path(temporary) / 'plan'
        stage.mkdir()
        for name, body in members.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        plan = check_plan(load_plan(stage), expected)
        os.rename(stage, output)
    return dict(status='TESTED_LOCAL', code='FROZEN_PLAN_READY', batch_id=plan.batch_id,
                snapshot_id=plan.snapshot_id, package_sha256=sha256(raw), payload_objects=len(plan.objects),
                payload_bytes=sum(len(o.body) for o in plan.objects), cloud_calls=0)


def identity(sts, expected, session_name):
    role = expected['expected_role_arn']
    account = role.split(':')[4]
    check(account == expected['destination']['expected_bucket_owner'], 'EXPECTED_ACCOUNT_DIFFERS')
    observed = sts.get_caller_identity()
    check(observed.get('Account') == account and
          observed.get('Arn') == f'arn:aws:sts::{account}:assumed-role/{role.split("/")[-1]}/{session_name}' and
          observed.get('UserId') == expected['expected_role_id'] + ':' + session_name, 'STS_IDENTITY_DIFFERS', stage='IDENTITY')
    return {k: observed[k] for k in ('Account', 'Arn', 'UserId')}


def bucket_readback(client, destination):
    args = dict(Bucket=destination.bucket, ExpectedBucketOwner=destination.expected_bucket_owner)
    calls = {'location': 'get_bucket_location', 'versioning': 'get_bucket_versioning',
             'ownership': 'get_bucket_ownership_controls', 'encryption': 'get_bucket_encryption',
             'public_access': 'get_public_access_block', 'policy': 'get_bucket_policy'}
    values = {name: getattr(client, operation)(**args) for name, operation in calls.items()}
    check((values['location'].get('LocationConstraint') or 'us-east-1') == destination.region, 'BUCKET_REGION_DIFFERS')
    check(values['versioning'].get('Status') == 'Enabled', 'BUCKET_VERSIONING_DIFFERS')
    check(values['ownership']['OwnershipControls']['Rules'] == [{'ObjectOwnership': 'BucketOwnerEnforced'}], 'BUCKET_OWNERSHIP_DIFFERS')
    check(all(values['public_access']['PublicAccessBlockConfiguration'].get(k) is True for k in
              ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')), 'BUCKET_PUBLIC_ACCESS_DIFFERS')
    rules = values['encryption']['ServerSideEncryptionConfiguration']['Rules']
    check(len(rules) == 1 and rules[0]['ApplyServerSideEncryptionByDefault'] == {'SSEAlgorithm': 'AES256'}, 'BUCKET_ENCRYPTION_DIFFERS')
    policy = document(values['policy']['Policy'].encode())
    return dict(region=destination.region, versioning='Enabled', ownership='BucketOwnerEnforced',
                encryption='AES256', public_access='BLOCKED', policy=policy, policy_sha256=sha256(canonical(policy)))


def service_code(error):
    response = getattr(error, 'response', {})
    code = response.get('Error', {}).get('Code') if type(response) is dict else None
    return code if type(code) is str and re.fullmatch('[A-Za-z0-9_.-]{1,100}', code) else type(error).__name__


def smoke(client, destination, execution_id):
    """Only public probe bytes, outside the valid snapshot; no automatic deletion."""
    check(type(execution_id) is str and re.fullmatch('[a-zA-Z0-9_-]{1,80}', execution_id), 'INVALID_PROBE_ID')
    import base64
    prefix = destination.prefix + '/snapshots/_smoke_tests/' + execution_id + '/'
    body = b'Factory SBOM analytics conditional-write probe v1\n'
    arguments = dict(Bucket=destination.bucket, ExpectedBucketOwner=destination.expected_bucket_owner,
                     Body=body, ContentType='text/plain', ContentLength=len(body), Metadata={'probe':'sbom-analytics-v1'},
                     ChecksumSHA256=base64.b64encode(bytes.fromhex(sha256(body))).decode())
    first = client.put_object(Key=prefix + 'conditional.txt', IfNoneMatch='*', **arguments)
    version = first.get('VersionId')
    check(type(version) is str and version, 'SMOKE_VERSION_REQUIRED')

    def read(version_id=None):
        args = dict(Bucket=destination.bucket, Key=prefix + 'conditional.txt', ExpectedBucketOwner=destination.expected_bucket_owner)
        if version_id:
            args['VersionId'] = version_id
        result = client.get_object(**args)
        with result['Body'] as stream:
            recovered = stream.read(len(body) + 1)
        check(recovered == body and sha256(recovered) == sha256(body) and result.get('VersionId') == version, 'SMOKE_READBACK_DIFFERS')
        return sha256(recovered)

    read(version)
    try:
        client.put_object(Key=prefix + 'conditional.txt', IfNoneMatch='*', **arguments)
    except Exception as error:
        check(service_code(error) == 'PreconditionFailed' and error.response['ResponseMetadata']['HTTPStatusCode'] == 412,
              'SMOKE_RETRY_NOT_PRECONDITION_FAILED')
    else:
        raise IngestionError('SMOKE_CONDITIONAL_OVERWRITE_ALLOWED')
    try:
        client.put_object(Key=prefix + 'unconditional-deny.txt', **arguments)
    except Exception as error:
        check(service_code(error) == 'AccessDenied', 'SMOKE_DENY_UNEXPECTED_ERROR')
        message = getattr(error, 'response', {}).get('Error', {}).get('Message', '')
        deny_source = 'RESOURCE_POLICY_EXPLICIT_DENY' if 'explicit deny in a resource-based policy' in message else 'ACCESS_DENIED_SOURCE_NOT_CERTIFIED'
    else:
        raise IngestionError('SMOKE_UNCONDITIONAL_WRITE_ALLOWED')
    read()
    return dict(status='PASS', key=prefix + 'conditional.txt', version_id=version, sha256=sha256(body),
                retry='PreconditionFailed/412', unconditional_denied=True, deny_source=deny_source,
                retained=True, delete_test='NOT_EXECUTED')


class CountedClient:
    def __init__(self, client):
        self.client, self.meta, self.calls = client, client.meta, Counter()

    def __getattr__(self, name):
        operation = getattr(self.client, name)
        def call(**kwargs):
            self.calls[name] += 1
            return operation(**kwargs)
        return call


def publish(plan_directory, client, sts, expected, session_name, report_directory, execution_id):
    plan = check_plan(load_plan(plan_directory), expected)  # Before any cloud call.
    reports = Path(report_directory)
    reports.mkdir(parents=True, exist_ok=True)
    check(reports.resolve() != Path(plan_directory).resolve() and Path(plan_directory).resolve() not in reports.resolve().parents,
          'REPORT_INSIDE_INPUT')
    observed = identity(sts, expected, session_name)
    write_json(reports / 'identity.json', observed)
    checks = bucket_readback(client, plan.destination)
    write_json(reports / 'bucket-readback.json', checks)
    probe = smoke(client, plan.destination, execution_id)
    write_json(reports / 'smoke.json', probe)
    counted = CountedClient(client)
    adapter = S3Adapter(counted, plan.destination, plan.limits)
    first = publish_reported(plan, adapter, reports / 'publication.json', protected_roots=(plan_directory,))
    check(first.get('complete') is True, first['code'], stage='PUBLISH')
    before = read_snapshot(adapter, plan.snapshot_id)
    puts = counted.calls['put_object']
    retry = publish_reported(plan, adapter, reports / 'retry.json', protected_roots=(plan_directory,))
    check(retry.get('code') == 'SNAPSHOT_ALREADY_PRESENT_IDENTICAL' and retry.get('complete') is True, 'RETRY_DIFFERS')
    after = read_snapshot(adapter, plan.snapshot_id)
    check(before.manifest_version == after.manifest_version and before.manifest == after.manifest and
          counted.calls['put_object'] == puts, 'RETRY_WROTE_OR_CHANGED_SNAPSHOT')
    manifest = document(after.manifest.body)
    write_json(reports / 'manifest.json', manifest)
    return dict(status='SUCCESS', code='S3_PUBLISHED_AND_IDENTICAL_RETRY', identity=observed,
                batch_id=plan.batch_id, snapshot_id=plan.snapshot_id, object_count=len(plan.objects)+1,
                smoke=probe, publication=first, retry=retry, retry_put_calls=0,
                s3_integrity='READBACK_VERIFIED', authentication='NOT_REVALIDATED', publication_authority=False)


def inspect_recovered(directory, expected):
    data = read_completed(directory)
    golden = expected['golden']
    check(len(data['observations']) == golden['observations'] and len(data['packages']) == golden['packages'], 'RECOVERED_COUNTS_DIFFER')
    trace = []
    for row in data['observations']:
        raw = read_local(Path(directory) / row['raw_spdx_path'], LIMITS['document_bytes'])
        check(sha256(raw) == row['sbom_sha256'], 'RAW_HASH_DIFFERS')
        packages(raw, row['subject_digest'])
        trace.append(dict(observation_id=row['observation_id'], framework=row['framework'],
                          document_platform=row['document_platform'], subject_digest=row['subject_digest'],
                          sbom_sha256=row['sbom_sha256'], raw_spdx_path=row['raw_spdx_path']))
    selected = {r['framework']:r['image_index_digest'] for r in data['observations']}
    local = demonstrate(Path(directory), component=golden['component'],
        runtime_framework=golden['runtime_framework'], dev_framework=golden['dev_framework'],
        runtime_index=selected[golden['runtime_framework']], dev_index=selected[golden['dev_framework']], platform='linux/amd64')
    counts = {r['framework'] + ':' + r['document_platform']: r['component_records'] for r in local['component_counts']}
    check(counts == golden['platform_components'], 'RECOVERED_COMPONENT_COUNTS_DIFFER')
    check(local['queries']['03_runtime_vs_dev']['counts'] == golden['comparison'], 'RECOVERED_COMPARISON_DIFFERS')
    return dict(observations=len(data['observations']), packages=len(data['packages']), raw_traceability=trace,
                local_queries=local, authority=False, authenticity='NOT_REVALIDATED')


def recover(client, sts, expected, session_name, output):
    observed = identity(sts, expected, session_name)
    adapter = S3Adapter(client, Destination(**expected['destination']))
    result = recover_snapshot(adapter, expected['snapshot_id'], output)
    check(result['batch_id'] == expected['batch_id'], 'RECOVERED_BATCH_DIFFERS')
    inspection = inspect_recovered(output, expected)
    verified = read_snapshot(adapter, expected['snapshot_id'])
    return dict(status='SUCCESS', code='INDEPENDENT_S3_RECOVERY_VERIFIED', identity=observed,
                recovery=result, inspection=inspection, manifest=document(verified.manifest.body),
                preparation_inputs_required=False, github_artifact_fallback=False)



def session_policy(expected, *, writer):
    target = Destination(**expected['destination'])
    bucket = 'arn:aws:s3:::' + target.bucket
    prefix = target.prefix + '/snapshots/'
    statements = [
        dict(Effect='Allow', Action=['sts:GetCallerIdentity'], Resource='*'),
        dict(Effect='Allow', Action=['s3:ListBucket'], Resource=bucket,
             Condition={'StringLike': {'s3:prefix': [prefix + '*']}}),
        dict(Effect='Allow', Action=['s3:GetObject', 's3:GetObjectVersion'] + (['s3:PutObject'] if writer else []),
             Resource=bucket + '/' + prefix + '*'),
    ]
    if writer:
        statements.append(dict(Effect='Allow', Action=['s3:GetBucketLocation', 's3:GetBucketVersioning',
            's3:GetBucketOwnershipControls', 's3:GetEncryptionConfiguration', 's3:GetBucketPublicAccessBlock',
            's3:GetBucketPolicy'], Resource=bucket))
    return dict(Version='2012-10-17', Statement=statements)


def aws_clients(expected):
    """Explicit CLI boundary: require already supplied temporary credentials, no profile fallback."""
    check(all(os.environ.get(k) for k in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')),
          'TEMPORARY_CREDENTIALS_REQUIRED')
    import boto3
    from botocore.config import Config
    region = expected['destination']['region']
    session = boto3.Session(aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'], aws_session_token=os.environ['AWS_SESSION_TOKEN'],
        region_name=region)
    options = Config(connect_timeout=10, read_timeout=30, retries={'total_max_attempts': 1})
    return session.client('s3', config=options), session.client('sts', config=options)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise IngestionError('POC_ARGUMENTS_INVALID', stage='ARGUMENTS')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _Parser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'publish', 'recover'))
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--descriptor', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--session-name')
    parser.add_argument('--execution-id')
    try:
        args = parser.parse_args(argv)
    except (IngestionError, argparse.ArgumentError):
        result = dict(status='ERROR', code='POC_ARGUMENTS_INVALID', stage='ARGUMENTS')
        # Malformed arguments still get JSON; never overwrite a referenced input.
        def option(name):
            positions = [i for i, value in enumerate(argv) if value == name]
            return Path(argv[positions[0]+1]) if len(positions)==1 and positions[0]+1<len(argv) else None
        sink = option('--report')
        inputs = [option(x) for x in ('--plan','--package','--descriptor','--config','--output')]
        try:
            if sink:
                check(all(sink.resolve()!=p.resolve() and p.resolve() not in sink.resolve().parents for p in inputs if p), 'REPORT_INSIDE_INPUT')
                write_json(sink,result)
        except Exception:
            result = dict(status='ERROR', code='REPORT_WRITE_FAILED', stage='ARGUMENTS')
        print(json.dumps(result,sort_keys=True))
        return 1
    result = dict(status='ERROR', code='POC_NOT_STARTED', stage=args.command)
    try:
        expected = config(args.config)
        protected = [p.resolve() for p in (args.plan, args.package, args.descriptor, args.config, args.output) if p is not None]
        target = args.report.resolve()
        check(all(target != p and p not in target.parents for p in protected), 'REPORT_INSIDE_INPUT')
        if args.command == 'prepare':
            result = unpack(args.package, args.descriptor, args.output, expected)
        else:
            check(type(args.session_name) is str and re.fullmatch('[a-zA-Z0-9_-]{2,64}', args.session_name), 'INVALID_SESSION_NAME')
            # Complete local plan validation occurs before SDK/session construction.
            if args.command == 'publish':
                check_plan(load_plan(args.plan), expected)
            s3, sts = aws_clients(expected)
            if args.command == 'publish':
                result = publish(args.plan, s3, sts, expected, args.session_name, args.report.parent, args.execution_id)
            else:
                result = recover(s3, sts, expected, args.session_name, args.output)
        result['execution'] = {k: os.environ.get(k) for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
                                'GITHUB_REPOSITORY', 'GITHUB_REF', 'GITHUB_EVENT_NAME')}
        result['session_scope'] = 'ANALYTICS_S3_ONLY' if args.command == 'publish' else 'ANALYTICS_S3_READ_ONLY'
        write_json(args.report, result)
    except Exception as error:
        result = error.diagnostic() if isinstance(error, IngestionError) else dict(status='ERROR', code=service_code(error), stage=args.command)
        try:
            # Recheck sink safety even on input/argument failure.
            check(all(args.report.resolve() != p.resolve() and p.resolve() not in args.report.resolve().parents
                      for p in (args.plan, args.package, args.descriptor, args.config, args.output) if p), 'REPORT_INSIDE_INPUT')
            write_json(args.report, result)
        except Exception:
            result = dict(status='ERROR', code='REPORT_WRITE_FAILED', stage=args.command)
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps({k:v for k,v in result.items() if k != 'inspection'}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
