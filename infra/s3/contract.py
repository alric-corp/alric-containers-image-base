"""Offline S3 policy and address contract; no SDK, credentials or network."""

SNAPSHOTS_PREFIX = 'sbom-analytics/poc-v1/snapshots/'
RESULTS_PREFIX = 'query-results/poc-v1/'
RESOURCE_TYPES = (
    'aws_s3_bucket',
    'aws_s3_bucket_public_access_block',
    'aws_s3_bucket_ownership_controls',
    'aws_s3_bucket_server_side_encryption_configuration',
    'aws_s3_bucket_versioning',
    'aws_s3_bucket_policy',
)
ADDRESSES = {f'module.sbom.{kind}.sbom': kind for kind in RESOURCE_TYPES}


def bucket_policy(bucket):
    arn = f'arn:aws:s3:::{bucket}'
    protected = f'{arn}/{SNAPSHOTS_PREFIX}*'
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
