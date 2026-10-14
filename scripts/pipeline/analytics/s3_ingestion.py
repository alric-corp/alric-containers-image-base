"""Low-level S3 calls on an explicitly injected client, never SDK construction."""
import base64
from dataclasses import dataclass

from scripts.pipeline.analytics.ingestion_types import (
    Destination, FrozenObject, IngestionError, Limits, check, material_path,
)
from scripts.pipeline.analytics.spdx import sha256


@dataclass(frozen=True)
class ReadObject:
    body: bytes
    content_type: str
    metadata: tuple
    version_id: object


def _service_error(error):
    response = getattr(error, 'response', None)
    if type(response) is dict:
        metadata, detail = response.get('ResponseMetadata'), response.get('Error')
        return (metadata.get('HTTPStatusCode') if type(metadata) is dict else None,
                detail.get('Code') if type(detail) is dict else None)
    return None, None


def _http_status(response):
    metadata = response.get('ResponseMetadata') if type(response) is dict else None
    return metadata.get('HTTPStatusCode') if type(metadata) is dict else None


def _version(value):
    check(value is None or (type(value) is str and 0 < len(value) <= 1024), 'INVALID_VERSION_RESPONSE', stage='READBACK')
    return value


class S3Adapter:
    def __init__(self, client, destination, limits=Limits()):
        check(type(destination) is Destination and type(limits) is Limits, 'EXPLICIT_CONFIGURATION_REQUIRED')
        check(client is not None and all(callable(getattr(client, n, None)) for n in
              ('put_object', 'get_object', 'list_objects_v2')), 'INJECTED_LOW_LEVEL_CLIENT_REQUIRED')
        check(getattr(getattr(client, 'meta', None), 'region_name', None) == destination.region, 'CLIENT_REGION_DIFFERS')
        self.client, self.destination, self.limits = client, destination, limits

    def authorize(self, destination):
        check(destination == self.destination, 'DESTINATION_NOT_AUTHORIZED', stage='AUTHORIZE')

    def _arguments(self, key):
        prefix = self.destination.prefix + '/snapshots/'
        check(type(key) is str and key.startswith(prefix) and len(key.encode()) <= 1024, 'KEY_NOT_AUTHORIZED')
        tail = key[len(prefix):].split('/', 1)
        from scripts.pipeline.analytics.ingestion_types import hash_id
        check(len(tail) == 2, 'KEY_NOT_AUTHORIZED')
        hash_id(tail[0])
        if tail[1] != 'ingestion-manifest.json':
            material_path(tail[1])
        result = dict(Bucket=self.destination.bucket, Key=key)
        if self.destination.expected_bucket_owner is not None:
            result['ExpectedBucketOwner'] = self.destination.expected_bucket_owner
        return result

    def _failure(self, error, operation, key):
        status, _ = _service_error(error)
        return IngestionError('ACCESS_DENIED' if status == 403 else 'TRANSPORT_ERROR', stage='TRANSPORT',
            operation=operation, key=key, retryable=status is None or status in (408, 429) or
            (type(status) is int and status >= 500),
            observed={'http_status': status} if type(status) is int else None)

    def get(self, key, version_id=None):
        arguments = self._arguments(key)
        if version_id is not None:
            arguments['VersionId'] = _version(version_id)
        try:
            response = self.client.get_object(**arguments)
        except Exception as error:
            status, code = _service_error(error)
            if status == 404 and code == 'NoSuchKey' and version_id is None:
                return None
            if status == 404 and code in ('NoSuchKey', 'NoSuchVersion') and version_id is not None:
                raise IngestionError('VERSION_UNAVAILABLE', stage='READBACK', operation='GetObject', key=key) from error
            raise self._failure(error, 'GetObject', key) from error
        stream = response.get('Body') if type(response) is dict else None
        try:
            check(_http_status(response) == 200,
                  'INCONCLUSIVE_READ', stage='READBACK', operation='GetObject', key=key)
            size = response.get('ContentLength')
            check(type(size) is int and 0 <= size <= self.limits.object_bytes, 'READ_SIZE_LIMIT',
                  stage='READBACK', operation='GetObject', key=key)
            check(callable(getattr(stream, 'read', None)), 'INVALID_BODY', stage='READBACK', key=key)
            chunks, total = [], 0
            while True:
                chunk = stream.read(min(self.limits.read_chunk, size - total + 1))
                check(type(chunk) is bytes, 'INVALID_BODY', stage='READBACK', key=key)
                total += len(chunk)
                check(total <= size, 'READBACK_SIZE_DIFFERS', stage='READBACK', key=key, expected=size, observed=total)
                if not chunk:
                    break
                chunks.append(chunk)
            check(total == size, 'READBACK_TRUNCATED', stage='READBACK', key=key, expected=size, observed=total)
            observed_version = _version(response.get('VersionId'))
            check(version_id is None or observed_version == version_id, 'VERSION_DIFFERS', stage='READBACK', key=key)
            metadata = response.get('Metadata')
            check(type(metadata) is dict and all(type(k) is str and type(v) is str for k,v in metadata.items()),
                  'INVALID_METADATA_RESPONSE', stage='READBACK', key=key)
            check(type(response.get('ContentType')) is str, 'INVALID_CONTENT_TYPE_RESPONSE', stage='READBACK', key=key)
            return ReadObject(b''.join(chunks), response['ContentType'], tuple(sorted(metadata.items())), observed_version)
        except IngestionError:
            raise
        except Exception as error:
            raise self._failure(error, 'GetObject', key) from error
        finally:
            if callable(getattr(stream, 'close', None)):
                try:
                    stream.close()
                except Exception as error:
                    raise self._failure(error, 'CloseBody', key) from error

    def compare(self, key, request, observed):
        check(observed is not None, 'READBACK_MISSING', stage='READBACK', operation='GetObject', key=key, retryable=True)
        check(observed.body == request.body and sha256(observed.body) == request.sha256
              and observed.metadata == request.metadata and observed.content_type == request.content_type,
              'CONTENT_CONFLICT', stage='READBACK', operation='GetObject', key=key,
              expected={'sha256': request.sha256, 'size': len(request.body)},
              observed={'sha256': sha256(observed.body), 'size': len(observed.body)})
        return observed

    def create(self, key, request):
        check(type(request) is FrozenObject and len(request.body) <= self.limits.object_bytes, 'INVALID_PUT_REQUEST')
        arguments = self._arguments(key)
        check(key.endswith('/' + request.path), 'REQUEST_PATH_DIFFERS')
        for attempt in range(self.limits.put_attempts):
            try:
                response = self.client.put_object(**arguments, Body=request.body, ContentLength=len(request.body),
                    ContentType=request.content_type, Metadata=dict(request.metadata), IfNoneMatch='*',
                    ChecksumSHA256=base64.b64encode(bytes.fromhex(request.sha256)).decode())
            except Exception as error:
                status, code = _service_error(error)
                if status == 409 and code == 'ConditionalRequestConflict':
                    if attempt + 1 < self.limits.put_attempts:
                        continue  # Same frozen request, conditional again; no HEAD/overwrite.
                    raise IngestionError('CONDITIONAL_RETRY_EXHAUSTED', stage='PUT', operation='PutObject',
                                         key=key, retryable=True) from error
                if status == 412 and code == 'PreconditionFailed':
                    return 'ALREADY_PRESENT_IDENTICAL', self.compare(key, request, self.get(key))
                uncertain = isinstance(error, (OSError, ConnectionError, TimeoutError)) or type(error).__name__ in (
                    'EndpointConnectionError', 'ConnectionClosedError', 'ConnectTimeoutError', 'ReadTimeoutError')
                if uncertain or (type(status) is int and status >= 500):
                    try:
                        observed = self.get(key)
                    except IngestionError as read_error:
                        raise IngestionError('WRITE_OUTCOME_UNKNOWN', stage='PUT', operation='PutObject', key=key,
                                             retryable=True, observed={'read_code': read_error.code}) from error
                    if observed is not None:
                        return 'ALREADY_PRESENT_IDENTICAL', self.compare(key, request, observed)
                    raise IngestionError('WRITE_OUTCOME_UNKNOWN', stage='PUT', operation='PutObject', key=key,
                                         retryable=True) from error
                raise self._failure(error, 'PutObject', key) from error
            check(_http_status(response) == 200,
                  'INCONCLUSIVE_WRITE', stage='PUT', operation='PutObject', key=key, retryable=True)
            version = _version(response.get('VersionId'))
            observed = self.compare(key, request, self.get(key, version))
            check(observed.version_id == version, 'VERSION_DIFFERS', stage='READBACK', key=key)
            return 'CREATED', observed

    def list_snapshot(self, snapshot_id):
        prefix = self.destination.snapshot_prefix(snapshot_id)
        arguments = dict(Bucket=self.destination.bucket, Prefix=prefix, MaxKeys=self.limits.page_size)
        if self.destination.expected_bucket_owner is not None:
            arguments['ExpectedBucketOwner'] = self.destination.expected_bucket_owner
        result, tokens = {}, set()
        for _ in range(self.limits.pages):
            try:
                page = self.client.list_objects_v2(**arguments)
            except Exception as error:
                raise self._failure(error, 'ListObjectsV2', prefix) from error
            check(type(page) is dict and _http_status(page) == 200
                  and type(page.get('IsTruncated')) is bool and not page.get('CommonPrefixes'),
                  'INCONCLUSIVE_LIST', stage='LIST', operation='ListObjectsV2', key=prefix)
            entries = page.get('Contents', [])
            check(type(entries) is list and len(entries) <= self.limits.page_size
                  and type(page.get('KeyCount')) is int and page['KeyCount'] == len(entries), 'INVALID_LIST', stage='LIST')
            check(page.get('Name', self.destination.bucket) == self.destination.bucket
                  and page.get('Prefix', prefix) == prefix, 'LIST_SCOPE_DIFFERS', stage='LIST')
            for entry in entries:
                check(type(entry) is dict and type(entry.get('Key')) is str and entry['Key'].startswith(prefix),
                      'LIST_SCOPE_DIFFERS', stage='LIST')
                key = entry['Key']
                self._arguments(key)
                check(key not in result and type(entry.get('Size')) is int and 0 <= entry['Size'] <= self.limits.object_bytes,
                      'INVALID_LIST_ENTRY', stage='LIST', key=key)
                result[key] = entry['Size']
                check(len(result) <= self.limits.objects, 'LIST_LIMIT', stage='LIST', key=prefix)
            if not page['IsTruncated']:
                return result
            token = page.get('NextContinuationToken')
            check(type(token) is str and 0 < len(token) <= 4096 and token not in tokens, 'INVALID_LIST_TOKEN', stage='LIST')
            tokens.add(token)
            arguments['ContinuationToken'] = token
        raise IngestionError('LIST_LIMIT', stage='LIST', operation='ListObjectsV2', key=prefix, retryable=True)
