"""Offline atomic simulation only; no test constructs a cloud client."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import patch

from scripts.pipeline.release.evidence_store import (
    EvidenceStore, FrozenObject, MemoryTransport, MissingObject, PreconditionFailed,
    ReadStatus, StoredObject, TransportError, WriteResponseLost, WriteStatus,
)


class EvidenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.transport = MemoryTransport()
        self.store = EvidenceStore(self.transport)
        self.request = FrozenObject.freeze(b'{ "original": true }\n\x00\xff', {'kind': 'test', 'schema': '1'})

    def test_first_create_and_exact_retry(self):
        first = self.store.create_once('key', self.request)
        retry = self.store.create_once('key', self.request)
        self.assertEqual((first.status, retry.status), (WriteStatus.CREATED, WriteStatus.ALREADY_PRESENT_IDENTICAL))
        self.assertEqual(first.object, retry.object)
        self.assertEqual(first.object.content.data, self.request.data)

    def test_semantically_equal_json_is_a_content_conflict(self):
        self.store.create_once('key', FrozenObject.freeze(b'{"a":1}', {}))
        result = self.store.create_once('key', FrozenObject.freeze(b'{ "a": 1 }\n', {}))
        self.assertEqual(result.status, WriteStatus.CONFLICT)

    def test_application_metadata_is_content_and_input_is_frozen(self):
        metadata = {'purpose': 'original'}
        original = FrozenObject.freeze(b'bytes', metadata)
        metadata['purpose'] = 'changed'
        self.store.create_once('key', original)
        self.assertEqual(self.store.get('key').object.content.metadata, (('purpose', 'original'),))
        changed = FrozenObject.freeze(original.data, metadata)
        self.assertEqual(self.store.create_once('key', changed).status, WriteStatus.CONFLICT)

    def test_put_is_atomic_operation_before_readback_of_exact_version(self):
        events = []

        class Recorded(MemoryTransport):
            def put_if_absent(self, key, content):
                events.append(('put', key))
                return super().put_if_absent(key, content)

            def get(self, key, version_id=None):
                events.append(('get', version_id))
                return super().get(key, version_id)

        result = EvidenceStore(Recorded()).create_once('key', self.request)
        self.assertEqual(events, [('put', 'key'), ('get', result.object.version_id)])

    def test_lost_success_response_reconciles_existing_frozen_bytes(self):
        class Lost(MemoryTransport):
            def put_if_absent(self, key, content):
                super().put_if_absent(key, content)
                raise WriteResponseLost('response lost')

        result = EvidenceStore(Lost()).create_once('key', self.request)
        self.assertEqual(result.status, WriteStatus.ALREADY_PRESENT_IDENTICAL)
        self.assertEqual(result.object.content, self.request)

    def test_lost_response_with_different_content_is_conflict(self):
        class Lost(MemoryTransport):
            def put_if_absent(self, key, content):
                super().put_if_absent(key, FrozenObject.freeze(b'other', {}))
                raise WriteResponseLost('response lost')

        self.assertEqual(EvidenceStore(Lost()).create_once('key', self.request).status, WriteStatus.CONFLICT)

    def test_read_denied_and_timeout_never_mean_missing(self):
        for error in (TransportError('AccessDenied / 403'), TimeoutError('timeout')):
            with self.subTest(error=error), patch.object(self.transport, 'get', side_effect=error):
                self.assertEqual(self.store.get('key').status, ReadStatus.ERROR)

    def test_specific_missing_version_has_no_latest_fallback(self):
        self.store.create_once('key', self.request)
        with patch.object(self.transport, 'get', wraps=self.transport.get) as get:
            self.assertEqual(self.store.get('key', 'absent-version').status, ReadStatus.MISSING)
        get.assert_called_once_with('key', 'absent-version')

    def test_transport_returning_wrong_version_is_error(self):
        created = self.store.create_once('key', self.request)
        with patch.object(self.transport, 'get', return_value=created.object):
            self.assertEqual(self.store.get('key', 'another-version').status, ReadStatus.ERROR)

    def test_s3_409_is_operational_error_not_content_conflict(self):
        with patch.object(self.transport, 'put_if_absent', side_effect=TransportError('ConditionalRequestConflict / 409')):
            result = self.store.create_once('key', self.request)
        self.assertEqual(result.status, WriteStatus.ERROR)
        self.assertEqual(self.store.get('key').status, ReadStatus.MISSING)

    def test_failed_reconciliation_is_error(self):
        for error in (MissingObject('gone after 412'), TransportError('denied'), TimeoutError('timeout')):
            with self.subTest(error=error), patch.object(self.transport, 'put_if_absent', side_effect=PreconditionFailed()), \
                    patch.object(self.transport, 'get', side_effect=error):
                self.assertEqual(self.store.create_once('key', self.request).status, WriteStatus.ERROR)

    def test_corrupt_readback_prevents_created(self):
        wrong = StoredObject(FrozenObject.freeze(b'changed', {}), 'memory-1')
        with patch.object(self.transport, 'get', return_value=wrong):
            self.assertEqual(self.store.create_once('key', self.request).status, WriteStatus.ERROR)

    def _concurrent(self, different):
        count, barrier = 8, Barrier(8)

        def write(index):
            barrier.wait(timeout=5)
            request = FrozenObject.freeze(str(index).encode(), {}) if different else self.request
            return self.store.create_once('key', request)

        with ThreadPoolExecutor(max_workers=count) as workers:
            results = list(workers.map(write, range(count)))
        self.assertEqual(sum(r.status == WriteStatus.CREATED for r in results), 1)
        other = WriteStatus.CONFLICT if different else WriteStatus.ALREADY_PRESENT_IDENTICAL
        self.assertEqual(sum(r.status == other for r in results), count - 1)
        winner = next(r for r in results if r.status == WriteStatus.CREATED)
        self.assertEqual(self.store.get('key').object, winner.object)

    def test_concurrent_identical_writers(self):
        self._concurrent(False)

    def test_concurrent_different_writers(self):
        self._concurrent(True)

    def test_no_transport_defaults_or_implicit_credentials(self):
        with patch('subprocess.run', side_effect=AssertionError('implicit process')), \
                patch('socket.socket', side_effect=AssertionError('implicit network')):
            store = EvidenceStore(MemoryTransport())
            self.assertEqual(store.create_once('key', self.request).status, WriteStatus.CREATED)
        with self.assertRaises(TypeError):
            EvidenceStore()

    def test_inventory_denied_incomplete_or_unbounded_is_error(self):
        with patch.object(self.transport, 'keys', side_effect=TransportError('denied')):
            self.assertEqual(self.store.keys('prefix/').status, ReadStatus.ERROR)
        for keys in (('wrong-prefix',), ('prefix/b', 'prefix/a'), ('prefix/a', 1),
                     tuple('prefix/' + str(i) for i in range(4097))):
            with self.subTest(keys=len(keys)), patch.object(self.transport, 'keys', return_value=keys):
                self.assertEqual(self.store.keys('prefix/').status, ReadStatus.ERROR)

    def test_no_overwrite_or_delete_interface(self):
        self.assertFalse(hasattr(self.store, 'put'))
        self.assertFalse(hasattr(self.store, 'delete'))

    def test_invalid_mutable_or_duplicate_request_metadata_rejected(self):
        for data, metadata in ((bytearray(b'a'), ()), (b'a', (('a', '1'), ('a', '1'))), (b'a', (('a', 1),))):
            with self.subTest(data=data, metadata=metadata), self.assertRaises(ValueError):
                FrozenObject(data, metadata)
