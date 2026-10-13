"""TEST-ONLY reference model of the S3 semantics that matter to HGC-04.

Not an adapter: no SDK, endpoint or credential exists here, and production
code never imports it. FakeBucket models documented server outcomes;
ReferenceTransport is the mapping a future, separately approved adapter must
implement (docs/hgc04-evidence-custody.md, "Transport conformance"):

* PutObject + If-None-Match: * -> 412 while a current version exists, but
  success when the current version is a delete marker; 409 when a concurrent
  delete wins (retryable). Concurrent conditional writes: first finisher wins.
* GetObject -> 404 for a missing key only with s3:ListBucket, otherwise 403;
  405 for a versionId that is a delete marker.
* Versioning suspended/never enabled -> version ID "null", and a later PUT
  replaces that version's bytes: "null" never pins content.
* User metadata keys are stored lowercase; values should be US-ASCII; 2 KB.
* ListObjectsV2 returns at most 1,000 keys per page (IsTruncated + token).
"""
import itertools
from threading import Lock

from scripts.pipeline.release.evidence_store import (
    FrozenObject, MissingObject, PreconditionFailed, StoredObject, TransportError, WriteResponseLost,
)

METADATA_BYTES = 2048


class S3Error(Exception):
    def __init__(self, status, code):
        super().__init__(f'{status} {code}')
        self.status, self.code = status, code


class FakeBucket:
    """Server-side behaviour only. Tests inject faults and administrator deletes."""

    def __init__(self, versioning='Enabled', list_permission=True, page_size=1000):
        self.versioning, self.list_permission, self.page_size = versioning, list_permission, page_size
        self.exists = True
        self.versions = {}
        self._ids = itertools.count(1)
        self._lock = Lock()

    def _store(self, key, entry):
        versions = self.versions.setdefault(key, [])
        if entry['version_id'] == 'null':  # The null slot is replaced, not versioned.
            versions[:] = [item for item in versions if item['version_id'] != 'null']
        versions.append(entry)

    def _bucket(self):
        if not self.exists:
            raise S3Error(404, 'NoSuchBucket')

    def put_object(self, key, body, metadata, if_none_match):
        with self._lock:
            self._bucket()
            versions = self.versions.get(key)
            if if_none_match and versions and not versions[-1]['delete_marker']:
                raise S3Error(412, 'PreconditionFailed')
            version = f'3sL4kqtJlcpXroDTDmJ+rmSpXd3dIbrHY{next(self._ids):05d}' if self.versioning == 'Enabled' else 'null'
            self._store(key, dict(version_id=version, body=body, delete_marker=False,
                                  metadata={name.lower(): value for name, value in metadata.items()}))
            return None if self.versioning == 'Disabled' else version

    def delete_object(self, key):
        """Administrator action: a delete marker (or the null slot) becomes current."""
        with self._lock:
            version = f'3sL4kqtJlcpXroDTDmJ+rmSpXd3dIbrHY{next(self._ids):05d}' if self.versioning == 'Enabled' else 'null'
            self._store(key, dict(version_id=version, body=None, delete_marker=True, metadata={}))

    def get_object(self, key, version_id=None):
        with self._lock:
            self._bucket()
            versions = self.versions.get(key, [])
            if version_id is None:
                if not versions or versions[-1]['delete_marker']:
                    raise S3Error(404, 'NoSuchKey') if self.list_permission else S3Error(403, 'AccessDenied')
                return dict(versions[-1])
            entry = next((item for item in versions if item['version_id'] == version_id), None)
            if entry is None:
                raise S3Error(404, 'NoSuchVersion')
            if entry['delete_marker']:
                raise S3Error(405, 'MethodNotAllowed')
            return dict(entry)

    def list_objects_v2(self, prefix, token=None):
        with self._lock:
            self._bucket()
            if not self.list_permission:
                raise S3Error(403, 'AccessDenied')
            keys = sorted(key for key, versions in self.versions.items()
                          if key.startswith(prefix) and not versions[-1]['delete_marker'])
            start = int(token or 0)
            truncated = start + self.page_size < len(keys)
            return dict(keys=keys[start:start + self.page_size], truncated=truncated,
                        token=str(start + self.page_size) if truncated else None)


def _pinned(version_id):
    if type(version_id) is not str or not version_id or version_id == 'null':
        raise TransportError('object version does not pin content; bucket versioning must be Enabled')
    return version_id


class ReferenceTransport:
    """Executable statement of the adapter mapping; see the module docstring."""

    def __init__(self, bucket, max_keys=4096):
        self.bucket, self.max_keys = bucket, max_keys

    def put_if_absent(self, key, content):
        metadata = dict(content.metadata)
        if (any(name != name.lower() or not (name + value).isascii() or not (name + value).isprintable()
                for name, value in metadata.items())
                or sum(len(name.encode()) + len(value.encode()) for name, value in metadata.items()) > METADATA_BYTES):
            raise TransportError('application metadata would not round-trip through S3 exactly')
        try:
            version = self.bucket.put_object(key, content.data, metadata, if_none_match=True)
        except S3Error as error:
            if error.status == 412:
                raise PreconditionFailed(str(error)) from error
            raise TransportError(str(error)) from error  # 409 (lost race with a delete), 403, 5xx.
        except OSError as error:  # Reset/timeout after sending: the write may exist.
            raise WriteResponseLost(str(error)) from error
        return _pinned(version)

    def get(self, key, version_id=None):
        if version_id is not None:
            _pinned(version_id)
        try:
            entry = self.bucket.get_object(key, version_id)
        except S3Error as error:
            if error.code in ('NoSuchKey', 'NoSuchVersion'):
                raise MissingObject(str(error)) from error
            raise TransportError(str(error)) from error  # 403 is never absence; 405 is a delete marker.
        return StoredObject(FrozenObject.freeze(entry['body'], entry['metadata']), _pinned(entry['version_id']))

    def keys(self, prefix):
        keys, token = [], None
        while True:
            try:
                page = self.bucket.list_objects_v2(prefix, token)
            except S3Error as error:
                raise TransportError(str(error)) from error  # NoSuchBucket is not an empty inventory.
            keys += page['keys']
            if len(keys) > self.max_keys:
                raise TransportError('inventory exceeds its bound; a partial listing is never returned')
            if not page['truncated']:
                return tuple(keys)
            token = page['token']
