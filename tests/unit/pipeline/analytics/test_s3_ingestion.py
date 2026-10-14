from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
from threading import Barrier
import unittest

from scripts.pipeline.analytics.ingestion_types import Destination, FrozenObject, IngestionError, Limits, object_bytes
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from tests.unit.pipeline.analytics.s3_support import FakeS3, ServiceError


class S3IngestionTests(unittest.TestCase):
    def setUp(self):
        self.target = Destination('analytics-example', 'offline/poc', 'test-region-1', '000000000000')
        self.client = FakeS3()
        self.store = S3Adapter(self.client, self.target)
        self.request = object_bytes('reports/records.json', b'{"value":1}', 'a'*64)
        self.key = self.target.snapshot_prefix('b'*64) + self.request.path

    def test_construction_and_requests_have_no_implicit_client_or_calls(self):
        self.assertEqual(self.client.calls, [])
        with self.assertRaises(IngestionError):S3Adapter(None, self.target)
        with self.assertRaisesRegex(IngestionError,'CLIENT_REGION_DIFFERS'):
            S3Adapter(FakeS3('another-region-1'),self.target)
        self.assertEqual(self.client.calls, [])

    def test_conditional_first_create_and_identical_retry_compare_exact_bytes_and_metadata(self):
        self.assertEqual(self.store.create(self.key,self.request)[0], 'CREATED')
        self.assertEqual(self.store.create(self.key,self.request)[0], 'ALREADY_PRESENT_IDENTICAL')
        puts = [r for op,r in self.client.calls if op == 'PutObject']
        self.assertEqual(len(puts),2)
        self.assertTrue(all(r['IfNoneMatch'] == '*' and r['ExpectedBucketOwner'] == '000000000000' for r in puts))
        self.assertEqual(self.client.calls[0][0], 'PutObject')  # No HEAD/GET as substitute for conditional PUT.
        self.assertIn('VersionId',self.client.calls[1][1])

    def test_semantically_equal_json_with_different_bytes_is_content_conflict(self):
        self.store.create(self.key,self.request)
        other = object_bytes(self.request.path,b'{ "value": 1 }','a'*64)
        with self.assertRaisesRegex(IngestionError,'CONTENT_CONFLICT'):self.store.create(self.key,other)

    def test_application_metadata_and_content_type_are_part_of_identity(self):
        self.store.create(self.key,self.request)
        for other in (replace(self.request,metadata={'purpose':'different'}),
                      replace(self.request,content_type='application/vnd.apache.parquet')):
            with self.assertRaisesRegex(IngestionError,'CONTENT_CONFLICT'):self.store.create(self.key,other)

    def test_metadata_is_frozen_before_original_mapping_mutates(self):
        metadata = {'purpose':'original'}
        request = FrozenObject(self.request.path,b'bytes','application/json',metadata)
        metadata['purpose'] = 'mutated'
        self.assertEqual(dict(request.metadata),{'purpose':'original'})
        _,read = self.store.create(self.key,request)
        self.assertEqual(dict(read.metadata),{'purpose':'original'})

    def test_lost_success_response_reconciles_existing_bytes(self):
        def lost(operation,request,response):
            if operation == 'PutObject':raise TimeoutError('SECRET signed URL')
        self.client.after = lost
        status,value = self.store.create(self.key,self.request)
        self.assertEqual(status,'ALREADY_PRESENT_IDENTICAL')
        self.assertEqual(value.body,self.request.body)

    def test_lost_response_and_denied_recovery_is_error_not_absence_or_success(self):
        self.client.after = lambda op,r,v: (_ for _ in ()).throw(TimeoutError()) if op == 'PutObject' else None
        self.client.before = lambda op,r: (_ for _ in ()).throw(ServiceError(403,'AccessDenied')) if op == 'GetObject' else None
        with self.assertRaisesRegex(IngestionError,'WRITE_OUTCOME_UNKNOWN'):self.store.create(self.key,self.request)

    def test_write_timeout_without_created_object_is_retryable_error(self):
        self.client.before = lambda op,r: (_ for _ in ()).throw(TimeoutError()) if op == 'PutObject' else None
        with self.assertRaisesRegex(IngestionError,'WRITE_OUTCOME_UNKNOWN') as error:self.store.create(self.key,self.request)
        self.assertTrue(error.exception.retryable)

    def test_only_no_such_key_404_is_current_object_absence(self):
        self.assertIsNone(self.store.get(self.key))
        for status,code in ((403,'AccessDenied'),(404,'NoSuchBucket'),(500,'InternalError')):
            self.client.before = lambda op,r,s=status,c=code: (_ for _ in ()).throw(ServiceError(s,c))
            with self.subTest(code=code), self.assertRaises(IngestionError):self.store.get(self.key)
        self.client.before = lambda op,r: (_ for _ in ()).throw(ServiceError(404,'NoSuchBucket'))
        with self.assertRaisesRegex(IngestionError,'TRANSPORT_ERROR'):self.store.get(self.key,'requested-version')

    def test_requested_version_unavailable_never_falls_back_to_latest(self):
        self.store.create(self.key,self.request)
        before = len(self.client.calls)
        with self.assertRaisesRegex(IngestionError,'VERSION_UNAVAILABLE'):self.store.get(self.key,'missing-version')
        self.assertEqual(len(self.client.calls),before+1)
        self.assertEqual(self.client.calls[-1][1]['VersionId'],'missing-version')

    def test_wrong_returned_version_is_rejected(self):
        self.store.create(self.key,self.request)
        self.client.after = lambda op,r,v: dict(v,VersionId='wrong') if op == 'GetObject' else None
        with self.assertRaisesRegex(IngestionError,'VERSION_DIFFERS'):self.store.get(self.key,'v1')

    def test_truncated_or_extended_stream_is_rejected(self):
        self.store.create(self.key,self.request)
        for body in (b'x',self.request.body+b'extra'):
            self.client.after = lambda op,r,v,b=body: dict(v,Body=io.BytesIO(b)) if op == 'GetObject' else None
            with self.assertRaises(IngestionError):self.store.get(self.key)

    def test_changed_readback_does_not_use_etag_or_writer_metadata_as_proof(self):
        def changed(op,r,v):
            if op == 'GetObject':return dict(v,Body=io.BytesIO(b'x'*len(self.request.body)))
        self.client.after = changed
        with self.assertRaisesRegex(IngestionError,'CONTENT_CONFLICT'):self.store.create(self.key,self.request)

    def test_409_conditional_request_conflict_retries_frozen_conditional_put(self):
        remaining = [1]
        def conflict(op,r):
            if op == 'PutObject' and remaining[0]:
                remaining[0] -= 1
                raise ServiceError(409,'ConditionalRequestConflict')
        self.client.before = conflict
        self.assertEqual(self.store.create(self.key,self.request)[0],'CREATED')
        puts = [r for op,r in self.client.calls if op == 'PutObject']
        self.assertEqual(puts[0],puts[1])

    def test_409_exhaustion_or_other_409_is_operational_error(self):
        for code in ('ConditionalRequestConflict','OperationAborted'):
            self.client.before = lambda op,r,c=code: (_ for _ in ()).throw(ServiceError(409,c))
            with self.subTest(code=code),self.assertRaises(IngestionError) as error:self.store.create(self.key,self.request)
            self.assertNotEqual(error.exception.code,'CONTENT_CONFLICT')

    def test_concurrent_equal_and_different_writers_use_adapter_boundary(self):
        for different in (False,True):
            client = FakeS3(); store = S3Adapter(client,self.target); barrier = Barrier(2)
            other = object_bytes(self.request.path,b'different','a'*64) if different else self.request
            def write(request):
                barrier.wait(timeout=5)
                try:return store.create(self.key,request)[0]
                except IngestionError as error:return error.code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(write,(self.request,other)))
            self.assertEqual(sorted(results),sorted(['CREATED','CONTENT_CONFLICT' if different else 'ALREADY_PRESENT_IDENTICAL']))

    def test_owner_optional_and_unversioned_objects_are_explicit(self):
        target = replace(self.target,expected_bucket_owner=None)
        client = FakeS3(versioned=False); store = S3Adapter(client,target)
        status,read = store.create(self.key,self.request)
        self.assertEqual(status,'CREATED');self.assertIsNone(read.version_id)
        self.assertNotIn('ExpectedBucketOwner',client.calls[0][1])

    def test_unauthorized_prefix_and_destination_are_rejected_without_client_calls(self):
        for key in ('elsewhere/snapshots/'+'b'*64+'/reports/records.json', self.key+'/extra',self.key.replace('/reports/','/../')):
            with self.assertRaises(IngestionError):self.store.create(key,self.request)
        with self.assertRaises(IngestionError):self.store.authorize(replace(self.target,bucket='another-bucket'))
        self.assertEqual(self.client.calls,[])

    def test_list_pagination_is_complete_and_limited(self):
        store = S3Adapter(self.client,self.target,Limits(page_size=1))
        store.create(self.key,self.request)
        other = object_bytes('reports/normalization.json',b'{}','a'*64)
        store.create(self.target.snapshot_prefix('b'*64)+other.path,other)
        self.assertEqual(len(store.list_snapshot('b'*64)),2)
        self.assertEqual(len([1 for op,r in self.client.calls if op=='ListObjectsV2']),2)
        limited = S3Adapter(self.client,self.target,Limits(page_size=1,pages=1))
        with self.assertRaisesRegex(IngestionError,'LIST_LIMIT'):limited.list_snapshot('b'*64)

    def test_list_duplicates_foreign_keys_bad_tokens_and_incomplete_responses_rejected(self):
        self.store.create(self.key,self.request)
        for mode in ('duplicate','foreign','token','inconclusive'):
            def corrupt(op,r,v):
                if op != 'ListObjectsV2':return None
                if mode == 'duplicate':v['Contents'] *= 2;v['KeyCount'] = 2
                elif mode == 'foreign':v['Contents'][0]['Key'] = 'outside/prefix'
                elif mode == 'token':v['IsTruncated'] = True;v['NextContinuationToken'] = 'same'
                else:v.pop('IsTruncated')
                return v
            self.client.after = corrupt
            with self.subTest(mode=mode),self.assertRaises(IngestionError):self.store.list_snapshot('b'*64)
