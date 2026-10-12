"""Offline S3 policy and address contract; no SDK, credentials or network."""

DATA_PREFIX = 'sbom-analytics/v1'
SNAPSHOTS_PREFIX = DATA_PREFIX + '/snapshots/'
RESULTS_PREFIX = 'query-results/sbom-analytics-v1/'
RESOURCE_TYPES = (
    'aws_s3_bucket',
    'aws_s3_bucket_public_access_block',
    'aws_s3_bucket_ownership_controls',
    'aws_s3_bucket_server_side_encryption_configuration',
    'aws_s3_bucket_versioning',
    'aws_s3_bucket_policy',
)
MODULE = 'sbom_analytics'
ADDRESSES = {f'module.{MODULE}.{kind}.sbom': kind for kind in RESOURCE_TYPES}

# Legacy bucket replaced by Distroless SBOM Analytics (2026-10-11). It keeps
# its real historical state address and prefix only while transitional, then
# may only be destroyed.
LEGACY_MODULE = 'sbom'
LEGACY_SOURCE = '../s3-legacy'
LEGACY_ADDRESSES = {f'module.{LEGACY_MODULE}.{kind}.sbom': kind for kind in RESOURCE_TYPES}
LEGACY_SNAPSHOTS_PREFIX = 'sbom-analytics/poc-v1/snapshots/'


# The active bucket name is never derived: each deployment supplies it exactly
# (policies/pipeline/config.json -> analytics.bucket -> var.sbom_bucket_name).
BUCKET_NAME_PATTERN = r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]'


def legacy_bucket_name(account, region):
    return f'alric-distroless-sbom-{account}-{region}'


def bucket_policy(bucket, snapshots_prefix=SNAPSHOTS_PREFIX):
    arn = f'arn:aws:s3:::{bucket}'
    protected = f'{arn}/{snapshots_prefix}*'
    return {
        'Version': '2012-10-17',
        'Statement': [
            {'Sid': 'DenyInsecureTransport', 'Effect': 'Deny', 'Principal': '*',
             'Action': 's3:*', 'Resource': [arn, arn + '/*'],
             'Condition': {'Bool': {'aws:SecureTransport': 'false'}}},
            {'Sid': 'DenySnapshotUnconditionalPut', 'Effect': 'Deny', 'Principal': '*',
             'Action': 's3:PutObject', 'Resource': protected,
             'Condition': {'Null': {'s3:if-none-match': 'true'},
                           'Bool': {'s3:ObjectCreationOperation': 'true'}}},
            {'Sid': 'DenySnapshotOtherCondition', 'Effect': 'Deny', 'Principal': '*',
             'Action': 's3:PutObject', 'Resource': protected,
             'Condition': {'Null': {'s3:if-none-match': 'false'},
                           'StringNotEquals': {'s3:if-none-match': '*'},
                           'Bool': {'s3:ObjectCreationOperation': 'true'}}},
        ],
    }


def unique_json(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f'duplicate JSON key: {key}')
        document[key] = value
    return document
