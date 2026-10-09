"""Service-shaped in-process fake. Its lock proves no deployed S3 control."""
import base64
import io
from threading import Lock
from types import SimpleNamespace

from scripts.pipeline.analytics.spdx import sha256


class ServiceError(Exception):
    def __init__(self, status, code):
        super().__init__('opaque SDK message: SECRET must never reach diagnostics')
        self.response = dict(ResponseMetadata=dict(HTTPStatusCode=status), Error=dict(Code=code))


class FakeS3:
    def __init__(self, region='test-region-1', *, versioned=True):
        self.meta = SimpleNamespace(region_name=region)
        self.versioned, self.counter = versioned, 0
        self.current, self.versions, self.calls = {}, {}, []
        self.lock = Lock()
        self.before, self.after = None, None

    def _call(self, name, request, implementation):
        with self.lock:
            self.calls.append((name, dict(request)))
        if self.before:
            self.before(name, request)
        with self.lock:
            result = implementation()
        if self.after:
            changed = self.after(name, request, result)
            if changed is not None:
                result = changed
        return result

    def put_object(self, **request):
        def operation():
            assert set(request) <= {'Bucket','Key','Body','ContentLength','ContentType','Metadata','IfNoneMatch',
                                    'ChecksumSHA256','ExpectedBucketOwner'}
            assert request['IfNoneMatch'] == '*'
            assert type(request['Body']) is bytes and request['ContentLength'] == len(request['Body'])
            assert request['ChecksumSHA256'] == base64.b64encode(bytes.fromhex(sha256(request['Body']))).decode()
            identity = (request['Bucket'], request['Key'])
            if identity in self.current:
                raise ServiceError(412, 'PreconditionFailed')
            self.counter += 1
            version = 'v' + str(self.counter) if self.versioned else None
            value = dict(body=request['Body'], content_type=request['ContentType'],
                         metadata=dict(request['Metadata']), version_id=version)
            self.current[identity] = value
            self.versions[identity + (version,)] = value
            result = dict(ResponseMetadata=dict(HTTPStatusCode=200), ETag='opaque-not-a-sha256')
            if version is not None:
                result['VersionId'] = version
            return result
        return self._call('PutObject', request, operation)

    def get_object(self, **request):
        def operation():
            assert set(request) <= {'Bucket','Key','VersionId','ExpectedBucketOwner'}
            key = (request['Bucket'], request['Key'])
            value = self.versions.get(key + (request['VersionId'],)) if 'VersionId' in request else self.current.get(key)
            if value is None:
                raise ServiceError(404, 'NoSuchVersion' if 'VersionId' in request else 'NoSuchKey')
            result = dict(Body=io.BytesIO(value['body']), ContentLength=len(value['body']),
                ContentType=value['content_type'], Metadata=dict(value['metadata']), ResponseMetadata=dict(HTTPStatusCode=200))
            if value['version_id'] is not None:
                result['VersionId'] = value['version_id']
            return result
        return self._call('GetObject', request, operation)

    def list_objects_v2(self, **request):
        def operation():
            assert set(request) <= {'Bucket','Prefix','MaxKeys','ContinuationToken','ExpectedBucketOwner'}
            keys = sorted((k,v) for (b,k),v in self.current.items() if b == request['Bucket'] and k.startswith(request['Prefix']))
            start = int(request.get('ContinuationToken', 'page:0').split(':')[1])
            selected = keys[start:start+request['MaxKeys']]
            end = start + len(selected)
            result = dict(ResponseMetadata=dict(HTTPStatusCode=200), IsTruncated=end < len(keys),
                Name=request['Bucket'], Prefix=request['Prefix'], KeyCount=len(selected),
                Contents=[dict(Key=k, Size=len(v['body'])) for k,v in selected])
            if result['IsTruncated']:
                result['NextContinuationToken'] = 'page:' + str(end)
            return result
        return self._call('ListObjectsV2', request, operation)
