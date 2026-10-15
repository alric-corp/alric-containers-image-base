"""Retention inventory and cost sensitivity (audit G13), from saved exports only."""
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics import retention_inventory as r, s3_run
from scripts.pipeline.analytics.snapshot import load_plan
from scripts.pipeline.analytics.spdx import canonical, sha256

ROOT = Path(__file__).resolve().parents[4]
DATA, RESULTS = 'sbom-analytics/v1', 'query-results/sbom-analytics-v1/'
SNAPSHOT = 'a' * 64
JOURNAL = ROOT / 'tests/fixtures/sbom-analytics/athena-describe-results/execution-journal.json'
TEST_ASSUMPTIONS = dict(source='TEST VALUES ONLY, not a price', storage_usd_per_gib_month=1.0,
                        athena_usd_per_tib_scanned=5.0, athena_minimum_mib_per_query=10, athena_rounding_mib=1,
                        athena_billable_statement_types=['DML'])


def key(path, snapshot=SNAPSHOT):
    return DATA + '/snapshots/' + snapshot + '/' + path


def version(name, size, version_id, latest=True):
    return dict(Key=name, Size=size, VersionId=version_id, IsLatest=latest)


class RetentionInventoryTests(unittest.TestCase):
    def test_every_category_noncurrent_version_and_delete_marker_is_counted_once(self):
        page = dict(Versions=[
            version(key('raw/spdx/sha256=' + 'b' * 64 + '/document.spdx.json'), 100, 'v1'),
            version(key('raw/records/sha256=' + 'c' * 64 + '/record.json'), 10, 'v2'),
            version(key('reports/records.json'), 20, 'v3'), version(key('reports/normalization.json'), 2, 'v4'),
            version(key('analytics/sbom_packages/part-00000.parquet'), 30, 'v5'),
            version(key('complete.json'), 3, 'v6'), version(key('ingestion-manifest.json'), 4, 'v7'),
            version(key('ingestion-manifest.json'), 5, 'v0', latest=False),
            version(DATA + '/snapshots/_smoke_tests/r1-a1/conditional.txt', 50, 'v8'),
            version(RESULTS + 'q-1.csv', 7, 'v9'), version(RESULTS + 'q-1.csv.metadata', 1, 'v10'),
            version(RESULTS + 'q-2.txt', 6, 'v11'), version('elsewhere/unknown.bin', 9, 'v12'),
            version(key('notes.txt'), 1, 'v13')],
            DeleteMarkers=[dict(Key=RESULTS + 'q-3.csv', VersionId='d1', IsLatest=True)])
        repeated = dict(Versions=page['Versions'][:2])  # Overlapping pages never double count.
        result = r.inventory([page, repeated], DATA, RESULTS)
        categories = result['categories']
        self.assertEqual({c: (v['objects'], v['versions'], v['current_bytes'], v['noncurrent_bytes'])
                          for c, v in categories.items() if v['versions']},
                         {'RAW_SPDX': (1, 1, 100, 0), 'BINDING_RECORDS': (1, 1, 10, 0), 'STRUCTURED_RECORDS': (2, 2, 22, 0),
                          'PARQUET': (1, 1, 30, 0), 'MANIFESTS': (2, 3, 7, 5), 'SMOKE_PROBES': (1, 1, 50, 0),
                          'QUERY_RESULTS': (2, 2, 13, 0), 'QUERY_RESULT_METADATA': (1, 1, 1, 0), 'UNCLASSIFIED': (2, 2, 10, 0)})
        self.assertEqual((result['delete_markers'], result['current_delete_markers'], result['total_bytes_all_versions']),
                         (1, 1, 248))
        self.assertEqual(result['snapshots'], {SNAPSHOT: dict(versions=9, bytes=175)})
        self.assertEqual(result['unclassified_keys'], ['elsewhere/unknown.bin', key('notes.txt')])
        self.assertEqual(result['version_history'], 'COMPLETE')

    def test_current_only_listings_cannot_claim_version_history(self):
        result = r.inventory([dict(Contents=[dict(Key=RESULTS + 'q.csv', Size=5)]), dict(Prefix=RESULTS)], DATA, RESULTS)
        self.assertEqual((result['version_history'], result['categories']['QUERY_RESULTS']['current_bytes']),
                         ('CURRENT_OBJECTS_ONLY', 5))
        for listings in ([dict(Versions=[], Contents=[])], [dict(Versions=[version('k', 1, 'v')]), dict(Contents=[dict(Key='k', Size=1)])],
                         [dict(Versions=[version('k', 1, 'v')]), dict(Versions=[version('k', 2, 'v')])],
                         [dict(Versions=[dict(Key='k', Size=-1)])], ['not a listing']):
            with self.subTest(listings=listings), self.assertRaises(ValueError):
                r.inventory(listings, DATA, RESULTS)

    def test_the_real_v1_snapshot_layout_is_fully_classified(self):
        expected = s3_run.config(ROOT / 'policies/analytics/s3.json')
        with tempfile.TemporaryDirectory() as temporary:
            plan_directory = Path(temporary) / 'plan'
            s3_run.unpack(ROOT / 'tests/fixtures/sbom-analytics/frozen-plan-v1.zip',
                          ROOT / 'tests/fixtures/sbom-analytics/frozen-plan-v1.json', plan_directory, expected)
            plan = load_plan(plan_directory)
        listing = dict(Versions=[version(plan.key(o.path), len(o.body), 'v%d' % i) for i, o in enumerate(plan.objects)])
        settings = json.loads((ROOT / 'policies/analytics/athena.json').read_bytes())
        result = r.inventory([listing], expected['destination']['prefix'], settings['results_prefix'])
        counts = {c: v['objects'] for c, v in result['categories'].items() if v['objects']}
        self.assertEqual(counts, {'RAW_SPDX': 6, 'BINDING_RECORDS': 8, 'STRUCTURED_RECORDS': 2, 'PARQUET': 2, 'MANIFESTS': 1})
        self.assertEqual((result['total_bytes_all_versions'], result['snapshots']),
                         (expected['payload_bytes'], {expected['snapshot_id']: dict(versions=19, bytes=expected['payload_bytes'])}))

    def test_real_journal_executions_and_explicit_billing_assumptions(self):
        journal = json.loads(JOURNAL.read_bytes())
        recorded = {e['query_id']: e['execution'] for e in journal['executions'].values() if 'execution' in e}
        unobserved = sorted(e['query_id'] for e in journal['executions'].values() if 'execution' not in e and e['query_id'])
        plain = r.athena([journal])
        self.assertEqual((plain['executions'], plain['unobserved_executions'], plain['billable_bytes'], plain['cost_usd']),
                         (len(recorded), unobserved, None, None))
        self.assertEqual(plain['scanned_bytes'], sum(e['Statistics']['DataScannedInBytes'] for e in recorded.values()))
        batch = dict(QueryExecutions=list(recorded.values()), UnprocessedQueryExecutionIds=[])
        self.assertEqual(r.athena([journal, batch]), plain)  # The same executions from two exports count once.
        estimated = r.athena([journal], r.load_assumptions(dict(TEST_ASSUMPTIONS)))
        billable = sum(max(math.ceil(e['Statistics']['DataScannedInBytes'] / 2**20), 10) * 2**20
                       for e in recorded.values() if e['StatementType'] == 'DML' and e['Status']['State'] != 'FAILED')
        self.assertEqual((estimated['billable_bytes'], estimated['cost_usd']), (billable, billable / 2**40 * 5.0))
        self.assertGreater(estimated['billable_bytes'], estimated['scanned_bytes'])  # The minimum dominates tiny scans.

    def test_unobserved_and_failed_executions_are_neither_dropped_nor_billed(self):
        execution = lambda identity, state, scanned: dict(QueryExecutionId=identity, StatementType='DML',
                                                          Status=dict(State=state), Statistics=dict(DataScannedInBytes=scanned))
        journal = dict(executions={'a': dict(query_id='q-started', state='SUBMITTED'),
                                   'b': dict(query_id='q-failed', execution=execution('q-failed', 'FAILED', 5 * 2**20)),
                                   'c': dict(query_id=None, state='PREPARED')})
        batch = dict(QueryExecutions=[execution('q-ok', 'SUCCEEDED', 0)], UnprocessedQueryExecutionIds=['q-lost'])
        result = r.athena([journal, batch], r.load_assumptions(dict(TEST_ASSUMPTIONS)))
        self.assertEqual((result['executions'], result['unobserved_executions']), (2, ['q-lost', 'q-started']))
        self.assertEqual((result['scanned_bytes'], result['billable_bytes']), (5 * 2**20, 10 * 2**20))  # Only q-ok, at the minimum.

    def test_assumptions_must_be_sourced_and_complete(self):
        for change in (dict(source=' '), dict(athena_usd_per_tib_scanned=-1), dict(storage_usd_per_gib_month=True),
                       dict(athena_rounding_mib=0), dict(athena_billable_statement_types=None), dict(extra=1),
                       dict(athena_minimum_mib_per_query=None)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                r.load_assumptions(dict(TEST_ASSUMPTIONS, **change))
        r.load_assumptions(dict(TEST_ASSUMPTIONS, athena_usd_per_tib_scanned=None, athena_rounding_mib=None,
                                athena_minimum_mib_per_query=None, athena_billable_statement_types=None))

    def test_cutoff_is_a_per_round_bound_never_a_budget_retention_or_recovery_promise(self):
        config = json.loads((ROOT / 'policies/analytics/athena.json').read_bytes())
        result = r.report([dict(Versions=[])], DATA, RESULTS, [json.loads(JOURNAL.read_bytes())], None, config)
        self.assertEqual((result['athena']['per_query_scan_cutoff_bytes'], result['athena']['per_round_scan_bound_bytes']),
                         (104857600, 18 * 104857600))
        self.assertEqual({k: result[k] for k in ('cost', 'monthly_budget', 'retention_policy', 'recovery_guarantee',
                                                 'lifecycle_or_object_lock_changes', 'deletions', 'cloud_calls')},
                         dict(cost='NOT_ESTIMATED', monthly_budget='NOT_DEFINED', retention_policy='NOT_DEFINED',
                              recovery_guarantee='NOT_DEFINED', lifecycle_or_object_lock_changes=0, deletions=0, cloud_calls=0))
        self.assertIsNone(result['storage']['monthly_storage_usd'])

    def test_cli_reads_saved_exports_only_and_never_overwrites_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            listing = directory / 'versions.json'
            listing.write_bytes(canonical(dict(Versions=[version(RESULTS + 'q.csv', 2**30, 'v1')])))
            assumptions = directory / 'assumptions.json'
            assumptions.write_bytes(canonical(TEST_ASSUMPTIONS))
            before = {p: sha256(p.read_bytes()) for p in (listing, assumptions, JOURNAL)}
            output = directory / 'out/inventory.json'
            argv = ['--data-prefix', DATA, '--results-prefix', RESULTS, '--objects', str(listing),
                    '--executions', str(JOURNAL), '--athena-config', str(ROOT / 'policies/analytics/athena.json'),
                    '--assumptions', str(assumptions)]
            with patch('socket.socket', side_effect=AssertionError('no network')), \
                    patch('sys.stdout', new_callable=io.StringIO) as out:
                self.assertEqual(r.main(argv + ['--output', str(output)]), 0)
            result = json.loads(output.read_bytes())
            self.assertEqual((result['cost'], result['storage']['monthly_storage_usd']), ('ESTIMATED_FROM_ASSUMPTIONS', 1.0))
            self.assertEqual([i['path'] for i in result['inputs']],
                             ['versions.json', 'execution-journal.json', 'athena.json', 'assumptions.json'])
            self.assertEqual(json.loads(out.getvalue())['version_history'], 'COMPLETE')
            with patch('sys.stderr', new_callable=io.StringIO) as err:
                self.assertEqual(r.main(argv + ['--output', str(listing)]), 1)
                self.assertIn('must not replace an input', err.getvalue())
                listing_bad = directory / 'bad.json'
                listing_bad.write_bytes(b'{"Versions": [{"Key": 1}]}')
                self.assertEqual(r.main(['--data-prefix', DATA, '--results-prefix', RESULTS, '--objects', str(listing_bad),
                                         '--output', str(directory / 'x.json')]), 1)
            self.assertEqual({p: sha256(p.read_bytes()) for p in before}, before)


if __name__ == '__main__':
    unittest.main()
