import copy
from pathlib import Path
import tempfile
import unittest

from scripts.pipeline.analytics.demo import SQL, demonstrate, open_database, query
from scripts.pipeline.analytics.normalize import export, prepare
from scripts.pipeline.analytics.parquet import definition
from scripts.pipeline.analytics.spdx import AnalyticsError, sha256
from tests.unit.pipeline.analytics.fixture_support import historical, mutate_spdx, synthetic


class QueryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sbom-queries-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def database(self, contexts):
        batches = [export(prepare(c), self.root / 'output')['path'] for c in contexts]
        database = open_database(batches)
        self.addCleanup(database.close)
        return database

    def test_all_five_queries_run_on_real_platform_documents(self):
        context = historical(self.root / 'input')
        batch = export(prepare(context), self.root / 'output')['path']
        indices = {image['framework']:image['image_index_digest'] for image in context['images']}
        result = demonstrate(batch, component='wolfi-baselayout', runtime_framework='go1-26',
            dev_framework='go1-26-dev', runtime_index=indices['go1-26'], dev_index=indices['go1-26-dev'], platform='linux/amd64')
        self.assertFalse(result['athena_executed'])
        self.assertEqual(result['local_sql_engine'], 'SQLite')
        queries = result['queries']
        self.assertEqual(len(queries['01_find_images']['rows']), 4)
        self.assertEqual(queries['02_versions']['rows'], [dict(package_version='20230201-r30', distinct_image_platforms=4)])
        self.assertEqual(queries['03_runtime_vs_dev']['counts'],
                         dict(ONLY_RUNTIME=2, ONLY_DEV=103, SAME_REPORTED_NAME_VERSION=20))
        self.assertEqual(queries['04_compare_digests']['counts'],
                         dict(ONLY_LEFT=2, ONLY_RIGHT=103, SAME_REPORTED_NAME_VERSION=20))
        self.assertEqual(len(queries['05_trace_original']['rows']), 1)
        trace = queries['05_trace_original']['rows'][0]
        self.assertEqual(trace['sbom_sha256'], sha256((Path(batch) / trace['raw_spdx_path']).read_bytes()))
        self.assertEqual(trace['cryptographic_authenticity'], 'NOT_REVALIDATED')
        self.assertEqual(sorted(r['component_records'] for r in result['component_counts']), [22, 22, 123, 123])

    def test_overlapping_batches_do_not_multiply_packages_or_inventory_joins(self):
        context = synthetic(self.root / 'input')
        next_run = copy.deepcopy(context)
        next_run['origin']['run_id'] += 1
        database = self.database([context, next_run, context])
        count = lambda name: database.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
        self.assertEqual(count('sbom_package_rows_v1'), 27)
        self.assertEqual(count('sbom_packages_v1'), 9)
        self.assertEqual(count('sbom_observation_rows_v1'), 9)
        self.assertEqual(count('sbom_observations_v1'), 6)
        self.assertEqual(count('sbom_inventory_v1'), 8)  # 2 runs x 2 platforms x 2 homonymous package IDs.
        self.assertEqual(len(query(database, '01_find_images', ('same-name',))), 2)
        self.assertEqual(query(database, '02_versions', ('same-name',)),
                         [dict(package_version='1+test', distinct_image_platforms=2)])

    def test_index_is_retained_but_subject_and_index_packages_are_excluded_from_inventory(self):
        database = self.database([synthetic(self.root / 'input')])
        self.assertEqual(database.execute("SELECT COUNT(*) FROM sbom_observations_v1 WHERE sbom_scope='index'").fetchone()[0], 1)
        self.assertEqual(database.execute('SELECT COUNT(*) FROM sbom_packages_v1').fetchone()[0], 9)
        self.assertEqual(database.execute('SELECT COUNT(*) FROM sbom_inventory_v1').fetchone()[0], 4)
        self.assertEqual(query(database, '01_find_images', ('container',)), [])

    def test_multiple_references_do_not_multiply_homonymous_packages(self):
        context = synthetic(self.root / 'input')
        refs = [dict(referenceCategory='PACKAGE-MANAGER', referenceType='purl', referenceLocator='pkg:generic/example@1'),
                dict(referenceCategory='PACKAGE-MANAGER', referenceType='purl', referenceLocator='pkg:apk/wolfi/example@1')]
        mutate_spdx(context, lambda d:d['packages'][1].update(externalRefs=refs), document=1)
        database = self.database([context])
        rows = list(database.execute("SELECT * FROM sbom_inventory_v1 WHERE document_platform='linux/amd64'"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(query(database, '01_find_images', ('same-name',))), 2)

    def test_null_versions_and_exact_untrusted_component_text_remain_queryable(self):
        context = synthetic(self.root / 'input')
        name = " café ' OR 1=1 -- "
        def change(value):
            value['packages'][1]['name'] = name
            value['packages'][1].pop('versionInfo')
        mutate_spdx(context, change, document=1)
        database = self.database([context])
        self.assertEqual(query(database, '02_versions', (name,)), [dict(package_version=None, distinct_image_platforms=1)])
        self.assertEqual(len(query(database, '01_find_images', (name,))), 1)
        self.assertEqual(query(database, '01_find_images', (name.strip(),)), [])

    def test_unknown_or_wrong_explicit_digest_never_selects_latest(self):
        context = historical(self.root / 'input')
        batch = export(prepare(context), self.root / 'output')['path']
        with self.assertRaisesRegex(AnalyticsError, 'must select one'):
            demonstrate(batch, component='wolfi-baselayout', runtime_framework='go1-26', dev_framework='go1-26-dev',
                runtime_index='sha256:'+'0'*64, dev_index=context['images'][0]['image_index_digest'], platform='linux/amd64')

    def test_athena_ddl_has_exact_versioned_columns_and_separate_parquet_locations(self):
        ddl = (SQL / 'tables.sql').read_text()
        for table, columns in definition()['tables'].items():
            name = 'sbom_' + ('observation' if table == 'observations' else 'package') + '_rows_v1'
            block = ddl.split('CREATE EXTERNAL TABLE IF NOT EXISTS ' + name + ' (', 1)[1].split('\n)', 1)[0]
            self.assertEqual([line.strip().split(' ', 1)[0] for line in block.strip().splitlines()],
                             [c['name'] for c in columns])
        self.assertEqual(ddl.count('STORED AS PARQUET'), 2)
        self.assertEqual(ddl.count('s3://<ANALYTICS_BUCKET>/<DATASET_PREFIX>/analytics/'), 2)
        self.assertNotIn('PARTITIONED BY', ddl)
        self.assertIn('purls array<string>', ddl)
        self.assertIn('external_references array<struct<', ddl)

    def test_different_raw_documents_for_same_subject_keep_separate_inventory_observations(self):
        context = synthetic(self.root / 'input')
        first = export(prepare(context), self.root / 'output')['path']
        item = context['images'][0]['documents'][1]
        path = Path(item['path'])
        path.write_bytes(path.read_bytes() + b'\n')
        second = export(prepare(context), self.root / 'output')['path']
        database = open_database([first, second])
        self.addCleanup(database.close)
        rows = list(database.execute("SELECT DISTINCT sbom_sha256 FROM sbom_inventory_v1 WHERE document_platform='linux/amd64'"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(query(database, '01_find_images', ('same-name',))), 2)
