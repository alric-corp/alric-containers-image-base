"""Real selected API responses + synthetic negative mutations; all clients fake."""
from collections import Counter
import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics import athena_poc as a
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics import test_athena_poc as support

Athena, ROOT = support.Athena, support.ROOT

FIXTURE = ROOT/'tests/fixtures/sbom-analytics/athena-reconciliation'
AUTH = 'TomasAlric-PR124-lab-sbom-athena-v1'
PLAN_HASH = 'ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e'
QUERY_ID = 'f65fa3ea-3d73-4d3d-a2b6-13637500920d'
TOKEN = '80d33f677de36228e9c2d8ed6bf34207f6bd400c2d779fdfcdd42d8e245ca3d8'


class AthenaReconciliationTests(unittest.TestCase):
    # Reuse setup, not the author's test cases: no duplicated suite/count.
    setUpClass = classmethod(support.AthenaPocTests.setUpClass.__func__)
    setUp = support.AthenaPocTests.setUp

    def original(self):
        self.raw = (FIXTURE/'sql-plan.json').read_bytes()
        self.journal.write_bytes((FIXTURE/'execution-journal.json').read_bytes())
        self.athena = Athena(self.raw, self.expected, self.settings, self.glue)
        plan = json.loads(self.raw)
        statement = plan['statements'][0]
        submitted = json.loads(self.journal.read_bytes())['executions']['table-0']
        self.athena.executions[QUERY_ID] = dict(id=QUERY_ID, request=submitted['request'], statement=statement)
        self.athena.tokens[TOKEN] = self.athena.executions[QUERY_ID]
        self.remote = json.loads((FIXTURE/'query-execution.json').read_bytes())['QueryExecution']
        original_get = self.athena.get_query_execution
        self.gets = []
        def get(**kwargs):
            self.gets.append(kwargs['QueryExecutionId'])
            return {'QueryExecution': copy.deepcopy(self.remote)} if kwargs['QueryExecutionId'] == QUERY_ID else original_get(**kwargs)
        self.athena.get_query_execution = get
        table = json.loads((FIXTURE/'glue-table.json').read_bytes())['Table']
        self.glue.tables[table['Name']] = table
        return submitted

    def execute(self, **kwargs):
        return a.execute_plan(self.raw, self.athena, self.journal, authorized_sha256=sha256(self.raw),
                              authorization_reference=AUTH, **kwargs)

    def test_original_hashes_requests_and_rebuilt_plan_unchanged(self):
        first = self.original()
        self.assertEqual(sha256(self.raw), PLAN_HASH)
        self.assertEqual(sha256(self.journal.read_bytes()), '714c2e35c113c2f4185892f2431007d0e3ed945e1e5220627528fcc21e71f9ff')
        self.assertEqual(first['request'], a.request(json.loads(self.raw)['statements'][0], json.loads(self.raw)))
        self.assertEqual(first['request']['ClientRequestToken'], TOKEN)
        rebuilt = a.build_plan(self.proposal, self.inspection, self.root/'local', self.expected,
                               type(self).settings, 'lab-sbom-athena-v1')
        self.assertEqual(rebuilt, self.raw)

    def test_observed_sql_whitespace_catalog_and_safe_diagnostics(self):
        first = self.original()
        observed = []
        result = a._execution(self.athena, QUERY_ID, first['request'], observation=lambda *v:observed.append(v))
        self.assertEqual(result['QueryExecutionContext']['Catalog'], 'awsdatacatalog')
        self.assertEqual(a.execution_tokens(result['Query']), a.execution_tokens(first['request']['QueryString']))
        self.assertEqual(observed[0][1]['execution_parameters'], 'NOT_RETURNED')
        self.assertEqual(observed[0][0]['Statistics']['TotalExecutionTimeInMillis'], 438)
        self.assertEqual(observed[0][0]['Statistics']['EngineExecutionTimeInMillis'], 359)

    def test_sql_tokens_preserve_comments_literals_identifiers_and_boundaries(self):
        sql = "SELECT 'a  b', \"A B\", `x y`, 12, 1.2 FROM t WHERE x>=1 --keep\nAND y=2 /*exact*/"
        equivalent = sql.replace('SELECT ', 'SELECT\n').replace('FROM t', 'FROM\tt')
        self.assertEqual(a.execution_tokens(sql), a.execution_tokens(equivalent))
        changed = [sql.replace('a  b', 'a b'), sql.replace('A B', 'A  B'), sql.replace('x y', 'x  y'),
                   sql.replace('--keep\n', '--keep '), sql.replace('/*exact*/', '/* different */'),
                   sql.replace('>=', '>'), sql.replace('12', '1 2'), sql.replace('1.2', '1 . 2'),
                   sql.replace('SELECT', 'select'), sql.replace('AND', 'OR'), sql.replace('FROM t', 'FROM other'),
                   sql.replace('x>=1', 'x>=2'), sql.replace('y=2', 'y=3'), sql.replace('12, 1.2', '1.2, 12')]
        for text in changed:
            with self.subTest(text=text):self.assertNotEqual(a.execution_tokens(sql), a.execution_tokens(text))
        for text in ("SELECT 'unterminated", 'SELECT $x', 'SELECT /* outer /* nested */ 1', "SELECT 'a\\b'", 'SELECT \u00a01'):
            with self.subTest(text=text), self.assertRaisesRegex(IngestionError,'REPRESENTATION_UNSUPPORTED'):
                a.execution_tokens(text)

    def test_changed_query_context_id_type_column_and_predicate_rejected_before_next_start(self):
        first = self.original()
        changes = [lambda r:r.update(Query=r['Query'].replace('bigint', 'int')),
                   lambda r:r.update(Query=r['Query'].replace('framework string', 'other string')),
                   lambda r:r.update(Query=r['Query'].replace('poc_distroless_sbom.', 'other.')),
                   lambda r:r['QueryExecutionContext'].update(Catalog='AWSDATACATALOG'),
                   lambda r:r['QueryExecutionContext'].update(Catalog='other'),
                   lambda r:r['QueryExecutionContext'].update(Database='other'),
                   lambda r:r.update(WorkGroup='other'), lambda r:r.update(QueryExecutionId='other')]
        original = copy.deepcopy(self.remote)
        for change in changes:
            self.remote = copy.deepcopy(original);change(self.remote)
            with self.subTest(change=change),self.assertRaisesRegex(IngestionError,'IDENTITY_DIFFERS'):
                self.execute()
            saved=json.loads(self.journal.read_bytes())['executions']['table-0']
            self.assertIn('remote_observation',saved)
            self.assertIn('identity_comparison',saved)
            self.assertEqual(self.athena.calls,[])
        self.remote=original
        self.assertEqual(a._execution(self.athena,QUERY_ID,first['request'])['QueryExecutionId'],QUERY_ID)

    def test_missing_parameters_is_not_returned_returned_values_must_match(self):
        plan=json.loads(self.raw);statement=plan['statements'][5];submission=a.request(statement,plan)
        response=dict(QueryExecutionId='params',Query=statement['sql'],WorkGroup=plan['workgroup'],
                      QueryExecutionContext=dict(Catalog='awsdatacatalog',Database=plan['database']))
        seen=[]
        with patch.object(self.athena,'get_query_execution',return_value={'QueryExecution':response}):
            a._execution(self.athena,'params',submission,observation=lambda *v:seen.append(v))
            self.assertEqual(seen[-1][1]['execution_parameters'],'NOT_RETURNED')
            response['ExecutionParameters']=submission['ExecutionParameters']
            a._execution(self.athena,'params',submission)
            for bad in ([],['wrong'],None,True):
                response['ExecutionParameters']=bad
                with self.subTest(bad=bad),self.assertRaisesRegex(IngestionError,'IDENTITY_DIFFERS'):
                    a._execution(self.athena,'params',submission)
            del response['ExecutionParameters']
            response['Query']=response['Query'].replace('?', "'substituted'",1)
            with self.assertRaisesRegex(IngestionError,'IDENTITY_DIFFERS'):a._execution(self.athena,'params',submission)

    def test_parameter_journal_or_token_changed_rejected_before_start(self):
        self.original();base=json.loads(self.journal.read_bytes())
        for mutate in (lambda j:j['executions']['table-0']['request'].update(ExecutionParameters=['x']),
                       lambda j:j['executions']['table-0']['request'].update(ClientRequestToken='f'*64)):
            journal=copy.deepcopy(base);mutate(journal);self.journal.write_bytes(canonical(journal))
            with self.assertRaisesRegex(IngestionError,'JOURNAL_CONFLICT'):self.execute()
            self.assertEqual(self.athena.calls,[])

    def test_location_omission_only_and_other_table_format_guards(self):
        self.original();journal=json.loads(self.journal.read_bytes())
        resource=a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,journal)
        table=next(iter(resource['existing_objects'].values()))
        comparison=table['location_comparison'];self.assertEqual(comparison['expected'][:-1],comparison['observed'])
        expected=comparison['expected']
        a.location_readback(expected,expected)
        for bad in (expected[:-2], expected+'/', expected.rsplit('/',2)[0]+'/', expected.replace('/analytics/','//analytics/'),
                    expected.replace('/analytics/','/%2Fanalytics/'),expected.replace('sbom_observations','sbom_packages'),
                    expected.replace('sbom_observations','SBOM_observations'), expected.replace(self.expected['snapshot_id'],'a'*64),
                    expected.replace(self.expected['destination']['bucket'],'other-bucket'),expected+'?q=x',expected+'#x',
                    expected.replace('/analytics/','/../analytics/')):
            with self.subTest(bad=bad),self.assertRaisesRegex(IngestionError,'LOCATION_CONFLICT'):a.location_readback(expected,bad)
        original=copy.deepcopy(next(iter(self.glue.tables.values())))
        for field in ('InputFormat','OutputFormat','SerdeInfo'):
            bad=copy.deepcopy(original);bad['StorageDescriptor'][field]='wrong'
            self.glue.tables[bad['Name']]=bad
            with self.subTest(field=field),self.assertRaises(IngestionError):
                a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,journal)

    def test_old_submitted_succeeded_reconciles_17_starts_then_second_pass_zero(self):
        first=self.original()
        # Actual API contract: parameter lists may be omitted on ALL SELECTs.
        self.athena.changed=lambda r:r.pop('ExecutionParameters',None)
        before=a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,
                                   json.loads(self.journal.read_bytes()),journal_path=self.journal,
                                   plan_raw=self.raw,authorization_reference=AUTH)
        self.assertEqual(before['api_calls']['idempotent_retransmissions'],0)
        self.assertEqual(self.athena.calls,[])
        result=self.execute()
        self.assertEqual(len(self.athena.calls),17)
        a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,
                           json.loads(self.journal.read_bytes()),require_complete=True)
        self.assertEqual(result['api_calls']['new_starts'],17)
        self.assertEqual(result['api_calls']['idempotent_retransmissions'],0)
        self.assertFalse(any(v['ClientRequestToken']==TOKEN for v in self.athena.calls))
        self.assertEqual(result['distinct_query_execution_ids'],18)
        self.assertNotIn('stopped',self.athena.__dict__)
        saved=json.loads(self.journal.read_bytes());entry=saved['executions']['table-0']
        self.assertEqual(entry['query_id'],QUERY_ID);self.assertEqual(entry['request'],first['request'])
        self.assertEqual(entry['state'],'VERIFIED');self.assertEqual(entry['timing']['total_execution_time_ms'],438)
        parameter_entry=saved['executions']['01_find_images']
        self.assertEqual(parameter_entry['identity_comparison']['execution_parameters'],'NOT_RETURNED')
        self.assertEqual(parameter_entry['request'],a.request(json.loads(self.raw)['statements'][5],json.loads(self.raw)))
        self.assertGreater(entry['timing']['observation_delay_seconds'],120)
        self.assertEqual(Counter(self.athena.executions[e['query_id']]['statement']['kind'] for e in list(saved['executions'].values())
                                 if e['query_id']!=QUERY_ID),{'DDL':4,'SELECT':11,'DESCRIBE':2})
        second=self.execute();self.assertEqual(second['api_calls']['start_query_execution'],0)
        self.assertEqual(len(self.athena.calls),17)
        self.assertEqual(sha256((FIXTURE/'execution-journal.json').read_bytes()),
                         '714c2e35c113c2f4185892f2431007d0e3ed945e1e5220627528fcc21e71f9ff')

    def test_interrupted_resume_preserves_prefix_request_tokens_and_budget(self):
        self.original();original_start=self.athena.start_query_execution
        def fail(**kwargs):
            if kwargs['ClientRequestToken']==a.request(json.loads(self.raw)['statements'][8],json.loads(self.raw))['ClientRequestToken']:
                self.athena.start_query_execution=original_start
                self.athena.lost_response=True
            return original_start(**kwargs)
        self.athena.start_query_execution=fail
        with self.assertRaisesRegex(IngestionError,'START_OUTCOME_UNKNOWN'):self.execute()
        saved=json.loads(self.journal.read_bytes());prefix={k:copy.deepcopy(e) for k,e in saved['executions'].items() if e['state']=='VERIFIED'}
        restored=self.root/'new-runner-journal.json';restored.write_bytes(self.journal.read_bytes());self.journal=restored
        before=len(self.athena.calls);result=self.execute()
        self.assertEqual(len(self.athena.tokens),18)
        self.assertEqual(result['api_calls']['idempotent_retransmissions'],1)
        self.assertTrue(all(v['ClientRequestToken'] not in {e['request']['ClientRequestToken'] for e in prefix.values()}
                            for v in self.athena.calls[before:]))
        final=json.loads(self.journal.read_bytes())
        self.assertTrue(all(final['executions'][k]['query_id']==e['query_id'] and final['executions'][k]['request']==e['request']
                            for k,e in prefix.items()))

    def test_success_actual_timeout_or_missing_invalid_timestamps_does_not_advance(self):
        self.original();base=copy.deepcopy(self.remote)
        changes=[lambda r:r['Status'].update(SubmissionDateTime=None),
                 lambda r:r['Status'].pop('CompletionDateTime'),
                 lambda r:r['Status'].update(CompletionDateTime='2026-10-10T19:42:30'),
                 lambda r:r['Status'].update(CompletionDateTime='invalid'),
                 lambda r:r['Status'].update(CompletionDateTime=r['Status']['SubmissionDateTime']),
                 lambda r:r['Statistics'].pop('TotalExecutionTimeInMillis'),
                 lambda r:r['Statistics'].update(TotalExecutionTimeInMillis=True),
                 lambda r:r['Statistics'].update(EngineExecutionTimeInMillis=439)]
        for change in changes:
            self.journal.write_bytes((FIXTURE/'execution-journal.json').read_bytes());self.remote=copy.deepcopy(base);change(self.remote)
            with self.subTest(change=change),self.assertRaisesRegex(IngestionError,'TIMING_'):self.execute()
            self.assertEqual(self.athena.calls,[])
        self.remote=copy.deepcopy(base)
        start=datetime.fromisoformat(self.remote['Status']['SubmissionDateTime'])
        self.remote['Status']['CompletionDateTime']=(start+timedelta(seconds=121)).isoformat()
        self.remote['Statistics']['TotalExecutionTimeInMillis']=121000
        self.journal.write_bytes((FIXTURE/'execution-journal.json').read_bytes())
        with self.assertRaisesRegex(IngestionError,'QUERY_TIMEOUT'):self.execute()
        self.assertEqual(self.athena.calls,[]);self.assertNotIn('stopped',self.athena.__dict__)
        self.remote=base
        with self.assertRaisesRegex(IngestionError,'PRIOR_EXECUTION_FAILED'):self.execute()

    def test_failed_cancelled_and_active_expired_are_not_late_success(self):
        self.original()
        for state in ('FAILED','CANCELLED'):
            self.journal.write_bytes((FIXTURE/'execution-journal.json').read_bytes());self.remote['Status']['State']=state
            with self.subTest(state=state),self.assertRaisesRegex(IngestionError,'QUERY_FAILED'):self.execute()
            self.assertNotIn('stopped',self.athena.__dict__)
        self.journal.write_bytes((FIXTURE/'execution-journal.json').read_bytes());self.remote['Status']['State']='RUNNING'
        stopped=[]
        with patch.object(self.athena,'stop_query_execution',side_effect=lambda **kw:stopped.append(kw)):
            with self.assertRaisesRegex(IngestionError,'QUERY_TIMEOUT'):self.execute()
        self.assertEqual(stopped,[{'QueryExecutionId':QUERY_ID}]);self.assertEqual(self.athena.calls,[])

    def test_whole_journal_sequence_ids_and_schema_before_any_service_call(self):
        self.original();base=json.loads(self.journal.read_bytes())
        changes=[lambda j:j.update(protocol_version=2),lambda j:j.update(protocol_version=True),
                 lambda j:j.update(plan_sha256='a'*64),lambda j:j.update(authorization_reference='wrong'),
                 lambda j:j['executions']['table-0'].update(submitted_at=True),
                 lambda j:j['executions']['table-0'].update(state='VERIFIED'),
                 lambda j:j['executions'].update({'view-0':copy.deepcopy(j['executions']['table-0'])})]
        for change in changes:
            value=copy.deepcopy(base);change(value);self.journal.write_bytes(canonical(value))
            with self.subTest(change=change),self.assertRaises(IngestionError):self.execute()
            self.assertEqual(self.gets,[]);self.assertEqual(self.athena.calls,[])
        value=copy.deepcopy(base);entry=value['executions']['table-0'];entry.update(state='VERIFIED',data_scanned_bytes=0,execution=copy.deepcopy(self.remote))
        value['executions']['table-1']=dict(request=a.request(json.loads(self.raw)['statements'][1],json.loads(self.raw)),
                                          submitted_at=entry['submitted_at'],query_id=QUERY_ID,state='SUBMITTED')
        self.journal.write_bytes(canonical(value))
        with self.assertRaisesRegex(IngestionError,'QUERY_ID_INVALID'):self.execute()
        self.assertEqual(self.athena.calls,[])


if __name__=='__main__':unittest.main()
