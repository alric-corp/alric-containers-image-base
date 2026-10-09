from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import shutil
from threading import Barrier
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics.catalog import catalog_plan
from scripts.pipeline.analytics.demo import demonstrate
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError, Limits, object_bytes
from scripts.pipeline.analytics.normalize import export, prepare, read_completed
from scripts.pipeline.analytics.snapshot import (
    load_plan, prepare_snapshot, publish_snapshot, read_snapshot, recover_snapshot, save_plan,
)
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics.fixture_support import historical, synthetic
from tests.unit.pipeline.analytics.s3_support import FakeS3, ServiceError


def refresh_inventory(batch):
    marker = json.loads((batch / 'complete.json').read_bytes())
    marker['files'] = [dict(path=p.relative_to(batch).as_posix(), size=p.stat().st_size, sha256=sha256(p.read_bytes()))
                       for p in sorted(batch.rglob('*')) if p.is_file() and p.name != 'complete.json']
    (batch / 'complete.json').write_bytes(canonical(marker))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sbom-snapshot-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = Destination('analytics-example', 'offline/poc', 'test-region-1', '000000000000')
        self.client = FakeS3()
        self.adapter = S3Adapter(self.client, self.target)
        self.batch = Path(export(prepare(synthetic(self.root / 'input')), self.root / 'output')['path'])
        self.plan = prepare_snapshot(self.batch, self.target)

    def marker_key(self, plan=None):
        return (plan or self.plan).key('ingestion-manifest.json')

    def test_complete_plan_freezes_every_original_byte_and_survives_preparation_mutation(self):
        other = prepare_snapshot(self.batch, self.target)
        self.assertEqual(self.plan, other)
        self.assertEqual(self.plan.snapshot_id, other.snapshot_id)
        for item in self.plan.objects:self.assertEqual(item.body, (self.batch / item.path).read_bytes())
        with self.assertRaises(FrozenInstanceError):self.plan.batch_id = '0'*64
        (self.batch / 'complete.json').write_bytes(b'changed after freezing')
        self.assertTrue(publish_snapshot(self.plan, self.adapter)['complete'])
        for item in read_snapshot(self.adapter, self.plan.snapshot_id).plan.objects:
            self.assertEqual(item.body, next(o.body for o in self.plan.objects if o.path == item.path))

    def test_frozen_plan_persists_exact_retry_request_without_preparation_paths(self):
        destination = self.root / 'frozen'
        self.assertEqual(save_plan(self.plan, destination), 'CREATED')
        self.assertEqual(save_plan(self.plan, destination), 'ALREADY_PRESENT_IDENTICAL')
        shutil.rmtree(self.root / 'input'); shutil.rmtree(self.root / 'output')
        self.assertEqual(load_plan(destination), self.plan)
        self.assertTrue(publish_snapshot(load_plan(destination), self.adapter)['complete'])
        value = json.loads((destination / 'plan.json').read_bytes())
        value['snapshot_id'] = '0'*64
        (destination / 'plan.json').write_bytes(canonical(value))
        with self.assertRaisesRegex(IngestionError, 'PLAN_CONTENT_DIFFERS'):load_plan(destination)

    def test_invalid_batch_is_rejected_before_any_transport(self):
        modes = ('missing', 'changed', 'extra', 'directory', 'symlink') + (('special',) if hasattr(os, 'mkfifo') else ())
        for mode in modes:
            batch = self.root / ('bad-' + mode); shutil.copytree(self.batch, batch)
            path = batch / 'reports/records.json'
            if mode == 'missing':path.unlink()
            elif mode == 'changed':path.write_bytes(path.read_bytes() + b'\n')
            elif mode == 'extra':(batch / 'unlisted.json').write_bytes(b'{}')
            elif mode == 'directory':(batch / 'empty-extra').mkdir()
            elif mode == 'symlink':path.unlink();path.symlink_to(self.batch / 'reports/records.json')
            else:
                path.unlink();os.mkfifo(path)
            with self.subTest(mode=mode), self.assertRaises(IngestionError):prepare_snapshot(batch, self.target)
        self.assertEqual(self.client.calls, [])

    def test_complete_marker_strict_schema_types_duplicates_paths_and_digests(self):
        original = (self.batch / 'complete.json').read_bytes()
        for mode in ('schema', 'boolean', 'duplicate', 'traversal', 'absolute', 'hash', 'size', 'extra-field', 'duplicate-json'):
            marker = json.loads(original)
            if mode == 'schema':marker['schema_version'] = 2
            elif mode == 'boolean':marker['schema_version'] = True
            elif mode == 'duplicate':marker['files'].append(marker['files'][0])
            elif mode == 'traversal':marker['files'][0]['path'] = '../secret'
            elif mode == 'absolute':marker['files'][0]['path'] = '/reports/records.json'
            elif mode == 'hash':marker['files'][0]['sha256'] = '0'*64
            elif mode == 'size':marker['files'][0]['size'] = True
            elif mode == 'extra-field':marker['unrecognized'] = True
            raw = canonical(marker) if mode != 'duplicate-json' else b'{"schema_version":1,"schema_version":1}'
            (self.batch / 'complete.json').write_bytes(raw)
            with self.subTest(mode=mode), self.assertRaises(IngestionError):prepare_snapshot(self.batch, self.target)
        self.assertEqual(self.client.calls, [])

    def test_reports_records_and_parquet_are_reconciled_not_only_hashed(self):
        for mode in ('report-count', 'report-version', 'report-authority', 'parquet-rows', 'records-identity'):
            batch = self.root / mode;shutil.copytree(self.batch, batch)
            if mode.startswith('report-'):
                path = batch / 'reports/normalization.json';value = json.loads(path.read_bytes())
                if mode == 'report-count':value['packages'] += 1
                elif mode == 'report-version':value['normalizer_version'] = 'unknown'
                else:value['publication_authority'] = True
                path.write_bytes(canonical(value))
            elif mode == 'parquet-rows':
                import pyarrow.parquet as pq
                path = batch / 'analytics/sbom_packages/part-00000.parquet'
                table = pq.ParquetFile(path).read();pq.write_table(table.slice(0, 1), path)
            else:
                path = batch / 'reports/records.json';value = json.loads(path.read_bytes())
                value['observations'][0]['run_id'] += 1;path.write_bytes(canonical(value))
            refresh_inventory(batch)
            with self.subTest(mode=mode), self.assertRaises(IngestionError):prepare_snapshot(batch, self.target)
        self.assertEqual(self.client.calls, [])

    def test_invalid_hand_built_frozen_plan_is_revalidated_before_transport(self):
        objects = tuple(object_bytes(o.path, b'{}' if o.path == 'reports/records.json' else o.body, self.plan.batch_id)
                        for o in self.plan.objects)
        plan = replace(self.plan, objects=objects)
        with self.assertRaises(IngestionError):publish_snapshot(plan, self.adapter)
        self.assertEqual(self.client.calls, [])

    def test_operational_and_parquet_expansion_limits_are_enforced(self):
        for limits in (Limits(object_bytes=1), Limits(snapshot_bytes=1), Limits(objects=2), Limits(parquet_expanded_bytes=1)):
            with self.subTest(limits=limits), self.assertRaises(IngestionError):prepare_snapshot(self.batch, self.target, limits)
        for limits in (Limits(object_bytes=1), Limits(objects=2), Limits(parquet_expanded_bytes=1)):
            with self.assertRaises(IngestionError):publish_snapshot(self.plan, S3Adapter(self.client, self.target, limits))
        self.assertEqual(self.client.calls, [])

    def test_first_upload_and_retry_are_byte_identical_with_no_new_puts_on_complete_retry(self):
        created = publish_snapshot(self.plan, self.adapter)
        self.assertEqual(created['code'], 'SNAPSHOT_CREATED')
        puts = sum(op == 'PutObject' for op,r in self.client.calls)
        self.assertEqual(puts, len(self.plan.objects)+1)
        retry = publish_snapshot(self.plan, self.adapter)
        self.assertEqual(retry['code'], 'SNAPSHOT_ALREADY_PRESENT_IDENTICAL')
        self.assertEqual(puts, sum(op == 'PutObject' for op,r in self.client.calls))
        verified = read_snapshot(self.adapter, self.plan.snapshot_id)
        manifest = json.loads(verified.manifest.body)
        self.assertEqual(manifest['batch_id'], self.plan.batch_id)
        self.assertEqual(manifest['authentication'], 'NOT_REVALIDATED')
        self.assertIs(manifest['publication_authority'], False)
        self.assertTrue(all(r['version_id'] is not None for r in manifest['files']))
        self.assertEqual(manifest['observations'], read_completed(self.batch)['observations'])

    def test_different_parquet_bytes_keep_logical_batch_but_get_different_publication(self):
        import pyarrow.parquet as pq
        batch = self.root / 'different-serialization';shutil.copytree(self.batch, batch)
        for table in ('observations', 'packages'):
            path = batch / ('analytics/sbom_' + table + '/part-00000.parquet')
            original = pq.ParquetFile(path).read()
            pq.write_table(original, path, version='2.6', compression='gzip', use_compliant_nested_type=True)
        refresh_inventory(batch)
        other = prepare_snapshot(batch, self.target)
        self.assertEqual(other.batch_id, self.plan.batch_id)
        self.assertNotEqual(other.snapshot_id, self.plan.snapshot_id)
        self.assertEqual(read_completed(batch), read_completed(self.batch))
        barrier = Barrier(2)
        def publish(plan):
            barrier.wait(timeout=5);return publish_snapshot(plan, self.adapter)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, (self.plan, other)))
        self.assertTrue(all(r['code'] == 'SNAPSHOT_CREATED' for r in results))

    def test_concurrent_identical_snapshot_writers_finalize_one_identical_manifest(self):
        barrier = Barrier(2)
        def publish(_):
            barrier.wait(timeout=5);return publish_snapshot(self.plan, self.adapter)
        with ThreadPoolExecutor(max_workers=2) as pool:results = list(pool.map(publish, (1,2)))
        self.assertEqual(sorted(r['code'] for r in results), ['SNAPSHOT_ALREADY_PRESENT_IDENTICAL','SNAPSHOT_CREATED'])
        self.assertTrue(read_snapshot(self.adapter, self.plan.snapshot_id).result('READBACK')['complete'])
        self.assertEqual(len(self.client.versions), len(self.plan.objects)+1)

    def test_existing_divergent_object_is_conflict_without_final_manifest(self):
        first = self.plan.objects[0]
        self.adapter.create(self.plan.key(first.path), replace(first, body=b'divergent'))
        with self.assertRaisesRegex(IngestionError, 'CONTENT_CONFLICT'):publish_snapshot(self.plan, self.adapter)
        self.assertNotIn((self.target.bucket, self.marker_key()), self.client.current)
        with self.assertRaises(IngestionError):catalog_plan(self.adapter, self.plan.snapshot_id, database='poc_test',table_prefix='poc_sbom')

    def test_partial_middle_failure_has_no_final_manifest_and_same_plan_resumes(self):
        key = self.plan.key(self.plan.objects[len(self.plan.objects)//2].path)
        def failure(op, request):
            if op == 'PutObject' and request['Key'] == key:raise ServiceError(503, 'SlowDown')
        self.client.before = failure
        with self.assertRaisesRegex(IngestionError, 'WRITE_OUTCOME_UNKNOWN'):publish_snapshot(self.plan, self.adapter)
        originals = dict(self.client.current)
        self.assertTrue(originals);self.assertNotIn((self.target.bucket, self.marker_key()), originals)
        with self.assertRaises(IngestionError):catalog_plan(self.adapter, self.plan.snapshot_id, database='poc_test', table_prefix='poc_sbom')
        self.client.before = None
        self.assertTrue(publish_snapshot(self.plan, self.adapter)['complete'])
        self.assertTrue(all(self.client.current[k] == v for k,v in originals.items()))

    def test_lost_success_responses_reconcile_including_final_manifest(self):
        def lost(op, request, response):
            if op == 'PutObject':raise TimeoutError('SECRET')
        self.client.after = lost
        result = publish_snapshot(self.plan, self.adapter)
        self.assertEqual(result['code'], 'SNAPSHOT_ALREADY_PRESENT_IDENTICAL')
        self.assertTrue(result['complete'])

    def test_final_readback_denied_never_returns_complete_or_eligible(self):
        finalized = [False]
        def after(op, request, response):
            if op == 'PutObject' and request['Key'] == self.marker_key():finalized[0] = True
        def before(op, request):
            if finalized[0] and op == 'GetObject':raise ServiceError(403, 'AccessDenied')
        self.client.after, self.client.before = after, before
        with self.assertRaisesRegex(IngestionError, 'ACCESS_DENIED'):publish_snapshot(self.plan, self.adapter)
        # An uploaded marker alone is not approval. Reconcile only by full read-back.
        self.assertIn((self.target.bucket, self.marker_key()), self.client.current)
        self.client.after = self.client.before = None
        self.assertEqual(publish_snapshot(self.plan, self.adapter)['code'], 'SNAPSHOT_ALREADY_PRESENT_IDENTICAL')

    def test_missing_payload_of_finalized_snapshot_is_not_automatically_repaired(self):
        publish_snapshot(self.plan, self.adapter)
        key = (self.target.bucket, self.plan.key(self.plan.objects[0].path))
        value = self.client.current.pop(key);self.client.versions.pop(key+(value['version_id'],))
        puts = sum(op == 'PutObject' for op,r in self.client.calls)
        with self.assertRaisesRegex(IngestionError, 'VERSION_UNAVAILABLE'):publish_snapshot(self.plan, self.adapter)
        self.assertEqual(puts, sum(op == 'PutObject' for op,r in self.client.calls))

    def test_athena_cannot_select_old_valid_version_when_current_object_changed(self):
        publish_snapshot(self.plan, self.adapter)
        key = (self.target.bucket, self.plan.key(self.plan.objects[0].path))
        old = self.client.current[key]
        self.client.current[key] = dict(old, version_id='new-current')
        with self.assertRaisesRegex(IngestionError, 'LATEST_VERSION_DIFFERS'):read_snapshot(self.adapter, self.plan.snapshot_id)

    def test_manifest_wrong_schema_hash_version_duplicate_path_and_authority_are_rejected(self):
        publish_snapshot(self.plan, self.adapter)
        key = (self.target.bucket, self.marker_key());original = self.client.current[key]
        for mode in ('schema', 'hash', 'version', 'duplicate', 'authority', 'unknown-field', 'duplicate-json'):
            value = json.loads(original['body'])
            if mode == 'schema':value['schema_version'] = True
            elif mode == 'hash':value['files'][0]['sha256'] = '0'*64
            elif mode == 'version':value['files'][0]['version_id'] = 'missing-version'
            elif mode == 'duplicate':value['files'].append(value['files'][0])
            elif mode == 'authority':value['publication_authority'] = True
            elif mode == 'unknown-field':value['unknown'] = 1
            body = canonical(value) if mode != 'duplicate-json' else b'{"schema_version":1,"schema_version":1}'
            self.client.current[key] = dict(original, body=body)
            with self.subTest(mode=mode), self.assertRaises(IngestionError):read_snapshot(self.adapter, self.plan.snapshot_id)

    def test_extra_remote_object_prevents_snapshot_approval_and_catalog_plan(self):
        publish_snapshot(self.plan, self.adapter)
        key = (self.target.bucket, self.plan.key('analytics/sbom_packages/unexpected.parquet'))
        self.client.current[key] = dict(body=b'PAR1',content_type='application/vnd.apache.parquet',metadata={},version_id='extra')
        with self.assertRaises(IngestionError):read_snapshot(self.adapter, self.plan.snapshot_id)
        with self.assertRaises(IngestionError):catalog_plan(self.adapter, self.plan.snapshot_id,database='poc_test',table_prefix='poc_sbom')
        self.assertIn(key, self.client.current)  # No orphan deletion.

    def test_wrong_bucket_prefix_or_owner_is_rejected_before_transport(self):
        for destination in (replace(self.target, bucket='different-bucket'), replace(self.target, prefix='another/poc'),
                            replace(self.target, expected_bucket_owner='111111111111')):
            with self.assertRaisesRegex(IngestionError, 'DESTINATION_NOT_AUTHORIZED'):
                publish_snapshot(replace(self.plan, destination=destination), self.adapter)
        self.assertEqual(self.client.calls, [])

    def test_pr_context_survives_without_becoming_published_or_stable(self):
        context = synthetic(self.root / 'pr');context['origin'].update(event='pull_request', ref='refs/pull/114/merge')
        batch = export(prepare(context), self.root / 'pr-output')['path']
        plan = prepare_snapshot(batch, self.target);publish_snapshot(plan,self.adapter)
        value = json.loads(read_snapshot(self.adapter,plan.snapshot_id).manifest.body)
        self.assertTrue(all(r['event'] == 'pull_request' and r['ref'] == 'refs/pull/114/merge'
                            and r['publication_authority'] is False for r in value['observations']))
        self.assertFalse(value['publication_authority'])

    def test_catalog_selection_is_explicit_and_only_exact_parquet_locations(self):
        publish_snapshot(self.plan, self.adapter)
        result = catalog_plan(self.adapter,self.plan.snapshot_id,database='poc_test',table_prefix='poc_sbom')
        self.assertFalse(result['execute']);self.assertTrue(result['external_namespace_confirmation_required'])
        self.assertFalse(result['existing_tables_changed']);self.assertFalse(result['publication_authority'])
        self.assertEqual(result['authentication'], 'NOT_REVALIDATED')
        self.assertEqual(len(result['queries']),5)
        for table, uri in result['locations'].items():
            self.assertEqual(uri,self.target.uri(self.plan.snapshot_id)+'analytics/'+table+'/')
            self.assertIn("LOCATION '"+uri+"'",result['ddl'])
            prefix = uri.removeprefix('s3://'+self.target.bucket+'/')
            self.assertEqual([k for b,k in self.client.current if k.startswith(prefix)], [prefix+'part-00000.parquet'])
        for database, prefix in (('production','poc_sbom'),('poc_test','active'),('poc_test','poc_unsafe;drop')):
            with self.assertRaisesRegex(IngestionError, 'ISOLATED_POC_NAMESPACE_REQUIRED'):
                catalog_plan(self.adapter,self.plan.snapshot_id,database=database,table_prefix=prefix)

    def test_historical_golden_recovery_uses_only_transport_and_preserves_query_results(self):
        context = historical(self.root / 'historical-input')
        batch = Path(export(prepare(context),self.root / 'historical-output')['path'])
        plan = prepare_snapshot(batch,self.target);save_plan(plan,self.root/'historical-plan')
        self.assertTrue(publish_snapshot(plan,self.adapter)['complete'])
        for name in ('historical-input','historical-output','historical-plan'):
            (self.root/name).rename(self.root/('unavailable-'+name))
        recovered = self.root/'recovered'
        def forbidden(*args, **kwargs):raise AssertionError('network/build/preparation fallback forbidden')
        with patch('socket.socket',side_effect=forbidden), patch('urllib.request.urlopen',side_effect=forbidden), \
                patch('subprocess.run',side_effect=forbidden), patch('scripts.pipeline.analytics.normalize.prepare',side_effect=forbidden):
            result = recover_snapshot(self.adapter,plan.snapshot_id,recovered)
            self.assertEqual(result['code'],'SNAPSHOT_RECOVERED')
            data = read_completed(recovered)
            self.assertEqual((len(data['observations']),len(data['packages'])),(6,300))
            for item in plan.objects:self.assertEqual((recovered/item.path).read_bytes(),item.body)
            indices = {i['framework']:i['image_index_digest'] for i in context['images']}
            demo = demonstrate(recovered,component='wolfi-baselayout',runtime_framework='go1-26',dev_framework='go1-26-dev',
                               runtime_index=indices['go1-26'],dev_index=indices['go1-26-dev'],platform='linux/amd64')
            self.assertEqual(demo['queries']['03_runtime_vs_dev']['counts'],
                             dict(ONLY_RUNTIME=2,ONLY_DEV=103,SAME_REPORTED_NAME_VERSION=20))
            self.assertEqual(sorted(r['component_records'] for r in demo['component_counts']),[22,22,123,123])
            self.assertFalse(demo['athena_executed'])
            trace = demo['queries']['05_trace_original']['rows'][0]
            catalog = catalog_plan(self.adapter,plan.snapshot_id,database='poc_test',table_prefix='poc_sbom')
            key = catalog['raw_root_uri'].removeprefix('s3://'+self.target.bucket+'/')+trace['raw_spdx_path']
            self.assertEqual(sha256(self.adapter.get(key).body),trace['sbom_sha256'])
        with self.assertRaisesRegex(IngestionError,'RECOVERY_DESTINATION_EXISTS'):
            recover_snapshot(self.adapter,plan.snapshot_id,recovered)
