"""Real DESCRIBE page of e3264498 and the current 17-entry journal of lab-sbom-athena-v1; all clients fake.

REAL: journal bytes of hosted run 38109412318 / artifact 11690561959 (requests, tokens, the
SUCCEEDED GetQueryExecution of e3264498 and the eleven SELECT pages); the DESCRIBE page read
administratively (Tomas-Instructor, read-only, ResponseMetadata removed, ResultSet unchanged);
Glue objects; GitHub metadata. SYNTHETIC: every mutation and page split, transport ZIPs, the
describe_packages execution and page (observed shape, real Glue names/types) and any
18-entry journal.
"""
from collections import Counter
import copy
import json
import unittest
from unittest import mock

from scripts.pipeline.analytics import athena_run as a, athena_restore as r
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics import test_athena_describe as previous, test_athena_run as support
from tests.unit.pipeline.analytics import test_athena_terminator as six
from tests.unit.pipeline.analytics.test_athena_restore import archive
from tests.unit.pipeline.analytics.test_athena_views import real_tables

ROOT = support.ROOT
FIXTURE = ROOT / 'tests/fixtures/sbom-analytics/athena-describe-results'
PLAN, PLAN_HASH, AUTH = previous.PLAN, previous.PLAN_HASH, previous.AUTH
DESCRIBE_ID, DESCRIBE_TOKEN = previous.DESCRIBE_ID, previous.DESCRIBE_TOKEN
JOURNAL_HASH = 'a921dad4d384f17275a97b702f1141876e98bacd39804b2deda7dc6e23aa7b4c'
PAGE_HASH = '3cdd3f191e0e969ba2b310ce9022b060b9c442d1de365d6b7c2cd46b49a95fc1'
# Current source: latest inspected evidence, not an automatic "latest" selection.
SOURCE = dict(run_id=38109412318, attempt=1, artifact_id=11690561959,
              source_sha='7cc3a5165490d6c3b1f0b7b0d3991914a6125f8b',
              zip_sha256='935e69060b25e94727eab1e512d4bfac28dc5de3e4916fc4e47c6b11c935165c', zip_bytes=555455,
              journal_sha256=JOURNAL_HASH, journal_bytes=607331, sql_plan_sha256=PLAN_HASH, sql_plan_bytes=257893)
SELECTS = previous.SELECTS


def real_pages():
    return json.loads((FIXTURE / 'describe-observations-results.json').read_bytes())


def real_lines():
    return [row['Data'][0]['VarCharValue'] for row in real_pages()[0]['ResultSet']['Rows']]


def with_lines(lines, page=None):
    page = copy.deepcopy(page or real_pages()[0])
    page['ResultSet']['Rows'] = [{'Data': [{'VarCharValue': v}]} for v in lines]
    return page


def split(page, sizes, tokens):
    """SYNTHETIC pagination of one page; the rows and their order are unchanged."""
    rows, pages, start = page['ResultSet']['Rows'], [], 0
    for size, token in zip(sizes, tokens):
        part = copy.deepcopy(page)
        part['ResultSet']['Rows'] = copy.deepcopy(rows[start:start + size])
        if token is not None:
            part['NextToken'] = token
        pages.append(part)
        start += size
    return pages


class Results:
    """Fake GetQueryResults over a page chain; failure=(index, exception) fails that call."""
    def __init__(self, pages, failure=None):
        self.pages, self.failure, self.calls = pages, failure, []

    def get_query_results(self, **kwargs):
        self.calls.append(kwargs.get('NextToken'))
        if self.failure and len(self.calls) - 1 == self.failure[0]:
            raise self.failure[1]
        return copy.deepcopy(self.pages[len(self.calls) - 1])


class RealDescribePageTests(unittest.TestCase):
    def fetch(self, pages, kind='DESCRIBE', failure=None):
        client, self.kept = Results(pages, failure), []
        self.client = client

        def keep(number, page):
            self.kept.append((number, copy.deepcopy(page)))
            return 'kept#%d' % number
        return a.query_results(client, DESCRIBE_ID, kind=kind, keep_page=keep)

    def test_real_page_is_accepted_literally_and_only_as_describe(self):
        raw = (FIXTURE / 'describe-observations-results.json').read_bytes()
        self.assertEqual(sha256(raw), PAGE_HASH)
        page = real_pages()[0]
        columns = page['ResultSet']['ResultSetMetadata']['ColumnInfo']
        self.assertEqual([(c['Name'], c['Type']) for c in columns], a.DESCRIBE_COLUMNS)
        self.assertEqual(Counter(len(row['Data']) for row in page['ResultSet']['Rows']), {1: 43})  # 3 declared, 1 cell.
        self.assertNotIn('NextToken', page)
        result = self.fetch([page])
        self.assertEqual(result['lines'], real_lines())
        self.assertEqual((result['columns'], result['pages']), (columns, [page]))
        self.assertEqual(self.kept, [(0, page)])
        # The data matches the real catalog in the observed layout; the executor keeps the text, it does not split it.
        glue = real_tables()['sbom_observation_rows_v1']['StorageDescriptor']['Columns']
        self.assertEqual(result['lines'], [previous.describe_line(c['Name'], c['Type']) for c in glue])
        self.assertEqual(previous.describe_pages('sbom_observation_rows_v1')[0]['ResultSet'], page['ResultSet'])
        # The textual reading is DESCRIBE-only; as a SELECT the same page is rejected.
        with self.assertRaisesRegex(IngestionError, 'ATHENA_HEADER_DIFFERS'):
            self.fetch([page], kind='SELECT')

    def test_select_keeps_strict_width_header_and_types(self):
        journal = json.loads((FIXTURE / 'execution-journal.json').read_bytes())['executions']
        page = journal['count_packages']['results']['pages'][0]  # REAL SELECT page.
        self.assertEqual(self.fetch([page], kind='SELECT')['rows'], [{'package_record_count': 300}])
        wide = copy.deepcopy(page)
        wide['ResultSet']['Rows'][1]['Data'].append({'VarCharValue': '1'})
        with self.assertRaises(IngestionError) as caught:
            self.fetch([wide], kind='SELECT')
        error = caught.exception
        self.assertEqual((error.code, error.key, error.expected['width']), ('ATHENA_ROW_WIDTH_DIFFERS', DESCRIBE_ID, 1))
        self.assertEqual(error.observed, dict(query_id=DESCRIBE_ID, page=0, page_sha256=sha256(canonical(wide)),
                                              kept='kept#0', row=1, width=2))
        text = copy.deepcopy(page)  # A DESCRIBE-like single text cell gets no tolerance in a SELECT.
        text['ResultSet']['ResultSetMetadata']['ColumnInfo'].append(dict(Name='x', Label='x', Type='varchar'))
        text['ResultSet']['Rows'] = [{'Data': [{'VarCharValue': 'package_record_count'}, {'VarCharValue': 'x'}]},
                                     {'Data': [{'VarCharValue': '300\tx'}]}]
        with self.assertRaisesRegex(IngestionError, 'ROW_WIDTH_DIFFERS'):
            self.fetch([text], kind='SELECT')
        typed = copy.deepcopy(page)
        typed['ResultSet']['Rows'][1]['Data'][0] = {'VarCharValue': '3OO'}
        with self.assertRaises(IngestionError) as caught:
            self.fetch([typed], kind='SELECT')
        self.assertEqual((caught.exception.code, caught.exception.observed['row']), ('ATHENA_INTEGER_INVALID', 1))

    def test_describe_shape_errors_name_query_page_row_width_hash_and_capture(self):
        bad = real_pages()[0]
        bad['ResultSet']['Rows'][5]['Data'].append({'VarCharValue': 'string'})
        with self.assertRaises(IngestionError) as caught:
            self.fetch([bad])
        error = caught.exception
        self.assertEqual((error.code, error.key, error.expected), ('ATHENA_DESCRIBE_LINE_INVALID', DESCRIBE_ID,
                                                                    dict(width=1, cell='VarCharValue')))
        self.assertEqual(error.observed, dict(query_id=DESCRIBE_ID, page=0, page_sha256=sha256(canonical(bad)),
                                              kept='kept#0', row=5, width=2))
        self.assertEqual(self.kept, [(0, bad)])  # Kept before the shape was interpreted.
        self.assertEqual(error.diagnostic()['observed']['kept'], 'kept#0')

    def test_strings_are_kept_and_missing_or_structured_cells_fail_closed(self):
        complex_type = 'array<struct<reference_category:string,reference_type:string,reference_locator:string,comment:string>>'
        lines = ['', ' ', '\t', '\t\t', ' ' * 20 + '\t' + ' ' * 20 + '\t' + ' ' * 20, 'references          \t' + complex_type + '\t' + ' ' * 20,
                 'x\r\n', '# col_name', 'col_name            \tdata_type           \tcomment             ']
        self.assertEqual(self.fetch([with_lines(lines)])['lines'], lines)  # No strip, split, drop or header removal.
        for cells in ([], [{}], [{'VarCharValue': None}], [{'VarCharValue': 1}], [{'VarCharValue': 'a', 'Other': 'b'}],
                      [{'VarCharValue': 'a'}] * 3, None, 'a'):
            page = with_lines(['x'])
            page['ResultSet']['Rows'][0] = {'Data': cells} if cells is not None else {}
            with self.subTest(cells=cells), self.assertRaisesRegex(IngestionError, 'DESCRIBE_LINE_INVALID'):
                self.fetch([page])
        page = with_lines(['x'])
        page['ResultSet']['Rows'][0] = 'not a row'
        with self.assertRaisesRegex(IngestionError, 'DESCRIBE_LINE_INVALID'):
            self.fetch([page])
        real = real_pages()[0]['ResultSet']['ResultSetMetadata']['ColumnInfo']
        for columns in ([dict(Name='col_name', Label='col_name', Type='string')],  # PR #128 assumption.
                        [dict(c, Type='varchar') for c in real], real[::-1], real + [dict(Name='extra', Type='string')]):
            page = real_pages()[0]
            page['ResultSet']['ResultSetMetadata']['ColumnInfo'] = columns
            with self.subTest(columns=columns), self.assertRaisesRegex(IngestionError, 'DESCRIBE_COLUMNS_DIFFER'):
                self.fetch([page])
        self.assertEqual(self.fetch([with_lines([])])['lines'], [])  # execute_plan rejects an empty DESCRIBE.

    def test_pagination_limits_and_partial_failures_keep_received_pages(self):
        pages = split(real_pages()[0], (20, 20, 3), ('t1', 't2', None))
        result = self.fetch(pages)
        self.assertEqual((result['lines'], self.client.calls), (real_lines(), [None, 't1', 't2']))
        self.assertEqual([n for n, _ in self.kept], [0, 1, 2])
        with self.assertRaisesRegex(IngestionError, 'ATHENA_SERVICE_ERROR'):
            self.fetch(pages, failure=(1, RuntimeError('second page')))
        self.assertEqual(self.kept, [(0, pages[0])])
        repeated = split(real_pages()[0], (20, 23), ('t', 't'))
        with self.assertRaisesRegex(IngestionError, 'RESULT_TOKEN_INVALID'):
            self.fetch(repeated)
        self.assertEqual([n for n, _ in self.kept], [0, 1])
        with mock.patch.object(a, 'RESULT_BYTES', len(canonical(pages[0])) + 10), self.assertRaises(IngestionError) as caught:
            self.fetch(pages)
        self.assertEqual((caught.exception.code, caught.exception.observed['kept_pages']), ('ATHENA_RESULT_BYTES_LIMIT', 1))
        self.assertEqual([n for n, _ in self.kept], [0])  # The page over the limit is not kept.
        endless = [dict(with_lines(['x']), NextToken='t%d' % n) for n in range(17)]
        with self.assertRaises(IngestionError) as caught:
            self.fetch(endless)
        self.assertEqual((caught.exception.code, caught.exception.observed), ('ATHENA_RESULT_PAGE_LIMIT', dict(kept_pages=16)))
        self.assertEqual(len(self.kept), 16)  # Incomplete capture is reported, not truncated into a result.

        def broken(number, page):
            raise OSError('journal write failed')
        client = Results(pages)
        with self.assertRaisesRegex(OSError, 'journal write failed'):
            a.query_results(client, DESCRIBE_ID, kind='DESCRIBE', keep_page=broken)
        self.assertEqual(client.calls, [None])  # No further page after a failed persistence.


class JournalCaptureValidationTests(unittest.TestCase):
    def validate(self, journal):
        return a.validate_journal(PLAN.read_bytes(), journal, AUTH)

    def test_current_and_previous_journals_validate_and_capture_is_strict(self):
        current = json.loads((FIXTURE / 'execution-journal.json').read_bytes())
        self.validate(current)
        for path in (previous.FIXTURE / 'execution-journal.json', previous.VIEWS_FIXTURE / 'execution-journal.json'):
            self.validate(json.loads(path.read_bytes()))  # Journals without the field stay compatible.
        good = dict(query_id=DESCRIBE_ID, pages=real_pages())
        journal = copy.deepcopy(current)
        journal['executions']['describe_observations']['results_capture'] = good
        self.validate(journal)
        cases = [('describe_observations', dict(good, extra=1)), ('describe_observations', dict(good, query_id='other')),
                 ('describe_observations', dict(good, pages=real_pages() * 17)), ('describe_observations', dict(good, pages={})),
                 ('describe_observations', dict(good, pages=['page'])), ('describe_observations', [good]),
                 ('count_packages', dict(good, query_id=current['executions']['count_packages']['query_id']))]
        for key, capture in cases:
            journal = copy.deepcopy(current)
            journal['executions'][key]['results_capture'] = capture
            with self.subTest(key=key, capture=str(capture)[:60]), self.assertRaisesRegex(IngestionError, 'JOURNAL_CONFLICT'):
                self.validate(journal)
        ddl = dict(current, executions={'table-0': dict(current['executions']['table-0'], state='SUCCEEDED')})
        self.validate(ddl)
        ddl['executions']['table-0']['results_capture'] = dict(query_id=ddl['executions']['table-0']['query_id'], pages=[])
        with self.assertRaisesRegex(IngestionError, 'JOURNAL_CONFLICT'):
            self.validate(ddl)


class CurrentJournalGitHub(previous.RealJournalGitHub):
    """Selected REAL run 38109412318 metadata; SYNTHETIC transport ZIP with its own hash."""
    def __init__(self, raw):
        self.metadata = json.loads((FIXTURE / 'github-metadata.json').read_bytes())
        self.metadata['artifact'].update(size_in_bytes=len(raw), digest='sha256:' + sha256(raw))
        self.raw, self.calls = raw, []


class CurrentJournalResumeTests(unittest.TestCase):
    setUpClass = classmethod(support.AthenaRunTests.setUpClass.__func__)
    restore, execute = six.AthenaSixEntryResumeTests.restore, six.AthenaSixEntryResumeTests.execute
    fresh, readback = previous.AthenaSeventeenEntryResumeTests.fresh, previous.AthenaSeventeenEntryResumeTests.readback

    def setUp(self):
        support.AthenaRunTests.setUp(self)
        self.raw, self.original = PLAN.read_bytes(), (FIXTURE / 'execution-journal.json').read_bytes()
        self.ancestor = (previous.FIXTURE / 'execution-journal.json').read_bytes()  # 605578 bytes, also 17 entries.
        # Ancestor first: selection is by exact member path and hashes, never order/basename/size/count.
        self.members = [('athena-resume-source/execution-journal.json', self.ancestor),
                        ('athena-resume-source/sql-plan.json', self.raw),
                        ('athena-reports/authentication.json', (FIXTURE / 'authentication.json').read_bytes()),
                        ('athena-reports/execution-journal.json', self.original),
                        ('athena-reports/sql-plan.json', self.raw)]
        self.zipped = archive(self.members)  # SYNTHETIC transport, not the original 555455-byte ZIP.
        self.resume = r.ResumeSource(**dict(SOURCE, zip_sha256=sha256(self.zipped), zip_bytes=len(self.zipped)))
        self.github = CurrentJournalGitHub(self.zipped)
        self.executor_sha = 'd' * 40
        self.fresh('first')

    def seed(self):
        previous.AthenaSeventeenEntryResumeTests.seed(self)
        # REAL hosted GetQueryExecution (SUCCEEDED) and REAL administrative page for e3264498.
        self.pending = copy.deepcopy(self.known['describe_observations']['execution'])
        self.pending_pages = real_pages()

    def start_index(self):
        return next(i for i, event in enumerate(self.events) if event[0] == 'START')

    def test_current_source_restores_607331_member_and_preserves_ancestor(self):
        self.assertEqual(r.source_document(canonical(SOURCE)), r.ResumeSource(**SOURCE))
        self.assertEqual((sha256(self.original), len(self.original)), (JOURNAL_HASH, 607331))
        self.assertEqual((sha256(self.ancestor), len(self.ancestor)), (previous.JOURNAL_HASH, 605578))
        receipt = self.restore()
        self.assertEqual((receipt['restored_executions'], receipt['total_round_budget'],
                          receipt['remaining_unreserved_executions']), (17, 18, 1))
        self.assertEqual((receipt['source']['source_sha'], receipt['executor_source_sha']), (SOURCE['source_sha'], self.executor_sha))
        self.assertEqual(self.journal.read_bytes(), self.original)
        self.assertEqual((self.originals / 'execution-journal.json').read_bytes(), self.original)
        self.assertEqual((self.originals / 'source-artifact.zip').read_bytes(), self.zipped)
        ancestor, current = (json.loads(v)['executions'] for v in (self.ancestor, self.original))
        self.assertEqual({k: (e['query_id'], e['request'], e.get('start_attempts')) for k, e in ancestor.items()},
                         {k: (e['query_id'], e['request'], e.get('start_attempts')) for k, e in current.items()})
        self.assertEqual(Counter(e['state'] for e in current.values()), {'VERIFIED': 16, 'SUCCEEDED': 1})
        entry = current['describe_observations']
        self.assertEqual((entry['query_id'], entry['execution']['Status']['State'], entry['data_scanned_bytes']), (DESCRIBE_ID, 'SUCCEEDED', 0))
        self.assertNotIn('results', entry)  # The real failure kept no page: the gap this change closes.

    def test_17_known_get_only_real_describe_results_then_one_start_and_second_pass_zero(self):
        self.restore()
        self.seed()
        self.readback()
        self.assertFalse([e for e in self.events if e[0] != 'GET'])
        result = self.execute()
        self.assertEqual((result['historically_reserved_requests'], result['api_calls']['new_starts'],
                          result['api_calls']['idempotent_retransmissions'], result['distinct_query_execution_ids'],
                          result['remaining_unreserved_executions']), (17, 1, 0, 18, 0))
        pins = json.loads((six.FIXTURE / 'request-fingerprints.json').read_bytes())
        self.assertEqual([v['ClientRequestToken'] for v in self.athena.calls], [pins[17]['client_request_token']])
        first = self.start_index()
        self.assertTrue({('GET', v['query_id']) for v in self.known.values()} <= set(self.events[:first]))
        self.assertTrue({('RESULTS', self.known[k]['query_id']) for k in SELECTS} | {('RESULTS', DESCRIBE_ID)}
                        <= set(self.events[:first]))
        saved = json.loads(self.journal.read_bytes())['executions']
        observations = saved['describe_observations']
        self.assertEqual((observations['state'], observations['query_id'], observations['start_attempts']), ('VERIFIED', DESCRIBE_ID, 1))
        self.assertEqual(observations['results']['lines'], real_lines())
        self.assertEqual(observations['results']['pages'], real_pages())
        self.assertEqual(observations['execution'], self.known['describe_observations']['execution'])
        packages = saved['describe_packages']
        self.assertEqual((packages['state'], packages['identity_comparison']['sql_rule'], packages['request']['ClientRequestToken']),
                         ('VERIFIED', 'DESCRIBE_DATABASE_QUALIFIER_OMITTED', pins[17]['client_request_token']))
        glue = real_tables()['sbom_package_rows_v1']['StorageDescriptor']['Columns']
        self.assertEqual(packages['results']['lines'], [previous.describe_line(c['Name'], c['Type']) for c in glue])  # SYNTHETIC.
        self.assertFalse([k for k, e in saved.items() if 'results_capture' in e])
        statements = {s['id']: s for s in json.loads(self.raw)['statements']}
        for key in SELECTS:
            self.assertEqual(Counter(canonical(x) for x in saved[key]['results']['rows']),
                             Counter(canonical(x) for x in statements[key]['expected_rows']))
            self.assertEqual(saved[key]['results']['rows'], self.known[key]['results']['rows'])
        for key, entry in self.known.items():
            self.assertEqual((saved[key]['query_id'], saved[key]['request'], saved[key].get('start_attempts')),
                             (entry['query_id'], entry['request'], entry.get('start_attempts')))
        for statement, pin in zip(json.loads(self.raw)['statements'], pins):
            self.assertEqual(sha256(canonical(saved[statement['id']]['request'])), pin['request_sha256'])
        self.readback(require_complete=True)
        self.events.clear()
        self.assertEqual(self.execute()['api_calls']['start_query_execution'], 0)
        self.assertEqual((len(self.athena.calls), [e for e in self.events if e[0] == 'START']), (1, []))
        self.assertEqual(sha256((FIXTURE / 'execution-journal.json').read_bytes()), JOURNAL_HASH)
        self.assertEqual((self.originals / 'execution-journal.json').read_bytes(), self.original)

    def test_invalid_describe_results_keep_pages_and_block_the_last_start(self):
        def lines(value):
            return lambda test: setattr(test, 'pending_pages', [with_lines(value)])

        def extra_cell(test):
            test.pending_pages = real_pages()
            test.pending_pages[0]['ResultSet']['Rows'][5]['Data'].append({'VarCharValue': 'x'})

        def single_column(test):
            test.pending_pages = real_pages()
            test.pending_pages[0]['ResultSet']['ResultSetMetadata']['ColumnInfo'] = [dict(Name='col_name', Type='string')]

        def second_page_fails(test):
            test.pending_pages = split(real_pages()[0], (20, 23), ('t', None))
            original = test.athena.get_query_results

            def results(**kwargs):
                if kwargs['QueryExecutionId'] == DESCRIBE_ID and kwargs.get('NextToken') == 't':
                    raise RuntimeError('second page')
                return original(**kwargs)
            test.athena.get_query_results = results

        def state(value):
            return lambda test: test.pending['Status'].update(State=value)
        cases = [(extra_cell, 'DESCRIBE_LINE_INVALID', 1), (single_column, 'DESCRIBE_COLUMNS_DIFFER', 1),
                 (lines([]), 'DESCRIBE_EMPTY', None), (second_page_fails, 'ATHENA_SERVICE_ERROR', 1),
                 (state('FAILED'), 'QUERY_FAILED', 0), (state('CANCELLED'), 'QUERY_FAILED', 0)]
        for number, (change, code, kept) in enumerate(cases):
            self.fresh(str(number))
            self.restore()
            self.seed()
            change(self)
            with self.subTest(code=code), self.assertRaisesRegex(IngestionError, code):
                self.execute()
            self.assertEqual((self.athena.calls, [e for e in self.events if e[0] == 'START']), ([], []))
            saved = json.loads(self.journal.read_bytes())
            entry = saved['executions']['describe_observations']
            self.assertNotIn('describe_packages', saved['executions'])
            self.assertNotEqual(entry['state'], 'VERIFIED')
            self.assertEqual((entry['query_id'], entry['request']['ClientRequestToken']), (DESCRIBE_ID, DESCRIBE_TOKEN))
            if kept is not None:
                self.assertEqual(entry.get('results_capture', {}).get('pages', []), self.pending_pages[:kept])
            a.validate_journal(self.raw, saved, AUTH)  # Still restorable for a read-only reconciliation.

    def test_capture_write_failure_stops_before_any_start(self):
        self.restore()
        self.seed()
        write = a.s3_run.write_json

        def failing(path, value):
            if value['executions'].get('describe_observations', {}).get('results_capture', {}).get('pages'):
                raise OSError('journal write failed')
            return write(path, value)
        with mock.patch.object(a.s3_run, 'write_json', failing), self.assertRaisesRegex(OSError, 'journal write failed'):
            self.execute()
        self.assertEqual((self.athena.calls, self.events.count(('RESULTS', DESCRIBE_ID))), ([], 1))

    def test_last_instruction_failure_leaves_zero_budget_and_read_only_reconciliation(self):
        self.restore()
        self.seed()
        original = self.athena.get_query_results
        broken = {'on': True}

        def results(**kwargs):
            value = original(**kwargs)
            if broken['on'] and kwargs['QueryExecutionId'] not in {v['query_id'] for v in self.known.values()}:
                value['ResultSet']['Rows'][0]['Data'].append({'VarCharValue': 'x'})
            return value
        self.athena.get_query_results = results
        with self.assertRaisesRegex(IngestionError, 'DESCRIBE_LINE_INVALID'):
            self.execute()
        saved = json.loads(self.journal.read_bytes())['executions']
        self.assertEqual((len(saved), saved['describe_packages']['state'], len(saved['describe_packages']['results_capture']['pages'])),
                         (18, 'SUCCEEDED', 1))
        self.assertEqual(len(self.athena.calls), 1)
        broken['on'] = False  # A later pass only reads the same 18 IDs again.
        result = self.execute()
        self.assertEqual((result['api_calls']['start_query_execution'], result['distinct_query_execution_ids'],
                          result['remaining_unreserved_executions'], len(self.athena.calls)), (0, 18, 0, 1))

    def test_last_instruction_submitted_by_an_interrupted_attempt_is_only_read(self):
        self.restore()
        self.seed()
        known = {v['query_id'] for v in self.known.values()}
        original = self.athena.get_query_execution
        lost = {'on': True}

        def get(**kwargs):  # SYNTHETIC: the attempt that made the last Start loses its first read.
            if lost['on'] and kwargs['QueryExecutionId'] not in known:
                raise RuntimeError('connection lost after Start')
            return original(**kwargs)
        self.athena.get_query_execution = get
        with self.assertRaisesRegex(IngestionError, 'ATHENA_SERVICE_ERROR'):
            self.execute()
        saved = json.loads(self.journal.read_bytes())['executions']
        self.assertEqual((len(saved), saved['describe_observations']['state'], saved['describe_packages']['state']),
                         (18, 'VERIFIED', 'SUBMITTED'))
        query_id = saved['describe_packages']['query_id']
        lost['on'] = False
        self.events.clear()
        result = self.execute()  # Next attempt: the balance is zero, so the 18th ID is only read.
        self.assertEqual((result['api_calls']['start_query_execution'], result['historically_reserved_requests'],
                          result['remaining_unreserved_executions'], len(self.athena.calls)), (0, 18, 0, 1))
        self.assertEqual([e for e in self.events if e[0] == 'START'], [])
        self.assertTrue({('GET', query_id), ('RESULTS', query_id)} <= set(self.events))

if __name__ == '__main__':
    unittest.main()
