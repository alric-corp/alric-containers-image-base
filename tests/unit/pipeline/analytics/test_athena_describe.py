"""Real 17-entry journal of lab-sbom-athena-v1 and the DESCRIBE response rule; all clients fake.

REAL: journal bytes (requests, tokens, saved GetQueryExecution responses and the
eleven SELECT result pages), Glue catalog objects, GitHub metadata. SYNTHETIC:
every mutation, transport ZIPs, the terminal state of the pending DESCRIBE, the
describe_packages execution and the DESCRIBE pages built here (real Glue
names/types in the shape observed in athena-describe-results, whose real page
the later journal tests use).
"""
from collections import Counter
import copy
from datetime import datetime, timedelta
import json
import unittest

from scripts.pipeline.analytics import athena_poc as a, athena_restore as r
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics import test_athena_poc as support, test_athena_terminator as six
from tests.unit.pipeline.analytics.test_athena_restore import archive, GitHub
from tests.unit.pipeline.analytics.test_athena_views import real_tables, VIEWS, FIXTURE as VIEWS_FIXTURE

ROOT = support.ROOT
FIXTURE = ROOT / 'tests/fixtures/sbom-analytics/athena-describe-reconciliation'
PLAN = ROOT / 'tests/fixtures/sbom-analytics/athena-reconciliation/sql-plan.json'
PLAN_HASH, AUTH = six.PLAN_HASH, six.AUTH
JOURNAL_HASH = 'ff09f07e1754bd7bce21e1b76eba04b65158e257b0bb6636eef099e9b4551983'
ANCESTOR_HASH = 'e621e60802bd9e7017460a012ec783ea17478cf0df0c26892c99624d03906101'
DESCRIBE_ID = 'e3264498-d19b-428a-80a8-a8f90a0ddce2'
DESCRIBE_TOKEN = '4fb38e95b4363447f9690faa5d15617ff88885bc3c4e3dc16dfb74f904ca72e5'
PREFIX = 'poc_snapshot_6ae0d5a463a20961e4431cb86d7d969ff2157bf25428a22dd08aa119632548b6_'
# Candidate source: latest inspected evidence, not an automatic "latest" selection.
SOURCE = dict(run_id=38103483249, attempt=1, artifact_id=11688034210,
              source_sha='bfb0f474756035a7d36b80c4454f138214feae8c',
              zip_sha256='c303c6531dd824e06cd959144241a5960d099b6be11d6ae268668d2eba5bfcb6', zip_bytes=360130,
              journal_sha256=JOURNAL_HASH, journal_bytes=605578, sql_plan_sha256=PLAN_HASH, sql_plan_bytes=257893)
REAL_DESCRIBE = ROOT / 'tests/fixtures/sbom-analytics/athena-describe-results/describe-observations-results.json'
SELECTS = ('01_find_images', '02_versions', '03_runtime_vs_dev', '04_compare_digests', '05_trace_original',
           'count_observations', 'count_packages', 'inventory_counts', 'null_empty_arrays', 'nested_types', 'nested_values')


def journal():
    return json.loads((FIXTURE / 'execution-journal.json').read_bytes())


def plan():
    return json.loads(PLAN.read_bytes())


def describe_line(name, kind):
    """Hive text line in the layout OBSERVED in the real e3264498 page."""
    return name.ljust(20) + '\t' + kind.ljust(20) + '\t' + ' ' * 20


def describe_pages(table_key, rows=None, columns=None):
    """SYNTHETIC DESCRIBE pages in the observed shape: real Glue names/types, the real
    three-column ColumnInfo and one text cell per row."""
    if rows is None:
        rows = [describe_line(c['Name'], c['Type']) for c in real_tables()[table_key]['StorageDescriptor']['Columns']]
    if columns is None:
        columns = json.loads(REAL_DESCRIBE.read_bytes())[0]['ResultSet']['ResultSetMetadata']['ColumnInfo']
    return [dict(ResultSet=dict(ResultSetMetadata={'ColumnInfo': columns}, Rows=[{'Data': [{'VarCharValue': v}]} for v in rows]))]


class AthenaDescribeComparisonTests(unittest.TestCase):
    def reconcile(self, statement_id='describe_observations', returned=None, kind='DESCRIBE', sent=None,
                  submission=None, **response_fields):
        """Real describe_observations response, optionally replayed for the other plan DESCRIBE."""
        real = journal()['executions']['describe_observations']
        statement = next(s for s in plan()['statements'] if s['id'] == statement_id)
        request = copy.deepcopy(real['request']) if statement_id == 'describe_observations' else a.request(statement, plan())
        response = copy.deepcopy(real['remote_observation'])
        if sent is not None:
            request['QueryString'] = sent
        if returned is not None:
            response['Query'] = returned
        for key, value in (submission or {}).items():
            request[key] = value
        response.update(response_fields)
        seen = []
        client = type('Client', (), {'get_query_execution': lambda self, **kw: {'QueryExecution': copy.deepcopy(response)}})()
        value = a._execution(client, real['query_id'], request, kind=kind,
                             observation=lambda *v: seen.append(copy.deepcopy(v)))
        return value, seen[-1][1], request

    def test_real_pair_is_accepted_only_as_identity_and_keeps_queued_state(self):
        raw = (FIXTURE / 'execution-journal.json').read_bytes()
        self.assertEqual((sha256(raw), len(raw)), (JOURNAL_HASH, 605578))
        entry = json.loads(raw)['executions']['describe_observations']
        self.assertEqual((entry['state'], entry['query_id'], entry['request']['ClientRequestToken']),
                         ('SUBMITTED', DESCRIBE_ID, DESCRIBE_TOKEN))
        self.assertEqual(entry['request']['QueryString'], 'DESCRIBE poc_distroless_sbom.' + PREFIX + 'sbom_observation_rows_v1')
        self.assertEqual(entry['remote_observation']['Query'], 'DESCRIBE ' + PREFIX + 'sbom_observation_rows_v1')
        self.assertEqual(entry['request']['QueryExecutionContext'], dict(Catalog='AwsDataCatalog', Database='poc_distroless_sbom'))
        self.assertEqual(entry['remote_observation']['QueryExecutionContext'], dict(Catalog='awsdatacatalog', Database='poc_distroless_sbom'))
        value, comparison, request = self.reconcile()
        self.assertEqual(value['Status']['State'], 'QUEUED')  # Identity only; never a terminal success.
        self.assertEqual((comparison['sql_rule'], comparison['validated_database'], comparison['execution_parameters']),
                         ('DESCRIBE_DATABASE_QUALIFIER_OMITTED', 'poc_distroless_sbom', 'NOT_RETURNED'))
        self.assertEqual((comparison['request_sql_sha256'], comparison['observed_sql_sha256']),
                         (sha256(entry['request']['QueryString'].encode()), sha256(entry['remote_observation']['Query'].encode())))
        self.assertEqual(request, entry['request'])

    def test_both_plan_describes_exact_or_omitted_qualifier(self):
        for statement_id, table in (('describe_observations', 'sbom_observation_rows_v1'), ('describe_packages', 'sbom_package_rows_v1')):
            sent = next(s['sql'] for s in plan()['statements'] if s['id'] == statement_id)
            self.assertEqual(sent, 'DESCRIBE poc_distroless_sbom.' + PREFIX + table)
            with self.subTest(statement=statement_id):
                self.assertEqual(self.reconcile(statement_id, returned=sent)[1]['sql_rule'], 'EXACT_TOKENS_ASCII_WHITESPACE_ONLY')
                self.assertEqual(self.reconcile(statement_id, returned='DESCRIBE ' + PREFIX + table)[1]['sql_rule'],
                                 'DESCRIBE_DATABASE_QUALIFIER_OMITTED')
                self.assertEqual(self.reconcile(statement_id, returned='\nDESCRIBE\t' + PREFIX + table + '\r\n')[1]['sql_rule'],
                                 'DESCRIBE_DATABASE_QUALIFIER_OMITTED')

    def test_context_and_identity_guards_run_before_the_exception(self):
        context = dict(Catalog='awsdatacatalog', Database='poc_distroless_sbom')
        cases = [(dict(QueryExecutionContext=dict(context, Database='other')), 'Database'),
                 (dict(QueryExecutionContext=dict(context, Catalog='other')), 'Catalog'),
                 (dict(QueryExecutionContext=dict(context, Catalog='AWSDATACATALOG')), 'Catalog'),
                 (dict(WorkGroup='other'), 'WorkGroup'), (dict(QueryExecutionId='other'), 'QueryExecutionId')]
        for fields, field in cases:
            with self.subTest(fields=fields), self.assertRaises(IngestionError) as caught:
                self.reconcile(**fields)
            self.assertEqual((caught.exception.code, caught.exception.expected['field']), ('ATHENA_EXECUTION_IDENTITY_DIFFERS', field))
        for bad in (None, 'x', {'Database': 'poc_distroless_sbom'}, dict(context, Extra='x')):
            with self.subTest(context=bad), self.assertRaisesRegex(IngestionError, 'EXECUTION_CONTEXT_INVALID'):
                self.reconcile(QueryExecutionContext=bad)
        # Coherent contexts, but the authorized qualifier names another database.
        other = dict(Catalog='AwsDataCatalog', Database='other')
        with self.assertRaises(IngestionError) as caught:
            self.reconcile(submission=dict(QueryExecutionContext=other), QueryExecutionContext=dict(context, Database='other'))
        self.assertEqual(caught.exception.expected['field'], 'Query.tokens')

    def test_other_tables_options_and_statements_stay_rejected(self):
        table = PREFIX + 'sbom_observation_rows_v1'
        for returned in ['DESCRIBE ' + PREFIX + 'sbom_package_rows_v1', 'DESCRIBE ' + table.replace('6ae0d5a4', 'aaaaaaaa'),
                         'DESCRIBE', 'DESCRIBE awsdatacatalog.' + table, 'DESCRIBE awsdatacatalog.poc_distroless_sbom.' + table,
                         'DESCRIBE other.' + table, 'DESCRIBE EXTENDED ' + table, 'DESCRIBE FORMATTED ' + table,
                         'DESCRIBE TABLE ' + table, 'DESCRIBE ' + table + ' observation_id', 'DESCRIBE ' + table + '.observation_id',
                         'DESCRIBE ' + table + " PARTITION (x='1')", 'DESCRIBE ' + table + ' /* c */',
                         'DESCRIBE ' + table + ' -- c\n', 'DESCRIBE ' + table + ';', 'DESCRIBE ' + table + '; DESCRIBE ' + table,
                         'describe ' + table, 'DESCRIBE "' + table + '"', 'DESCRIBE `' + table + '`', 'DESCRIBE ' + table.upper(),
                         "DESCRIBE '" + table + "'", 'DESCRIBE ' + table[:-1], 'SELECT * FROM ' + table]:
            with self.subTest(returned=returned), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile(returned=returned)
        for returned in ('DESCRIBE ' + table, 'DESCRIBE ' + table + ' $x'):
            with self.subTest(returned=returned), self.assertRaisesRegex(IngestionError, 'REPRESENTATION_UNSUPPORTED'):
                self.reconcile(returned=returned)

    def test_exception_is_not_extended_to_other_kinds_or_shapes(self):
        table = PREFIX + 'sbom_observation_rows_v1'
        for kind in (None, 'SELECT', 'DDL'):  # resource_readback passes no kind; SELECT/DDL never qualify.
            with self.subTest(kind=kind), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile(kind=kind)
        view = next(s['sql'] for s in plan()['statements'] if s['id'] == 'view-2')
        for kind, sent, returned in [
                ('SELECT', 'SELECT a FROM poc_distroless_sbom.' + table, 'SELECT a FROM ' + table),
                ('DESCRIBE', 'SELECT a FROM poc_distroless_sbom.' + table, 'SELECT a FROM ' + table),
                ('DDL', view, view.replace('poc_distroless_sbom.', '')),
                ('DESCRIBE', 'DESCRIBE "poc_distroless_sbom".' + table, 'DESCRIBE ' + table),
                ('DESCRIBE', 'DESCRIBE poc_distroless_sbom."' + table + '"', 'DESCRIBE "' + table + '"'),
                ('DESCRIBE', 'DESCRIBE poc_distroless_sbom.' + table + ';', 'DESCRIBE ' + table),
                ('DESCRIBE', 'DESCRIBE EXTENDED poc_distroless_sbom.' + table, 'DESCRIBE EXTENDED ' + table),
                ('DESCRIBE', "SELECT 'poc_distroless_sbom.x'", "SELECT 'x'")]:
            with self.subTest(sent=sent), self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
                self.reconcile(kind=kind, sent=sent, returned=returned)

    def test_all_18_requests_tokens_and_plan_unchanged(self):
        raw, pins = PLAN.read_bytes(), json.loads((six.FIXTURE / 'request-fingerprints.json').read_bytes())
        self.assertEqual(sha256(raw), PLAN_HASH)
        saved = journal()['executions']
        self.assertEqual(len(saved), 17)
        self.assertNotIn('describe_packages', saved)
        for statement, pin in zip(json.loads(raw)['statements'], pins):
            request = a.request(statement, json.loads(raw))
            with self.subTest(statement=statement['id']):
                self.assertEqual((sha256(canonical(request)), request['ClientRequestToken'], sha256(statement['sql'].encode())),
                                 (pin['request_sha256'], pin['client_request_token'], pin['sql_sha256']))
                if statement['id'] in saved:
                    self.assertEqual(canonical(saved[statement['id']]['request']), canonical(request))
        self.assertEqual(pins[16]['client_request_token'], DESCRIBE_TOKEN)


class AthenaDescribeResultsTests(unittest.TestCase):
    def fetch(self, pages):
        client = type('Client', (), {'get_query_results': lambda self, **kw: copy.deepcopy(
            pages[int(kw.get('NextToken', '0'))])})()
        return a.query_results(client, DESCRIBE_ID, kind='DESCRIBE')

    def test_describe_rows_are_recorded_literally_with_pagination(self):
        pages = describe_pages('sbom_observation_rows_v1')
        rows = pages[0]['ResultSet']['Rows']
        split = [dict(pages[0], ResultSet=dict(pages[0]['ResultSet'], Rows=rows[:10]), NextToken='1'),
                 dict(pages[0], ResultSet=dict(pages[0]['ResultSet'], Rows=rows[10:]))]
        result = self.fetch(split)
        self.assertEqual(len(result['pages']), 2)
        self.assertEqual(result['lines'], [v['Data'][0]['VarCharValue'] for v in rows])
        self.assertEqual(result['lines'][0], describe_line('observation_id', 'string'))  # No SELECT header removal.
        self.assertNotIn('rows', result)

    def test_describe_result_types_and_shapes_fail_closed(self):
        with self.assertRaisesRegex(IngestionError, 'DESCRIBE_COLUMNS_DIFFER'):
            self.fetch(describe_pages('sbom_package_rows_v1', columns=[dict(Name=k, Type='array<string>')
                                                                       for k in ('col_name', 'data_type', 'comment')]))
        bad = describe_pages('sbom_package_rows_v1')
        bad[0]['ResultSet']['Rows'][0]['Data'].append({'VarCharValue': 'extra'})
        with self.assertRaisesRegex(IngestionError, 'DESCRIBE_LINE_INVALID'):
            self.fetch(bad)
        self.assertEqual(self.fetch(describe_pages('sbom_package_rows_v1', rows=[]))['lines'], [])  # execute_plan rejects empty.


class RealJournalGitHub(GitHub):
    """Selected REAL run 38103483249 metadata; SYNTHETIC transport ZIP with its own hash."""
    def __init__(self, raw):
        self.metadata = json.loads((FIXTURE / 'github-metadata.json').read_bytes())
        self.metadata['artifact'].update(size_in_bytes=len(raw), digest='sha256:' + sha256(raw))
        self.raw, self.calls = raw, []


class AthenaSeventeenEntryResumeTests(unittest.TestCase):
    setUpClass = classmethod(support.AthenaPocTests.setUpClass.__func__)
    restore = six.AthenaSixEntryResumeTests.restore
    execute = six.AthenaSixEntryResumeTests.execute

    def setUp(self):
        support.AthenaPocTests.setUp(self)
        self.raw, self.original = PLAN.read_bytes(), (FIXTURE / 'execution-journal.json').read_bytes()
        self.ancestor = (VIEWS_FIXTURE / 'execution-journal.json').read_bytes()
        # Ancestor first: selection is by exact member path and hashes, never order/basename/size.
        self.members = [('athena-resume-source/execution-journal.json', self.ancestor),
                        ('athena-resume-source/sql-plan.json', self.raw),
                        ('athena-reports/authentication.json', (FIXTURE / 'authentication.json').read_bytes()),
                        ('athena-reports/execution-journal.json', self.original),
                        ('athena-reports/sql-plan.json', self.raw)]
        self.zipped = archive(self.members)  # SYNTHETIC transport, not the original 360130-byte ZIP.
        self.resume = r.ResumeSource(**dict(SOURCE, zip_sha256=sha256(self.zipped), zip_bytes=len(self.zipped)))
        self.github = RealJournalGitHub(self.zipped)
        self.executor_sha = 'c' * 40
        self.fresh('first')

    def fresh(self, name):
        self.reports, self.originals = self.root / ('reports-' + name), self.root / ('originals-' + name)
        self.journal = self.reports / 'execution-journal.json'
        self.settings = dict(type(self).settings)
        self.glue = support.Glue(self.expected, self.settings)
        self.athena = support.Athena(self.raw, self.expected, self.settings, self.glue)
        self.events = []

    def seed(self):
        self.known = json.loads(self.original)['executions']
        # SYNTHETIC terminal state for the pending DESCRIBE, built on its REAL QUEUED observation.
        self.pending = copy.deepcopy(self.known['describe_observations']['remote_observation'])
        submitted = datetime.fromisoformat(self.pending['Status']['SubmissionDateTime'])
        self.pending['Status'] = dict(State='SUCCEEDED', SubmissionDateTime=submitted.isoformat(),
                                      CompletionDateTime=(submitted + timedelta(milliseconds=400)).isoformat())
        self.pending['Statistics'] = dict(TotalExecutionTimeInMillis=400, EngineExecutionTimeInMillis=300,
                                          DataScannedInBytes=0, ResultReuseInformation={'ReusedPreviousResult': False})
        self.pending_pages = describe_pages('sbom_observation_rows_v1')
        statements = {s['id']: s for s in plan()['statements']}
        for key, saved in self.known.items():
            entry = dict(id=saved['query_id'], request=copy.deepcopy(saved['request']), statement=statements[key],
                         submitted_at=saved['submitted_at'])
            self.athena.executions[entry['id']] = entry
            self.athena.tokens[saved['request']['ClientRequestToken']] = entry
        for table in real_tables().values():
            self.glue.tables[table['Name']] = table
        original_get, original_start = self.athena.get_query_execution, self.athena.start_query_execution

        def get(**kwargs):
            query_id = kwargs['QueryExecutionId']
            self.events.append(('GET', query_id))
            if query_id == DESCRIBE_ID:
                return {'QueryExecution': copy.deepcopy(self.pending)}
            saved = next((v for v in self.known.values() if v['query_id'] == query_id), None)
            if saved:
                return {'QueryExecution': copy.deepcopy(saved['execution'])}  # REAL saved response.
            # SYNTHETIC describe_packages response, shaped like the real DESCRIBE response.
            response = copy.deepcopy(original_get(**kwargs))
            execution = response['QueryExecution']
            execution['QueryExecutionContext']['Catalog'] = 'awsdatacatalog'
            execution.pop('ExecutionParameters', None)
            execution['Query'] = execution['Query'].replace('DESCRIBE poc_distroless_sbom.', 'DESCRIBE ', 1)
            return response

        def results(**kwargs):
            query_id = kwargs['QueryExecutionId']
            self.events.append(('RESULTS', query_id))
            saved = next((v for v in self.known.values() if v['query_id'] == query_id and 'results' in v), None)
            pages = saved['results']['pages'] if saved else (
                self.pending_pages if query_id == DESCRIBE_ID else describe_pages('sbom_package_rows_v1'))
            chain = [None] + [page.get('NextToken') for page in pages[:-1]]
            return copy.deepcopy(pages[chain.index(kwargs.get('NextToken'))])  # REAL pages for the 11 SELECTs.

        def start(**kwargs):
            self.events.append(('START', kwargs['ClientRequestToken']))
            return original_start(**kwargs)

        def stop(**kwargs):
            self.events.append(('STOP', kwargs['QueryExecutionId']))
            self.pending['Status']['State'] = 'CANCELLED'
            return {}

        self.athena.get_query_execution, self.athena.start_query_execution = get, start
        self.athena.get_query_results, self.athena.stop_query_execution = results, stop

    def readback(self, **kwargs):
        return a.resource_readback(self.athena, self.glue, self.expected, self.settings, self.proposal,
                                   json.loads(self.journal.read_bytes()), journal_path=self.journal,
                                   plan_raw=self.raw, authorization_reference=AUTH, **kwargs)

    def test_candidate_source_restores_17_entry_member_and_preserves_ancestor(self):
        self.assertEqual(r.source_document(canonical(SOURCE)), r.ResumeSource(**SOURCE))
        self.assertEqual((sha256(self.original), len(self.original)), (JOURNAL_HASH, 605578))
        self.assertEqual((sha256(self.ancestor), len(self.ancestor)), (ANCESTOR_HASH, 36155))
        receipt = self.restore()
        self.assertEqual((receipt['restored_executions'], receipt['total_round_budget'],
                          receipt['remaining_unreserved_executions']), (17, 18, 1))
        self.assertEqual((receipt['source']['source_sha'], receipt['executor_source_sha']), (SOURCE['source_sha'], self.executor_sha))
        self.assertEqual(self.journal.read_bytes(), self.original)
        self.assertEqual((self.originals / 'execution-journal.json').read_bytes(), self.original)
        self.assertEqual((self.originals / 'source-artifact.zip').read_bytes(), self.zipped)
        self.assertIn(dict(path='athena-resume-source/execution-journal.json', size=36155, sha256=ANCESTOR_HASH),
                      r.archive_members(self.zipped)[1])
        ancestor, current = (json.loads(v)['executions'] for v in (self.ancestor, self.original))
        self.assertEqual({k: (e['query_id'], e['request']) for k, e in ancestor.items()},
                         {k: (current[k]['query_id'], current[k]['request']) for k in ancestor})
        self.assertEqual(Counter(e['state'] for e in current.values()), {'VERIFIED': 16, 'SUBMITTED': 1})

    def test_17_known_get_only_pending_describe_results_then_one_start_and_second_pass_zero(self):
        self.restore()
        self.seed()
        observations = {}
        before = self.readback(observations=observations)
        self.assertEqual(len(before['existing_objects']), 5)
        self.assertEqual([observations['objects'][VIEWS[k][0]]['view']['status'] for k in VIEWS], ['EQUIVALENT'] * 3)
        self.assertFalse([e for e in self.events if e[0] != 'GET'])
        result = self.execute()
        self.assertEqual((result['historically_reserved_requests'], result['api_calls']['new_starts'],
                          result['api_calls']['idempotent_retransmissions'], result['distinct_query_execution_ids'],
                          result['authorized_round_budget'], result['remaining_unreserved_executions']), (17, 1, 0, 18, 18, 0))
        pins = json.loads((six.FIXTURE / 'request-fingerprints.json').read_bytes())
        self.assertEqual([v['ClientRequestToken'] for v in self.athena.calls], [pins[17]['client_request_token']])
        first = next(i for i, event in enumerate(self.events) if event[0] == 'START')
        self.assertTrue({('GET', v['query_id']) for v in self.known.values()} <= set(self.events[:first]))
        self.assertIn(('RESULTS', DESCRIBE_ID), self.events[:first])
        self.assertTrue({('RESULTS', self.known[k]['query_id']) for k in SELECTS} <= set(self.events[:first]))
        saved = json.loads(self.journal.read_bytes())['executions']
        statements = {s['id']: s for s in plan()['statements']}
        for key in SELECTS:  # The eleven REAL result sets still match the frozen plan.
            self.assertEqual(Counter(canonical(x) for x in saved[key]['results']['rows']),
                             Counter(canonical(x) for x in statements[key]['expected_rows']))
        for key, query_id in (('describe_observations', DESCRIBE_ID), ('describe_packages', saved['describe_packages']['query_id'])):
            entry = saved[key]
            self.assertEqual((entry['state'], entry['query_id'], entry['identity_comparison']['sql_rule']),
                             ('VERIFIED', query_id, 'DESCRIBE_DATABASE_QUALIFIER_OMITTED'))
            self.assertTrue(entry['results']['lines'])
            self.assertNotIn('results_capture', entry)
        self.assertEqual(saved['describe_observations']['request']['ClientRequestToken'], DESCRIBE_TOKEN)
        self.assertEqual(saved['describe_observations']['start_attempts'], 1)
        for statement, pin in zip(plan()['statements'], pins):
            self.assertEqual(sha256(canonical(saved[statement['id']]['request'])), pin['request_sha256'])
        for key, entry in self.known.items():
            self.assertEqual((saved[key]['query_id'], saved[key]['request']), (entry['query_id'], entry['request']))
        after = {}
        self.readback(require_complete=True, observations=after)
        self.assertEqual([after['objects'][VIEWS[k][0]]['view']['status'] for k in VIEWS], ['EQUIVALENT'] * 3)
        self.assertEqual(self.execute()['api_calls']['start_query_execution'], 0)
        self.assertEqual(len(self.athena.calls), 1)
        self.assertEqual(sha256((self.reports / 'sql-plan.json').read_bytes()), PLAN_HASH)
        self.assertEqual((self.originals / 'execution-journal.json').read_bytes(), self.original)
        self.assertEqual(sha256((FIXTURE / 'execution-journal.json').read_bytes()), JOURNAL_HASH)

    def test_pending_describe_divergence_blocks_the_last_instruction(self):
        def status(**fields):
            return lambda test: test.pending['Status'].update(fields)

        def historical(test):  # The REAL recorded QUEUED observation, long past its original deadline.
            test.pending = copy.deepcopy(test.known['describe_observations']['remote_observation'])

        def overrun(test):
            submitted = datetime.fromisoformat(test.pending['Status']['SubmissionDateTime'])
            test.pending['Status']['CompletionDateTime'] = (submitted + timedelta(seconds=121)).isoformat()
            test.pending['Statistics']['TotalExecutionTimeInMillis'] = 121000

        def query(text):
            return lambda test: test.pending.update(Query=text)

        def pages(value):
            return lambda test: setattr(test, 'pending_pages', value)

        def select_page(test):
            original = test.athena.get_query_results

            def changed(**kwargs):
                value = original(**kwargs)
                if kwargs['QueryExecutionId'] == test.known['count_packages']['query_id']:
                    value['ResultSet']['Rows'][1]['Data'][0] = {'VarCharValue': '299'}
                return value
            test.athena.get_query_results = changed
        cases = [(historical, 'QUERY_TIMEOUT'), (status(State='FAILED'), 'QUERY_FAILED'),
                 (status(State='CANCELLED'), 'QUERY_FAILED'), (overrun, 'QUERY_TIMEOUT'),
                 (lambda t: t.pending.update(QueryExecutionContext=dict(Catalog='awsdatacatalog', Database='other')), 'IDENTITY_DIFFERS'),
                 (query('DESCRIBE ' + PREFIX + 'sbom_package_rows_v1'), 'IDENTITY_DIFFERS'),
                 (query('DESCRIBE EXTENDED ' + PREFIX + 'sbom_observation_rows_v1'), 'IDENTITY_DIFFERS'),
                 (pages(describe_pages('sbom_observation_rows_v1', rows=[])), 'DESCRIBE_EMPTY'),
                 (pages(describe_pages('sbom_observation_rows_v1', columns=[dict(Name='col_name', Type='bigint')])),
                  'DESCRIBE_COLUMNS_DIFFER'),
                 (select_page, 'RESULTS_DIFFER')]
        for number, (change, code) in enumerate(cases):
            self.fresh(str(number))
            self.restore()
            self.seed()
            self.readback()
            change(self)
            with self.subTest(code=code), self.assertRaisesRegex(IngestionError, code):
                self.execute()
            self.assertEqual(self.athena.calls, [])
            saved = json.loads(self.journal.read_bytes())['executions']
            self.assertNotIn('describe_packages', saved)
            self.assertNotEqual(saved['describe_observations']['state'], 'VERIFIED')
            self.assertEqual((saved['describe_observations']['query_id'],
                              saved['describe_observations']['request']['ClientRequestToken']), (DESCRIBE_ID, DESCRIBE_TOKEN))

    def test_historical_queued_response_is_cancelled_not_promoted(self):
        self.restore()
        self.seed()
        self.pending = copy.deepcopy(self.known['describe_observations']['remote_observation'])
        with self.assertRaisesRegex(IngestionError, 'QUERY_TIMEOUT'):
            self.execute()
        self.assertEqual([e for e in self.events if e[0] == 'STOP'], [('STOP', DESCRIBE_ID)])
        saved = json.loads(self.journal.read_bytes())['executions']['describe_observations']
        self.assertEqual(saved['state'], 'TIMED_OUT')
        self.assertEqual(self.athena.calls, [])


class AthenaDescribeRunTests(unittest.TestCase):
    """run() with the synthetic test round, REAL catalog and DESCRIBE responses without database."""
    setUpClass = classmethod(support.AthenaPocTests.setUpClass.__func__)
    setUp = support.AthenaPocTests.setUp

    def run_poc(self, name):
        return a.run(self.s3, self.sts, self.athena, self.glue, self.expected, self.settings, self.session, 'test-round',
                     self.root / 'reports', self.root / ('recovered-' + name), authorized_sha256=sha256(self.raw),
                     authorization_reference='TEST_ONLY owner ref')

    def returned(self, old, new):
        def change(response):
            response['QueryExecutionContext'] = dict(response['QueryExecutionContext'], Catalog='awsdatacatalog')
            response.pop('ExecutionParameters', None)
            if response['Query'].startswith('DESCRIBE '):
                response['Query'] = response['Query'].replace(old, new, 1)
        self.athena.changed = change

    def test_full_round_with_unqualified_describes_and_unchanged_snapshot(self):
        self.returned('DESCRIBE poc_distroless_sbom.', 'DESCRIBE ')
        self.run_poc('first')
        for table in real_tables().values():
            self.glue.tables[table['Name']] = table
        result = self.run_poc('second')  # Complete journal: zero starts, real catalog before and after.
        self.assertEqual((result['code'], result['query_executions'], result['api_calls']['start_query_execution']),
                         ('ATHENA_RESULTS_VERIFIED', 18, 0))
        saved = json.loads((self.root / 'reports/execution-journal.json').read_bytes())['executions']
        self.assertEqual([saved[k]['identity_comparison']['sql_rule'] for k in ('describe_observations', 'describe_packages')],
                         ['DESCRIBE_DATABASE_QUALIFIER_OMITTED'] * 2)
        self.assertEqual((self.root / 'reports/snapshot-after.json').read_bytes(), (self.root / 'reports/snapshot-before.json').read_bytes())

    def test_describe_of_another_table_keeps_error_and_final_readback(self):
        self.returned('_sbom_observation_rows_v1', '_sbom_package_rows_v1')
        with self.assertRaisesRegex(IngestionError, 'IDENTITY_DIFFERS'):
            self.run_poc('first')
        failure = json.loads((self.root / 'reports/execution-failure.json').read_bytes())
        self.assertEqual((failure['code'], failure['observed']['field']), ('ATHENA_EXECUTION_IDENTITY_DIFFERS', 'Query.tokens'))
        self.assertEqual(failure['final_readback']['status'], 'UNCHANGED')
        saved = json.loads((self.root / 'reports/execution-journal.json').read_bytes())['executions']
        self.assertEqual((len(saved), saved['describe_observations']['state']), (17, 'SUBMITTED'))
        self.assertEqual((self.root / 'reports/snapshot-after.json').read_bytes(), (self.root / 'reports/snapshot-before.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
