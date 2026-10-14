from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa

from scripts.pipeline.analytics import parquet
from scripts.pipeline.analytics.normalize import export, main, prepare, read_completed
from scripts.pipeline.analytics.spdx import AnalyticsError, canonical, document, sha256
from tests.unit.pipeline.analytics.fixture_support import historical, synthetic


class ParquetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sbom-parquet-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = synthetic(self.root / 'input')
        self.projection = prepare(self.context)
        self.output = self.root / 'output'

    def test_real_parquet_roundtrip_preserves_all_source_bytes_and_types(self):
        p = prepare(historical(self.root / 'historical'))
        result = export(p, self.output)
        target = Path(result['path'])
        data = read_completed(target)
        self.assertEqual(data, document(p.records))
        for path, raw in p.materials:
            self.assertEqual((target / path).read_bytes(), raw)
            self.assertEqual(sha256((target / path).read_bytes()), sha256(raw))
        schema = parquet.arrow_schema('packages')
        self.assertTrue(pa.types.is_list(schema.field('purls').type))
        self.assertTrue(pa.types.is_struct(schema.field('external_references').type.value_type))
        self.assertEqual(schema.field('is_document_subject').type, pa.bool_())
        self.assertEqual(parquet.arrow_schema('observations').field('run_id').type, pa.int64())

    def test_null_and_empty_arrays_have_the_same_explicit_schema(self):
        rows = document(self.projection.records)['packages']
        for label, value in [('null', None), ('empty', [])]:
            sample = [dict(r, purls=value, external_references=value) for r in rows]
            path = self.root / (label + '.parquet')
            parquet.write(path, 'packages', sample)
            self.assertEqual(parquet.read(path, 'packages'), sample)

    def test_retry_uses_same_batch_without_rewriting_or_adding_files(self):
        first = export(self.projection, self.output)
        target = Path(first['path'])
        before = {p.relative_to(target): (p.read_bytes(), p.stat().st_mtime_ns) for p in target.rglob('*') if p.is_file()}
        second = export(prepare(self.context), self.output)
        self.assertEqual(second['status'], 'ALREADY_PRESENT_IDENTICAL')
        self.assertEqual(first['batch_id'], second['batch_id'])
        after = {p.relative_to(target): (p.read_bytes(), p.stat().st_mtime_ns) for p in target.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(len(list((self.output / 'batches').iterdir())), 1)

    def test_prepared_bytes_are_frozen_and_recovery_needs_no_original_paths(self):
        input_directory = self.root / 'input'
        input_directory.rename(self.root / 'unavailable-preparation')
        with patch('subprocess.run', side_effect=AssertionError('no executables allowed')), \
             patch('socket.socket', side_effect=AssertionError('no network allowed')):
            result = export(self.projection, self.output)
            self.assertEqual(read_completed(result['path']), document(self.projection.records))
        self.assertFalse(input_directory.exists())

    def test_updated_marker_cannot_hide_an_extra_output_file(self):
        target = Path(export(self.projection, self.output)['path'])
        extra = b'{}'
        (target / 'unexpected.json').write_bytes(extra)
        marker_path = target / 'complete.json'
        marker = document(marker_path.read_bytes())
        marker['files'].append(dict(path='unexpected.json', size=len(extra), sha256=sha256(extra)))
        marker['files'].sort(key=lambda r:r['path'])
        marker_path.write_bytes(canonical(marker))
        with self.assertRaisesRegex(AnalyticsError, 'inventory differs'):
            read_completed(target)

    def test_json_representation_changes_hash_and_keeps_separate_original_documents(self):
        before = prepare(self.context)
        path = Path(self.context['images'][0]['documents'][0]['path'])
        path.write_bytes(path.read_bytes() + b'\n')
        after = prepare(self.context)
        self.assertNotEqual(before.batch_id, after.batch_id)
        self.assertEqual(len({r['subject_digest'] for p in (before,after) for r in document(p.records)['observations']}), 3)
        self.assertEqual(len({r['sbom_sha256'] for p in (before,after) for r in document(p.records)['observations']}), 4)

    def test_partial_serialization_is_not_visible_as_completed_batch(self):
        original = parquet.write
        def fail_second(path, table, rows):
            if table == 'packages':raise OSError('simulated disk failure')
            return original(path, table, rows)
        with patch.object(parquet, 'write', side_effect=fail_second), self.assertRaisesRegex(OSError, 'disk failure'):
            export(self.projection, self.output)
        self.assertEqual(list((self.output / 'batches').iterdir()), [])
        self.assertEqual(list(self.output.glob('.sbom-analytics-*')), [])
        self.assertEqual(export(self.projection, self.output)['status'], 'CREATED')

    def test_parquet_readback_failure_prevents_completion(self):
        with patch.object(parquet, 'read', return_value=[]), self.assertRaisesRegex(AnalyticsError, 'round-trip'):
            export(self.projection, self.output)
        self.assertEqual(list((self.output / 'batches').iterdir()), [])

    def test_tampered_or_extra_completed_output_is_rejected_without_overwrite(self):
        target = Path(export(self.projection, self.output)['path'])
        (target / 'unexpected.json').write_bytes(b'{}')
        with self.assertRaisesRegex(AnalyticsError, 'inventory differs'):export(self.projection, self.output)
        (target / 'unexpected.json').unlink()
        path = target / 'analytics/sbom_packages/part-00000.parquet'
        path.write_bytes(path.read_bytes() + b'tampered')
        with self.assertRaises(AnalyticsError):export(self.projection, self.output)

    def test_premature_batch_directory_is_not_approved_or_overwritten(self):
        path = self.output / 'batches' / self.projection.batch_id
        path.mkdir(parents=True)
        with self.assertRaises(AnalyticsError):export(self.projection, self.output)
        self.assertEqual(list(path.iterdir()), [])

    def test_symlink_output_is_rejected(self):
        real = self.root / 'real';real.mkdir()
        self.output.symlink_to(real, target_is_directory=True)
        with self.assertRaises(AnalyticsError):export(self.projection, self.output)

    def test_frozen_projection_cannot_supply_traversal_or_wrong_material_hash(self):
        for path in ('../../escaped', 'raw/spdx/sha256='+'0'*64+'/document.spdx.json'):
            with self.assertRaises(AnalyticsError):replace(self.projection, materials=((path,b'bad'),))

    def test_cli_rejects_invalid_batch_and_cloud_uri_with_explicit_error(self):
        path = self.root / 'context.json'
        path.write_bytes(canonical(self.context))
        with patch('sys.stderr', new_callable=io.StringIO) as error:
            self.assertEqual(main(['--input',str(path),'--output','s3://not-authorized/output']),1)
            self.assertIn('only local output', error.getvalue())
        self.context['images'][0]['documents'].pop()
        path.write_bytes(canonical(self.context))
        with patch('sys.stderr', new_callable=io.StringIO) as error:
            self.assertEqual(main(['--input',str(path),'--output',str(self.output)]),1)
            self.assertIn('three subject-specific SPDXs',error.getvalue())
        self.assertFalse(self.output.exists())

    def test_normalization_and_serialization_never_spawn_build_or_cloud_tools(self):
        with patch('subprocess.run', side_effect=AssertionError('no executables allowed')), \
             patch('socket.socket', side_effect=AssertionError('no network allowed')):
            self.assertEqual(export(prepare(self.context), self.output)['status'], 'CREATED')
