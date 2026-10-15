"""Offline transport conformance for HGC-04 against a TEST-ONLY S3 reference model.

No cloud client, credential or network is used. Passing here specifies the
mapping a future adapter must satisfy; it is not evidence of applied S3
controls, retention, IAM or hosted behaviour.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from scripts.pipeline.release import evidence_custody as custody
from scripts.pipeline.release.evidence_store import EvidenceStore, FrozenObject, ReadStatus, WriteStatus
from tests.unit.pipeline.release.custody_support import (
    TestAuthenticator, TestSigner, frozen_fixture, prepared_fixture,
)
from tests.unit.pipeline.release.s3_reference_model import FakeBucket, ReferenceTransport, S3Error


class TransportConformanceTests(unittest.TestCase):
    def setUp(self):
        self.bucket = FakeBucket()
        self.store = EvidenceStore(ReferenceTransport(self.bucket))
        self.request = FrozenObject.freeze(b'{ "original": true }\n\x00\xff', {'kind': 'test', 'sha256': '0' * 64})

    def test_create_once_contract_holds_with_s3_version_ids(self):
        first = self.store.create_once('key', self.request)
        retry = self.store.create_once('key', self.request)
        self.assertEqual((first.status, retry.status), (WriteStatus.CREATED, WriteStatus.ALREADY_PRESENT_IDENTICAL))
        self.assertEqual(first.object, retry.object)
        self.assertNotEqual(first.object.version_id, 'null')
        for other in (FrozenObject.freeze(b'other', dict(self.request.metadata)),
                      FrozenObject.freeze(self.request.data, {'kind': 'other', 'sha256': '0' * 64})):
            self.assertEqual(self.store.create_once('key', other).status, WriteStatus.CONFLICT)
        self.assertEqual(self.store.get('key', first.object.version_id).object.content, self.request)

    def test_concurrent_conditional_writers_create_exactly_once(self):
        barrier = Barrier(8)

        def write(index):
            barrier.wait(timeout=5)
            return self.store.create_once('key', self.request if index % 2 else FrozenObject.freeze(b'x%d' % index, {}))

        with ThreadPoolExecutor(max_workers=8) as workers:
            results = [r.status for r in workers.map(write, range(8))]
        self.assertEqual(results.count(WriteStatus.CREATED), 1)
        self.assertEqual(len(self.bucket.versions['key']), 1)

    def test_409_lost_race_is_an_operational_error_and_retry_creates(self):
        with patch.object(self.bucket, 'put_object', side_effect=S3Error(409, 'ConditionalRequestConflict')):
            self.assertEqual(self.store.create_once('key', self.request).status, WriteStatus.ERROR)
        self.assertEqual(self.store.create_once('key', self.request).status, WriteStatus.CREATED)

    def test_reset_after_sending_is_reconciled_never_assumed(self):
        put = self.bucket.put_object
        for persisted, expected in ((False, WriteStatus.ERROR), (True, WriteStatus.ALREADY_PRESENT_IDENTICAL)):
            with self.subTest(persisted=persisted):
                def reset(key, body, metadata, if_none_match):
                    if persisted:
                        put(key, body, metadata, if_none_match)
                    raise ConnectionResetError('connection reset by peer')
                with patch.object(self.bucket, 'put_object', side_effect=reset):
                    self.assertEqual(self.store.create_once(f'key-{persisted}', self.request).status, expected)

    def test_missing_key_without_list_permission_is_error_never_absence(self):
        self.bucket.list_permission = False
        self.assertEqual(self.store.get('absent').status, ReadStatus.ERROR)
        self.bucket.list_permission = True
        self.assertEqual(self.store.get('absent').status, ReadStatus.MISSING)

    def test_unversioned_or_suspended_buckets_never_establish_custody(self):
        for versioning in ('Suspended', 'Disabled'):
            with self.subTest(versioning=versioning):
                bucket = FakeBucket(versioning=versioning)
                store = EvidenceStore(ReferenceTransport(bucket))
                self.assertEqual(store.create_once('key', self.request).status, WriteStatus.ERROR)
                self.assertEqual(store.create_once('key', self.request).status, WriteStatus.ERROR)
                # Why "null" can never be a pin: the same version ID now names other bytes.
                bucket.delete_object('key')
                bucket.put_object('key', b'replacement', {}, if_none_match=True)
                self.assertEqual(bucket.get_object('key', 'null')['body'], b'replacement')

    def test_version_pin_survives_delete_marker_and_recreation(self):
        created = self.store.create_once('key', self.request)
        self.bucket.delete_object('key')
        self.assertEqual(self.store.get('key').status, ReadStatus.MISSING)
        # S3 accepts a new conditional write over a delete marker: create-once is
        # not delete protection. Only the exact pinned version keeps the bytes.
        replacement = FrozenObject.freeze(b'replacement', dict(self.request.metadata))
        self.assertEqual(self.store.create_once('key', replacement).status, WriteStatus.CREATED)
        self.assertEqual(self.store.get('key', created.object.version_id).object.content, self.request)
        self.assertEqual(self.store.create_once('key', self.request).status, WriteStatus.CONFLICT)
        marker = self.bucket.versions['key'][1]['version_id']
        self.assertEqual(self.store.get('key', marker).status, ReadStatus.ERROR)  # 405, not MISSING

    def test_listing_is_complete_across_pages_or_an_error(self):
        bucket = FakeBucket(page_size=3)
        for index in range(10):
            bucket.put_object(f'prefix/{index:02d}', b'x', {}, if_none_match=True)
        bucket.put_object('other/key', b'x', {}, if_none_match=True)
        self.assertEqual(EvidenceStore(ReferenceTransport(bucket)).keys('prefix/').keys,
                         tuple(f'prefix/{index:02d}' for index in range(10)))
        self.assertEqual(EvidenceStore(ReferenceTransport(bucket, max_keys=9)).keys('prefix/').status, ReadStatus.ERROR)
        bucket.exists = False
        self.assertEqual(EvidenceStore(ReferenceTransport(bucket)).keys('prefix/').status, ReadStatus.ERROR)

    def test_metadata_s3_would_rewrite_is_refused_before_writing(self):
        for metadata in ({'Kind': 'test'}, {'kind': 'tést'}, {'kind': 'line\nbreak'}, {'kind': 'x' * 2048}):
            with self.subTest(metadata=sorted(metadata)), patch.object(self.bucket, 'put_object') as put:
                self.assertEqual(self.store.create_once('key', FrozenObject.freeze(b'x', metadata)).status,
                                 WriteStatus.ERROR)
                put.assert_not_called()

    def test_custody_completes_and_recovers_on_the_reference_model(self):
        prepared, expected = prepared_fixture()
        signer = TestSigner()
        self.addCleanup(signer.close)
        with tempfile.TemporaryDirectory(prefix='hgc04-conformance-') as temporary:
            root = Path(temporary).resolve()
            frozen = frozen_fixture(self.store, prepared, expected, signer)
            result = custody.commit_record(self.store, frozen, expected, signer.policy(), TestAuthenticator(), root / 'finalize')
            self.assertEqual(result.status, WriteStatus.CREATED)
            read = custody.recover(self.store, expected, signer.policy(), TestAuthenticator(), root / 'read')
            self.assertEqual((read.state, read.profile, read.production_authority),
                             (custody.CustodyState.COMPLETE_VERIFIED, 'TEST_ONLY', False))
            self.bucket.list_permission = False
            other = custody.recover(self.store, custody.ExpectedIdentity.freeze(dict(
                expected.value, run_attempt=2, release_id=f'r{expected.value["run_id"]}-a2',
                publisher=dict(expected.value['publisher'], run_attempt=2))),
                signer.policy(), TestAuthenticator(), root / 'unknown')
            self.assertEqual(other.state, custody.CustodyState.ERROR)  # 403 is not "no custody".


if __name__ == '__main__':
    unittest.main()
