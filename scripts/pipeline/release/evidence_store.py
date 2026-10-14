"""Create-once byte storage. No default transport, credentials or cloud client.

Application metadata is content; version IDs and service response metadata are
not. A transport must implement atomic put_if_absent, not HEAD followed by PUT.
This module deliberately has no overwrite, delete or implicit latest fallback.
"""
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Mapping, Optional, Protocol, Tuple


class MissingObject(Exception):
    """An explicitly absent key/version, never an access-denied response."""


class PreconditionFailed(Exception):
    """The conditional create found an existing object (S3 412)."""


class TransportError(Exception):
    """Denied, timeout, S3 409, or another inconclusive operation."""


class WriteResponseLost(TransportError):
    """A create may have succeeded; reconcile without overwriting."""


def metadata_pairs(metadata):
    if not isinstance(metadata, Mapping) or not all(
            type(k) is str and k and type(v) is str for k, v in metadata.items()):
        raise ValueError('application metadata must map nonempty strings to strings')
    return tuple(sorted(metadata.items()))


@dataclass(frozen=True)
class FrozenObject:
    data: bytes
    metadata: Tuple[Tuple[str, str], ...]

    @classmethod
    def freeze(cls, data, metadata):
        if type(data) is not bytes:
            raise ValueError('immutable bytes required')
        return cls(data, metadata_pairs(metadata))

    def __post_init__(self):
        if (type(self.data) is not bytes or type(self.metadata) is not tuple
                or self.metadata != metadata_pairs(dict(self.metadata))):
            raise ValueError('invalid frozen object')


@dataclass(frozen=True)
class StoredObject:
    content: FrozenObject
    version_id: str

    def __post_init__(self):
        if not isinstance(self.content, FrozenObject) or type(self.version_id) is not str or not self.version_id:
            raise ValueError('stored object requires content and a version ID')


class Transport(Protocol):
    def get(self, key: str, version_id: Optional[str] = None) -> StoredObject:
        ...

    def put_if_absent(self, key: str, content: FrozenObject) -> str:
        ...

    def keys(self, prefix: str) -> Tuple[str, ...]:
        ...


class ReadStatus(str, Enum):
    FOUND = 'FOUND'
    MISSING = 'MISSING'
    ERROR = 'ERROR'


class WriteStatus(str, Enum):
    CREATED = 'CREATED'
    ALREADY_PRESENT_IDENTICAL = 'ALREADY_PRESENT_IDENTICAL'
    CONFLICT = 'CONFLICT'
    ERROR = 'ERROR'


@dataclass(frozen=True)
class ReadResult:
    status: ReadStatus
    object: Optional[StoredObject] = None
    reason: str = ''


@dataclass(frozen=True)
class WriteResult:
    status: WriteStatus
    object: Optional[StoredObject] = None
    reason: str = ''


@dataclass(frozen=True)
class InventoryResult:
    status: ReadStatus
    keys: Tuple[str, ...] = ()
    reason: str = ''


class EvidenceStore:
    def __init__(self, transport: Transport):
        self.transport = transport

    def get(self, key, version_id=None):
        try:
            obj = self.transport.get(key, version_id)
            if not isinstance(obj, StoredObject) or (version_id is not None and obj.version_id != version_id):
                raise TransportError('transport returned another version or invalid object')
            return ReadResult(ReadStatus.FOUND, obj)
        except MissingObject as error:
            return ReadResult(ReadStatus.MISSING, reason=str(error))
        except (TransportError, OSError, TimeoutError) as error:
            return ReadResult(ReadStatus.ERROR, reason=str(error))

    def keys(self, prefix):
        try:
            keys = self.transport.keys(prefix)
            if (type(keys) is not tuple or len(keys) > 4096
                    or any(type(key) is not str or not key.startswith(prefix) for key in keys)
                    or keys != tuple(sorted(set(keys)))):
                raise TransportError('invalid/incomplete bounded inventory')
            return InventoryResult(ReadStatus.FOUND, keys)
        except (TransportError, OSError, TimeoutError) as error:
            return InventoryResult(ReadStatus.ERROR, reason=str(error))

    def create_once(self, key, content):
        if not isinstance(content, FrozenObject):
            raise ValueError('freeze the request before creation')
        try:
            version = self.transport.put_if_absent(key, content)
        except (PreconditionFailed, WriteResponseLost):
            result = self.get(key)
            if result.status != ReadStatus.FOUND:
                return WriteResult(WriteStatus.ERROR, reason='conditional create cannot be reconciled: ' + result.reason)
            if result.object.content != content:
                return WriteResult(WriteStatus.CONFLICT, result.object, 'existing bytes/application metadata differ')
            return WriteResult(WriteStatus.ALREADY_PRESENT_IDENTICAL, result.object)
        except (TransportError, OSError, TimeoutError) as error:
            return WriteResult(WriteStatus.ERROR, reason=str(error))
        if type(version) is not str or not version:
            return WriteResult(WriteStatus.ERROR, reason='create returned no version ID')
        result = self.get(key, version_id=version)
        if result.status != ReadStatus.FOUND or result.object.content != content:
            return WriteResult(WriteStatus.ERROR, reason='created object read-back failed: ' + result.reason)
        return WriteResult(WriteStatus.CREATED, result.object)


class MemoryTransport:
    """Isolated process-local simulation, not proof of S3 enforcement."""

    def __init__(self):
        self._lock = Lock()
        self._objects = {}
        self._sequence = 0

    def get(self, key, version_id=None):
        with self._lock:
            obj = self._objects.get(key)
            if obj is None or (version_id is not None and obj.version_id != version_id):
                raise MissingObject('key/version absent')
            return obj

    def put_if_absent(self, key, content):
        with self._lock:
            if key in self._objects:
                raise PreconditionFailed('already present')
            self._sequence += 1
            version = f'memory-{self._sequence}'
            self._objects[key] = StoredObject(content, version)
            return version

    def keys(self, prefix):
        with self._lock:
            return tuple(sorted(key for key in self._objects if key.startswith(prefix)))
