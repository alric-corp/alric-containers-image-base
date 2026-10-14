"""Frozen analytics requests and redacted failures; no SDK or release Store."""
from dataclasses import asdict, dataclass, field
import re

from scripts.pipeline.analytics.spdx import canonical, sha256

PROTOCOL_VERSION = 1
FIXED_FILES = frozenset(('complete.json', 'reports/records.json', 'reports/normalization.json',
                        'analytics/sbom_observations/part-00000.parquet',
                        'analytics/sbom_packages/part-00000.parquet'))


class IngestionError(ValueError):
    def __init__(self, code, *, stage='VALIDATE', operation=None, key=None, retryable=False,
                 expected=None, observed=None, batch_id=None, snapshot_id=None):
        super().__init__(code)
        self.code, self.stage, self.operation, self.key = code, stage, operation, key
        self.retryable, self.expected, self.observed = retryable, expected, observed
        self.batch_id, self.snapshot_id = batch_id, snapshot_id

    def diagnostic(self, *, batch_id=None, snapshot_id=None):
        return dict(diagnostic_version=1, status='ERROR', stage=self.stage, code=self.code,
                    batch_id=batch_id or self.batch_id, snapshot_id=snapshot_id or self.snapshot_id,
                    operation=self.operation, object=self.key,
                    expected=self.expected, observed=self.observed, complete=False,
                    catalog_eligible=False, retryable=self.retryable)


def check(condition, code, **context):
    if not condition:
        raise IngestionError(code, **context)


def hash_id(value):
    check(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'INVALID_HASH')
    return value


def material_path(value):
    check(type(value) is str and (value in FIXED_FILES or re.fullmatch(
        r'raw/(?:spdx/sha256=[0-9a-f]{64}/document\.spdx\.json|records/sha256=[0-9a-f]{64}/record\.json)', value)),
        'UNSAFE_OR_UNEXPECTED_PATH')
    return value


@dataclass(frozen=True)
class Limits:
    object_bytes: int = 64 * 1024 * 1024
    snapshot_bytes: int = 256 * 1024 * 1024
    objects: int = 2048
    page_size: int = 1000
    pages: int = 8
    put_attempts: int = 3
    read_chunk: int = 64 * 1024
    parquet_expanded_bytes: int = 256 * 1024 * 1024

    def __post_init__(self):
        maximum = dict(object_bytes=512*1024*1024, snapshot_bytes=1024*1024*1024,
                       objects=8192, page_size=1000, pages=128, put_attempts=5,
                       read_chunk=1024*1024, parquet_expanded_bytes=1024*1024*1024)
        check(all(type(v) is int and 0 < v <= maximum[k] for k,v in asdict(self).items()), 'INVALID_LIMITS')


@dataclass(frozen=True)
class Destination:
    bucket: str
    prefix: str
    region: str
    expected_bucket_owner: object

    def __post_init__(self):
        check(type(self.bucket) is str and re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', self.bucket)
              and '..' not in self.bucket and '.-' not in self.bucket and '-.' not in self.bucket
              and not re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}', self.bucket)
              and not self.bucket.endswith(('--x-s3', '-s3alias', '--ol-s3')), 'INVALID_BUCKET')
        check(type(self.prefix) is str and len(self.prefix.encode()) <= 512
              and all(re.fullmatch('[A-Za-z0-9_=-][A-Za-z0-9_.=-]*', p) for p in self.prefix.split('/')),
              'INVALID_PREFIX')
        check(type(self.region) is str and re.fullmatch('[a-z0-9][a-z0-9-]{1,63}', self.region), 'INVALID_REGION')
        check(self.expected_bucket_owner is None or (type(self.expected_bucket_owner) is str
              and re.fullmatch('[0-9]{12}', self.expected_bucket_owner)), 'INVALID_BUCKET_OWNER')

    def snapshot_prefix(self, snapshot_id):
        return self.prefix + '/snapshots/' + hash_id(snapshot_id) + '/'

    def uri(self, snapshot_id):
        return 's3://' + self.bucket + '/' + self.snapshot_prefix(snapshot_id)


@dataclass(frozen=True)
class FrozenObject:
    path: str
    body: bytes
    content_type: str
    metadata: tuple
    sha256: str = field(init=False)

    def __post_init__(self):
        check(type(self.body) is bytes, 'FROZEN_BYTES_REQUIRED')
        material_path(self.path) if self.path != 'ingestion-manifest.json' else None
        check(self.content_type in ('application/json', 'application/vnd.apache.parquet'), 'INVALID_CONTENT_TYPE')
        metadata = tuple(sorted(dict(self.metadata).items()))
        check(all(type(k) is str and re.fullmatch('[a-z0-9-]+', k) and type(v) is str
                  and v.isascii() and all(32 <= ord(c) < 127 for c in v) for k,v in metadata), 'INVALID_METADATA')
        check(sum(len(k)+len(v) for k,v in metadata) <= 2048, 'METADATA_LIMIT')
        object.__setattr__(self, 'metadata', metadata)
        object.__setattr__(self, 'sha256', sha256(self.body))

    def inventory(self):
        return dict(path=self.path, size=len(self.body), sha256=self.sha256,
                    content_type=self.content_type, metadata=dict(self.metadata))


def object_bytes(path, body, batch_id):
    return FrozenObject(path, body, 'application/vnd.apache.parquet' if path.endswith('.parquet') else 'application/json',
                        (('analytics-protocol', '1'), ('batch-id', hash_id(batch_id)), ('sha256', sha256(body))))


@dataclass(frozen=True)
class SnapshotPlan:
    destination: Destination
    batch_id: str
    objects: tuple
    limits: Limits = Limits()

    def __post_init__(self):
        check(type(self.destination) is Destination and type(self.limits) is Limits, 'EXPLICIT_CONFIGURATION_REQUIRED')
        hash_id(self.batch_id)
        check(type(self.objects) is tuple and all(type(o) is FrozenObject for o in self.objects), 'FROZEN_OBJECTS_REQUIRED')
        paths = [o.path for o in self.objects]
        check(paths == sorted(set(paths)) and FIXED_FILES <= set(paths)
              and 'ingestion-manifest.json' not in paths, 'INVALID_PLAN_INVENTORY')
        check(len(paths) + 1 <= self.limits.objects and sum(len(o.body) for o in self.objects) <= self.limits.snapshot_bytes
              and all(len(o.body) <= self.limits.object_bytes for o in self.objects), 'PLAN_LIMIT_EXCEEDED')
        check(all(o == object_bytes(o.path, o.body, self.batch_id) for o in self.objects), 'PLAN_METADATA_DIFFERS')

    def identity(self):
        return dict(protocol_version=PROTOCOL_VERSION, batch_id=self.batch_id, schema_version=1,
                    normalizer_version='1.0.0', destination=asdict(self.destination),
                    files=[o.inventory() for o in self.objects])

    @property
    def snapshot_id(self):
        return sha256(canonical(self.identity()))

    def key(self, path):
        return self.destination.snapshot_prefix(self.snapshot_id) + path
