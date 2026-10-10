"""Selected real six-entry journal; fake clients never execute cloud operations."""
import copy
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import base64
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics import athena_poc as a, athena_restore as r, parquet
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics import test_athena_poc as support
from tests.unit.pipeline.analytics.test_athena_restore import archive, GitHub

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / 'tests/fixtures/sbom-analytics/athena-six-entry-resume'
PRIOR = ROOT / 'tests/fixtures/sbom-analytics/athena-reconciliation'
PLAN_HASH = 'ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e'
JOURNAL_HASH = 'e4a4410fc7f8149f8e7c3b859f028def03b5cfa3bd3133e7dcc2417bc26d5519'
QUERY_ID = '05c1e7d8-7ef4-4208-ab26-56552e29b7ef'
TOKEN = '64ed26cb6d228b79251721bbc4a8df7cb636ea3d52eddba3c4cdffda82f1f03b'
AUTH = 'TomasAlric-PR124-lab-sbom-athena-v1'


class AthenaTerminatorTests(unittest.TestCase):
    def reconcile(self, sent, returned, **fields):
        entry = json.loads((FIXTURE / 'execution-journal.json').read_bytes())['executions']['01_find_images']
        request, response = copy.deepcopy(entry['request']), copy.deepcopy(entry['remote_observation'])
        request['QueryString'], response['Query'] = sent, returned
        response.update(fields)
        seen = []
        client = SimpleNamespace(get_query_execution=lambda **kwargs: {'QueryExecution': response})
        value = a._execution(client, QUERY_ID, request, observation=lambda *v: seen.append(copy.deepcopy(v)))
        return value, seen[-1][1]

    def test_real_queued_response_omits_only_final_terminator(self):
        raw = (FIXTURE / 'execution-journal.json').read_bytes()
        self.assertEqual(sha256(raw), JOURNAL_HASH)
        entry = json.loads(raw)['executions']['01_find_images']
        self.assertEqual(entry['request']['ClientRequestToken'], TOKEN)
        response = entry['remote_observation']
        self.assertEqual(response['Status']['State'], 'QUEUED')
        self.assertNotIn('ExecutionParameters', response)
        seen = []
        client = SimpleNamespace(get_query_execution=lambda **kwargs: {'QueryExecution': copy.deepcopy(response)})
        result = a._execution(client, QUERY_ID, entry['request'], observation=lambda *v: seen.append(copy.deepcopy(v)))
        self.assertEqual(result['Query'], response['Query'])
        self.assertEqual(seen[-1][1]['sql_rule'], 'TRAILING_TERMINATOR_OMITTED')
        self.assertEqual(seen[-1][1]['execution_parameters'], 'NOT_RETURNED')
        self.assertEqual(seen[-1][1]['request_sql_sha256'], sha256(entry['request']['QueryString'].encode()))
        self.assertEqual(seen[-1][1]['observed_sql_sha256'], sha256(response['Query'].encode()))

    def test_all_18_exact_and_only_three_eligible_omissions(self):
        raw = (PRIOR / 'sql-plan.json').read_bytes()
        self.assertEqual(sha256(raw), PLAN_HASH)
        eligible = []
        for statement in json.loads(raw)['statements']:
            sent = statement['sql']
            with self.subTest(statement=statement['id'], rule='exact'):
                _, comparison = self.reconcile(sent, sent)
                self.assertEqual(comparison['sql_rule'], 'EXACT_TOKENS_ASCII_WHITESPACE_ONLY')
            tokens = a.execution_tokens(sent)
            if tokens[-1:] == [';'] and tokens.count(';') == 1:
                eligible.append(statement['id'])
                end = len(sent.rstrip(' \t\r\n\f')) - 1
                returned = sent[:end] + sent[end+1:]
                with self.subTest(statement=statement['id'], rule='omitted'):
                    _, comparison = self.reconcile(sent, returned)
                    self.assertEqual(comparison['sql_rule'], 'TRAILING_TERMINATOR_OMITTED')
        self.assertEqual(eligible, ['01_find_images', '02_versions', '05_trace_original'])

    def test_external_ascii_whitespace_and_exact_terminator_still_pass(self):
        for sent, returned, rule in [
            ('SELECT 1;', ' \tSELECT\n1;\r\n', 'EXACT_TOKENS_ASCII_WHITESPACE_ONLY'),
            ('SELECT 1;\t\n', '\tSELECT\n1 \f', 'TRAILING_TERMINATOR_OMITTED'),
            ('SELECT 1', '\tSELECT\n1\r\n', 'EXACT_TOKENS_ASCII_WHITESPACE_ONLY')]:
            with self.subTest(returned=returned):
                self.assertEqual(self.reconcile(sent, returned)[1]['sql_rule'], rule)

    def test_semicolons_in_quoted_tokens_and_supported_escapes_stay_exact(self):
        for sent, returned in [("SELECT 'a;b';", "SELECT 'a;b'"),
                               ('SELECT "a;""b";', 'SELECT "a;""b"'),
                               ('SELECT `a;``b`;', 'SELECT `a;``b`'),
                               ("SELECT 'a'';b';", "SELECT 'a'';b'")]:
            with self.subTest(sent=sent):
                self.assertEqual(self.reconcile(sent, returned)[1]['sql_rule'], 'TRAILING_TERMINATOR_OMITTED')
                with self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                    self.reconcile(sent, returned.replace(';', ''))
        for sent, returned in [("SELECT 'a  b';", "SELECT 'a b'"),
                               ('SELECT "a b";', 'SELECT "a  b"'),
                               ('SELECT `a b`;', 'SELECT `a  b`')]:
            with self.subTest(sent=sent), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile(sent, returned)

    def test_tables_columns_predicates_types_operators_and_numbers_stay_exact(self):
        sent = 'SELECT DISTINCT c, CAST(12 AS bigint) FROM t WHERE x>=1 AND y=?;'
        changes = [('DISTINCT ', ''), (' c,', ' other,'), ('bigint', 'int'), ('12', '13'),
                   ('FROM t', 'FROM other'), ('>=', '>'), ('x>=1', 'x>=2'), ('AND', 'OR'),
                   (' WHERE x>=1 AND y=?', ''), ('?', '1'), ('SELECT', 'select')]
        for old, new in changes:
            with self.subTest(change=(old, new)), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile(sent, sent[:-1].replace(old, new))
        with self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
            self.reconcile('SELECT a, b FROM t;', 'SELECT b, a FROM t')

    def test_comments_are_tokens_including_line_comment_termination(self):
        self.assertEqual(self.reconcile('SELECT /*keep;*/ 1;', 'SELECT /*keep;*/ 1')[1]['sql_rule'],
                         'TRAILING_TERMINATOR_OMITTED')
        for sent, returned in [('SELECT /*keep*/ 1;', 'SELECT 1'),
                               ('SELECT 1;', 'SELECT /*extra*/ 1'),
                               ('SELECT 1 --keep\n+ 2;', 'SELECT 1 --keep + 2'),
                               ('SELECT 1; --final\n', 'SELECT 1 --final\n'),
                               ('SELECT 1; /*final*/', 'SELECT 1 /*final*/')]:
            with self.subTest(sent=sent), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile(sent, returned)

    def test_directional_exception_never_absorbs_multiple_statements_or_delimiters(self):
        for sent, returned in [('SELECT 1;;', 'SELECT 1;'), ('SELECT 1;', 'SELECT 1;;'),
                               ('SELECT 1; SELECT 2;', 'SELECT 1; SELECT 2'),
                               ('SELECT 1; SELECT 2;', 'SELECT 1 SELECT 2'),
                               ('SELECT 1;', 'SELECT 1; SELECT 2'), ('SELECT 1', 'SELECT 1;')]:
            with self.subTest(sent=sent, returned=returned), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile(sent, returned)

    def test_omission_does_not_bypass_context_id_or_parameter_guards(self):
        for fields in [dict(QueryExecutionId='other'), dict(WorkGroup='other'),
                       dict(QueryExecutionContext={'Catalog': 'other', 'Database': 'poc_distroless_sbom'}),
                       dict(QueryExecutionContext={'Catalog': 'awsdatacatalog', 'Database': 'other'}),
                       dict(ExecutionParameters=[]), dict(ExecutionParameters=["'different'"])]:
            with self.subTest(fields=fields), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile('SELECT ?;', 'SELECT ?', **fields)
        _, comparison = self.reconcile('SELECT ?;', 'SELECT ?', ExecutionParameters=["'wolfi-baselayout'"])
        self.assertEqual(comparison['execution_parameters'], 'RETURNED')

    def test_all_request_fingerprints_parameters_and_tokens_unchanged(self):
        raw = (PRIOR / 'sql-plan.json').read_bytes()
        plan = json.loads(raw)
        pins = json.loads((FIXTURE / 'request-fingerprints.json').read_bytes())
        self.assertEqual(len(pins), 18)
        for statement, pin in zip(plan['statements'], pins):
            request = a.request(statement, plan)
            with self.subTest(statement=statement['id']):
                self.assertEqual(statement['id'], pin['statement_id'])
                self.assertEqual(sha256(statement['sql'].encode()), pin['sql_sha256'])
                self.assertEqual(sha256(canonical(request)), pin['request_sha256'])
                self.assertEqual(request['ClientRequestToken'], pin['client_request_token'])
                self.assertEqual(request.get('ExecutionParameters', []), pin['parameters'])
        self.assertEqual(sha256(raw), PLAN_HASH)

    def test_unsupported_sql_is_not_made_equivalent_by_terminator_rule(self):
        for returned in ('SELECT\u00a01', 'SELECT $value', "SELECT 'unterminated", "SELECT 'a\\b'"):
            with self.subTest(returned=returned), self.assertRaisesRegex(IngestionError, 'REPRESENTATION_UNSUPPORTED'):
                self.reconcile('SELECT 1;', returned)


class SixEntryGitHub(GitHub):
    """Selected real metadata, synthetic envelope with its own frozen ZIP hash."""
    def __init__(self, source, raw):
        self.metadata = json.loads((FIXTURE / 'github-metadata.json').read_bytes())
        self.metadata['artifact'].update(size_in_bytes=len(raw), digest='sha256:' + sha256(raw))
        self.raw, self.calls = raw, []


class AthenaSixEntryResumeTests(unittest.TestCase):
    setUpClass = classmethod(support.AthenaPocTests.setUpClass.__func__)

    def setUp(self):
        support.AthenaPocTests.setUp(self)
        self.raw = (PRIOR / 'sql-plan.json').read_bytes()
        self.original = (FIXTURE / 'execution-journal.json').read_bytes()
        self.source_sha, self.executor_sha = '20ee0051018eefe94001b9639fd819c4b898ded7', 'a' * 40
        nested = archive([('athena-reports/execution-journal.json', (PRIOR / 'execution-journal.json').read_bytes())])
        self.members = [('athena-reports/execution-journal.json', self.original),
                        ('athena-reports/sql-plan.json', self.raw),
                        ('athena-reports/authentication.json', (FIXTURE / 'authentication.json').read_bytes()),
                        ('athena-resume-source/execution-journal.json', (PRIOR / 'execution-journal.json').read_bytes()),
                        ('athena-resume-source/source-artifact.zip', nested)]
        zipped = archive(self.members)  # TEST transport; never called the original GitHub ZIP.
        self.resume = r.ResumeSource(38088837347, 1, 11683770809, self.source_sha, sha256(zipped), len(zipped),
                                     JOURNAL_HASH, len(self.original), PLAN_HASH, len(self.raw))
        self.github = SixEntryGitHub(self.resume, zipped)
        self.reports, self.originals = self.root / 'reports', self.root / 'originals'
        self.journal = self.reports / 'execution-journal.json'
        self.settings = dict(type(self).settings)
        self.athena = support.Athena(self.raw, self.expected, self.settings, self.glue)
        self.events = []

    def restore(self):
        return r.restore(self.github, self.resume, self.reports, self.originals, executor_sha=self.executor_sha,
                         authorized_sha256=PLAN_HASH, authorization_reference=AUTH,
                         round_id='lab-sbom-athena-v1', snapshot_id=self.expected['snapshot_id'])

    def seed_known(self):
        """Five saved real DDL responses; SELECT terminal/results are SYNTHETIC."""
        journal, plan = json.loads(self.original), json.loads(self.raw)
        self.known = journal['executions']
        self.synthetic_select = copy.deepcopy(self.known['01_find_images']['remote_observation'])
        submitted = self.known['01_find_images']['submitted_at']
        self.synthetic_select.update(Status=dict(State='SUCCEEDED',
            SubmissionDateTime=datetime.fromtimestamp(submitted + .1, timezone.utc),
            CompletionDateTime=datetime.fromtimestamp(submitted + .2, timezone.utc)),
            Statistics=dict(TotalExecutionTimeInMillis=100, EngineExecutionTimeInMillis=80,
                            DataScannedInBytes=100, ResultReuseInformation={'ReusedPreviousResult': False}),
            EngineVersion={'EffectiveEngineVersion': 'Athena engine version 3'})
        for statement in plan['statements'][:6]:
            saved = self.known[statement['id']]
            entry = dict(id=saved['query_id'], request=copy.deepcopy(saved['request']), statement=statement,
                         submitted_at=saved['submitted_at'])
            self.athena.executions[entry['id']] = entry
            self.athena.tokens[saved['request']['ClientRequestToken']] = entry
        # Synthetic matching catalog descriptions; no create API during seeding.
        types = dict(string='string', int32='int', int64='bigint', boolean='boolean', strings='array<string>',
                     references='array<struct<reference_category:string,reference_type:string,reference_locator:string,comment:string>>')
        for number, key in enumerate(a.TABLE_NAMES):
            name = plan['table_names'][key].split('.')[1]
            table = dict(Name=name, DatabaseName=plan['database'], CatalogId=self.expected['destination']['expected_bucket_owner'])
            if number < 2:
                kind = ('observations', 'packages')[number]
                table.update(TableType='EXTERNAL_TABLE', StorageDescriptor=dict(
                    Columns=[dict(Name=c['name'], Type=types[c['type']]) for c in parquet.definition()['tables'][kind]],
                    Location=self.proposal['locations']['sbom_' + kind][:-1],
                    InputFormat='org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat',
                    OutputFormat='org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat',
                    SerdeInfo={'SerializationLibrary': 'org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe'}))
            else:
                statement = plan['statements'][number]
                body = canonical(dict(originalSql=statement['sql'].split(' AS\n', 1)[1], catalog='awsdatacatalog', schema=plan['database']))
                table.update(TableType='VIRTUAL_VIEW', ViewOriginalText='/* Presto View: ' + base64.b64encode(body).decode() + ' */')
            self.glue.tables[name] = table
        original_get, original_start, original_results = (self.athena.get_query_execution,
            self.athena.start_query_execution, self.athena.get_query_results)

        def get(**kwargs):
            query_id = kwargs['QueryExecutionId']
            self.events.append(('GET', query_id))
            if query_id == QUERY_ID:
                return {'QueryExecution': copy.deepcopy(self.synthetic_select)}
            saved = next((v for v in self.known.values() if v['query_id'] == query_id), None)
            if saved:
                return {'QueryExecution': copy.deepcopy(saved['execution'])}
            response = copy.deepcopy(original_get(**kwargs))
            response['QueryExecution']['QueryExecutionContext']['Catalog'] = 'awsdatacatalog'
            response['QueryExecution'].pop('ExecutionParameters', None)
            return response

        def start(**kwargs):
            self.events.append(('START', kwargs['ClientRequestToken']))
            return original_start(**kwargs)

        def results(**kwargs):
            self.events.append(('RESULTS', kwargs['QueryExecutionId']))
            return original_results(**kwargs)

        def stop(**kwargs):
            self.events.append(('STOP', kwargs['QueryExecutionId']))
            self.synthetic_select['Status']['State'] = 'CANCELLED'
            return {}

        self.athena.get_query_execution, self.athena.start_query_execution = get, start
        self.athena.get_query_results, self.athena.stop_query_execution = results, stop

    def execute(self):
        return a.execute_plan(self.raw, self.athena, self.journal, authorized_sha256=PLAN_HASH,
                              authorization_reference=AUTH)

    def test_restore_selects_exact_six_entry_member_not_old_basename_or_dictionary_order(self):
        receipt = self.restore()
        self.assertEqual(receipt['restored_executions'], 6)
        self.assertEqual(receipt['remaining_unreserved_executions'], 12)
        self.assertEqual(self.journal.read_bytes(), self.original)
        self.assertEqual((self.originals / 'execution-journal.json').read_bytes(), self.original)
        selected, _ = r.archive_members(self.github.raw)
        self.assertEqual(selected['athena-reports/execution-journal.json'], self.original)
        self.assertNotEqual(self.original, (PRIOR / 'execution-journal.json').read_bytes())
        self.assertEqual(next(iter(json.loads(self.original)['executions'])), '01_find_images')
        a.validate_journal(self.raw, json.loads(self.original), AUTH)  # Plan order, not dictionary order.
        self.assertEqual(receipt['source']['source_sha'], self.source_sha)
        self.assertEqual(receipt['executor_source_sha'], self.executor_sha)

    def test_six_known_get_only_then_12_new_requests_and_zero_second_pass_starts(self):
        self.restore()
        self.seed_known()
        before = a.resource_readback(self.athena, self.glue, self.expected, self.settings, self.proposal,
                                    json.loads(self.journal.read_bytes()), journal_path=self.journal,
                                    plan_raw=self.raw, authorization_reference=AUTH)
        self.assertEqual(len(before['existing_objects']), 5)
        self.assertEqual(before['api_calls']['idempotent_retransmissions'], 0)
        result = self.execute()
        self.assertEqual(result['historically_reserved_requests'], 6)
        self.assertEqual(result['api_calls']['new_starts'], 12)
        self.assertEqual(result['api_calls']['idempotent_retransmissions'], 0)
        self.assertEqual(result['distinct_query_execution_ids'], 18)
        known_tokens = {v['request']['ClientRequestToken'] for v in self.known.values()}
        self.assertTrue(all(v['ClientRequestToken'] not in known_tokens for v in self.athena.calls))
        first_start = next(i for i, event in enumerate(self.events) if event[0] == 'START')
        self.assertIn(('RESULTS', QUERY_ID), self.events[:first_start])
        self.assertTrue({v['query_id'] for v in self.known.values()} <= {e[1] for e in self.events[:first_start] if e[0] == 'GET'})
        planned = {a.request(s, json.loads(self.raw))['ClientRequestToken']: s['kind'] for s in json.loads(self.raw)['statements']}
        self.assertEqual(Counter(planned[v['ClientRequestToken']] for v in self.athena.calls),
                         {'SELECT': 10, 'DESCRIBE': 2})
        after = a.resource_readback(self.athena, self.glue, self.expected, self.settings, self.proposal,
                                   json.loads(self.journal.read_bytes()), require_complete=True)
        self.assertEqual(len(after['existing_objects']), 5)
        saved = json.loads(self.journal.read_bytes())
        for key, entry in self.known.items():
            self.assertEqual(saved['executions'][key]['query_id'], entry['query_id'])
            self.assertEqual(saved['executions'][key]['request'], entry['request'])
        self.assertEqual(saved['executions']['01_find_images']['identity_comparison']['sql_rule'], 'TRAILING_TERMINATOR_OMITTED')
        self.assertEqual(saved['executions']['01_find_images']['request']['ClientRequestToken'], TOKEN)
        self.assertEqual(self.execute()['api_calls']['start_query_execution'], 0)
        self.assertEqual(len(self.athena.calls), 12)
        self.assertEqual(sha256((FIXTURE / 'execution-journal.json').read_bytes()), JOURNAL_HASH)

    def test_known_failed_or_cancelled_query_stops_without_new_starts(self):
        self.restore()
        self.seed_known()
        for state in ('FAILED', 'CANCELLED'):
            self.journal.write_bytes(self.original)
            self.synthetic_select['Status']['State'] = state
            with self.subTest(state=state), self.assertRaisesRegex(IngestionError, 'QUERY_FAILED'):
                self.execute()
            self.assertEqual(self.athena.calls, [])
            self.assertEqual(json.loads(self.journal.read_bytes())['executions']['01_find_images']['query_id'], QUERY_ID)

    def test_known_terminal_overrun_and_active_expiry_stop_without_new_starts(self):
        self.restore()
        self.seed_known()
        submitted = self.known['01_find_images']['submitted_at']
        self.synthetic_select['Status'].update(SubmissionDateTime=datetime.fromtimestamp(submitted, timezone.utc),
            CompletionDateTime=datetime.fromtimestamp(submitted + 121, timezone.utc))
        self.synthetic_select['Statistics']['TotalExecutionTimeInMillis'] = 121000
        with self.assertRaisesRegex(IngestionError, 'QUERY_TIMEOUT'):
            self.execute()
        self.assertFalse(any(e[0] == 'STOP' for e in self.events))
        self.journal.write_bytes(self.original)
        self.synthetic_select['Status']['State'] = 'RUNNING'
        with self.assertRaisesRegex(IngestionError, 'QUERY_TIMEOUT'):
            self.execute()
        self.assertEqual([e for e in self.events if e[0] == 'STOP'], [('STOP', QUERY_ID)])
        self.assertEqual(self.athena.calls, [])
        self.assertEqual(json.loads(self.journal.read_bytes())['executions']['01_find_images']['request']['ClientRequestToken'], TOKEN)

    def test_known_query_result_mismatch_preserves_rows_and_blocks_remaining_starts(self):
        self.restore()
        self.seed_known()
        original = self.athena.get_query_results
        def changed(**kwargs):
            value = original(**kwargs)
            if kwargs['QueryExecutionId'] == QUERY_ID:
                columns = value['ResultSet']['ResultSetMetadata']['ColumnInfo']
                index = next(i for i, column in enumerate(columns) if column['Name'] == 'image_repository')
                value['ResultSet']['Rows'][1]['Data'][index] = {'VarCharValue': 'changed-result'}
            return value
        self.athena.get_query_results = changed
        with self.assertRaisesRegex(IngestionError, 'RESULTS_DIFFER'):
            self.execute()
        saved = json.loads(self.journal.read_bytes())['executions']['01_find_images']
        self.assertEqual(saved['results']['rows'][0]['image_repository'], 'changed-result')
        self.assertEqual(self.athena.calls, [])
        self.assertEqual(saved['query_id'], QUERY_ID)
        self.assertEqual(saved['request']['ClientRequestToken'], TOKEN)

    def test_restore_hash_wrong_run_missing_or_incomplete_journal_never_becomes_history(self):
        for field, value in [('journal_sha256', 'f' * 64), ('attempt', 2), ('source_sha', 'b' * 40)]:
            base = self.resume
            self.resume = replace(base, **{field: value})
            with self.subTest(field=field), self.assertRaises(IngestionError):
                self.restore()
            self.assertFalse(self.journal.exists())
            self.resume = base
            # Each attempt uses a fresh private destination; originals are never overwritten.
            self.originals = self.root / ('originals-' + field)
        raw = archive(self.members[1:])
        self.github = SixEntryGitHub(self.resume, raw)
        self.resume = replace(self.resume, zip_bytes=len(raw), zip_sha256=sha256(raw))
        with self.assertRaisesRegex(IngestionError, 'REQUIRED_MEMBER_MISSING'):
            self.restore()
        self.assertEqual(self.athena.calls, [])

    def test_semantically_wrong_journal_rejected_even_with_test_refrozen_transport_hash(self):
        base = json.loads(self.original)
        for number, mutate in enumerate([
            lambda j: j.update(authorization_reference='another-round'),
            lambda j: j['executions'].pop('table-1'),
            lambda j: j['executions']['01_find_images'].update(query_id=j['executions']['table-0']['query_id']),
            lambda j: j['executions']['01_find_images']['request'].update(ClientRequestToken='f' * 64)]):
            value = copy.deepcopy(base)
            mutate(value)
            body = canonical(value)
            raw = archive([('athena-reports/execution-journal.json', body)] + self.members[1:])
            self.resume = replace(self.resume, zip_bytes=len(raw), zip_sha256=sha256(raw),
                                  journal_bytes=len(body), journal_sha256=sha256(body))
            self.github = SixEntryGitHub(self.resume, raw)
            self.originals = self.root / ('invalid-originals-' + str(number))
            with self.subTest(number=number), self.assertRaises(IngestionError):
                self.restore()
            self.assertFalse(self.journal.exists())
        self.assertEqual(self.athena.calls, [])

    def test_missing_or_changed_restored_journal_fails_before_aws_client_construction(self):
        self.restore()
        argv = ['--config', str(ROOT / 'policies/analytics/lab-poc.json'),
                '--athena-config', str(ROOT / 'policies/analytics/athena-lab-poc.json'),
                '--session-name', 'TEST_ONLY', '--round-id', 'lab-sbom-athena-v1',
                '--authorized-plan-sha256', PLAN_HASH, '--authorization-reference', AUTH,
                '--resume-receipt', str(self.reports / 'resume-receipt.json'),
                '--output', str(self.root / 'recovered'), '--report', str(self.reports / 'result.json')]
        for content in (None, b'truncated', (PRIOR / 'execution-journal.json').read_bytes()):
            if content is None:
                self.journal.unlink()
            else:
                self.journal.write_bytes(content)
            with self.subTest(content=content is None), patch.dict(os.environ, {'GITHUB_SHA': self.executor_sha}), \
                 patch.object(a, 'aws_clients') as clients, patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(a.main(argv), 1)
                clients.assert_not_called()
            result = json.loads((self.reports / 'result.json').read_bytes())
            self.assertEqual(result['status'], 'ERROR')
            self.assertFalse(result.get('complete', False))


if __name__ == '__main__':
    unittest.main()
