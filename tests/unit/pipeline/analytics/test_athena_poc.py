"""Service-shaped clients only. These tests execute no real Athena/S3 operation."""
import base64
from collections import Counter
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from scripts.pipeline.analytics import athena_poc as a, poc, parquet
from scripts.pipeline.analytics.catalog import catalog_plan
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import load_plan, publish_snapshot, read_snapshot, recover_snapshot
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics.s3_support import FakeS3, ServiceError

ROOT = Path(__file__).resolve().parents[4]


class Glue:
    def __init__(self, expected, settings):
        self.expected, self.settings, self.tables = expected, settings, {}
        self.error = None

    def get_database(self, **kwargs):
        assert kwargs == dict(CatalogId=self.expected['destination']['expected_bucket_owner'], Name=self.settings['database'])
        return {'Database': {'Name': kwargs['Name'], 'CatalogId': kwargs['CatalogId']}}

    def get_table(self, **kwargs):
        if self.error:
            raise self.error
        if kwargs['Name'] not in self.tables:
            raise ServiceError(400, 'EntityNotFoundException')
        return {'Table': self.tables[kwargs['Name']]}


class Athena:
    """Returns frozen expected rows, to exercise API/error/codec contracts only.

    This is deliberately NOT an SQL engine or a hosted result claim.
    """
    def __init__(self, raw, expected, settings, glue):
        self.plan, self.expected, self.settings, self.glue = json.loads(raw), expected, settings, glue
        self.calls, self.tokens, self.executions = [], {}, {}
        self.lost_response, self.running, self.failure, self.changed, self.page_size = False, False, None, None, 1000

    def get_work_group(self, **kwargs):
        return {'WorkGroup': dict(Name=self.settings['workgroup'], State='ENABLED', Configuration=dict(
            EnforceWorkGroupConfiguration=True, BytesScannedCutoffPerQuery=self.settings['scan_cutoff_bytes'],
            PublishCloudWatchMetricsEnabled=False, RequesterPaysEnabled=False,
            EngineVersion={'SelectedEngineVersion':'Athena engine version 3'},
            ResultConfiguration=a.result_configuration(self.expected, self.settings)))}

    def start_query_execution(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        token = kwargs['ClientRequestToken']
        if token in self.tokens:
            assert self.tokens[token]['request'] == kwargs
            return {'QueryExecutionId': self.tokens[token]['id']}
        statement = next(s for s in self.plan['statements'] if a.request(s, self.plan) == kwargs)
        query_id = 'q-' + str(len(self.tokens)+1)
        entry = dict(id=query_id, request=copy.deepcopy(kwargs), statement=statement)
        self.tokens[token] = entry
        self.executions[query_id] = entry
        if statement['kind'] == 'DDL':
            keys = [self.plan['table_names'][k] for k in a.TABLE_NAMES]
            number = int(statement['id'].split('-')[1]) + (2 if statement['id'].startswith('view-') else 0)
            name = keys[number].split('.')[1]
            value = dict(Name=name, DatabaseName=self.settings['database'], CatalogId=self.expected['destination']['expected_bucket_owner'])
            if number < 2:
                table_kind = ('observations','packages')[number]
                types = dict(string='string', int32='int', int64='bigint', boolean='boolean', strings='array<string>',
                             references='array<struct<reference_category:string,reference_type:string,reference_locator:string,comment:string>>')
                value.update(TableType='EXTERNAL_TABLE', StorageDescriptor=dict(
                    Columns=[dict(Name=c['name'],Type=types[c['type']]) for c in parquet.definition()['tables'][table_kind]],
                    Location=self.expected['destination']['bucket']))
                value['StorageDescriptor']['Location'] = Destination(**self.expected['destination']).uri(self.expected['snapshot_id']) + 'analytics/sbom_' + table_kind + '/'
            else:
                encoded = canonical(dict(originalSql=statement['sql'].split(' AS\n',1)[1], catalog=self.settings['catalog'], schema=self.settings['database']))
                value.update(TableType='VIRTUAL_VIEW', ViewOriginalText='/* Presto View: ' + base64.b64encode(encoded).decode() + ' */')
            self.glue.tables[name] = value
        if self.lost_response:
            self.lost_response = False
            raise TimeoutError('SECRET SDK message')
        return {'QueryExecutionId':query_id}

    def get_query_execution(self, **kwargs):
        entry = self.executions[kwargs['QueryExecutionId']]
        request = entry['request']
        result = dict(QueryExecutionId=entry['id'], Query=request['QueryString'], WorkGroup=request['WorkGroup'],
                      QueryExecutionContext=request['QueryExecutionContext'], Status={'State': 'RUNNING' if self.running else self.failure or 'SUCCEEDED'},
                      ResultConfiguration=copy.deepcopy(request['ResultConfiguration']),
                      EngineVersion={'EffectiveEngineVersion':'Athena engine version 3'},
                      Statistics=dict(DataScannedInBytes=100, ResultReuseInformation={'ReusedPreviousResult':False}))
        result['ResultConfiguration']['OutputLocation'] += entry['id'] + '.csv'
        if 'ExecutionParameters' in request:
            result['ExecutionParameters'] = request['ExecutionParameters']
        if self.changed:
            self.changed(result)
        return {'QueryExecution':result}

    def get_query_results(self, **kwargs):
        statement = self.executions[kwargs['QueryExecutionId']]['statement']
        rows = statement['expected_rows']
        if rows is None:
            rows = [{'col_name':'schema_version\tint\t'}]
        keys = list(rows[0])
        numeric = {'observation_count','package_record_count','component_records','total','purls_null','purls_empty',
                   'references_null','references_empty','distinct_image_platforms','run_id','run_attempt','artifact_id'}
        info = [dict(Name=k, Label=k, Type='bigint' if k in numeric else 'varchar') for k in keys]
        converted = [[{} if row[k] is None else {'VarCharValue': canonical(row[k]).decode() if k in statement['json_columns']
                      else str(row[k])} for k in keys] for row in rows]
        if statement['kind'] == 'SELECT':
            converted.insert(0, [{'VarCharValue':k} for k in keys])
        start = int(kwargs.get('NextToken','0'))
        result = dict(ResultSet=dict(ResultSetMetadata={'ColumnInfo':info}, Rows=[{'Data':r} for r in converted[start:start+self.page_size]]))
        if start + self.page_size < len(converted):
            result['NextToken'] = str(start+self.page_size)
        return result

    def stop_query_execution(self, **kwargs):
        self.running, self.failure = False, 'CANCELLED'
        self.stopped = kwargs['QueryExecutionId']
        return {}


class AthenaPocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.source = Path(cls.tmp.name)
        cls.expected = poc.config(ROOT/'policies/analytics/lab-poc.json')
        cls.settings = a.config(ROOT/'policies/analytics/athena-lab-poc.json')
        poc.unpack(ROOT/'tests/fixtures/sbom-analytics/lab-frozen-plan.zip',ROOT/'tests/fixtures/sbom-analytics/lab-frozen-plan.json',cls.source/'plan',cls.expected)
        cls.payload = load_plan(cls.source/'plan')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.s3 = FakeS3('us-east-1')
        self.adapter = S3Adapter(self.s3, self.payload.destination)
        publish_snapshot(self.payload, self.adapter)
        self.s3.calls.clear()
        self.settings = dict(type(self).settings)
        fingerprint = a.snapshot_fingerprint(read_snapshot(self.adapter,self.expected['snapshot_id']))
        # Fake versions/hashes are TEST inputs, not evidence for the historical S3.
        self.settings.update({k:fingerprint[k] for k in ('manifest_sha256','manifest_version_id')})
        recover_snapshot(self.adapter,self.expected['snapshot_id'],self.root/'local')
        self.inspection = poc.inspect_recovered(self.root/'local',self.expected)
        self.proposal = catalog_plan(self.adapter,self.expected['snapshot_id'],database=self.settings['database'],table_prefix=self.settings['table_prefix'])
        self.raw = a.build_plan(self.proposal,self.inspection,self.root/'local',self.expected,self.settings,'test-round')
        self.glue = Glue(self.expected,self.settings)
        self.athena = Athena(self.raw,self.expected,self.settings,self.glue)
        self.session = 'test-oidc-session'
        role = self.expected['expected_role_arn']
        account = self.expected['destination']['expected_bucket_owner']
        self.sts = SimpleNamespace(get_caller_identity=lambda:dict(Account=account,Arn=f'arn:aws:sts::{account}:assumed-role/{role.split("/")[-1]}/{self.session}',UserId=self.expected['expected_role_id']+':'+self.session))
        self.journal = self.root/'journal.json'

    def execute(self, **kwargs):
        return a.execute_plan(self.raw,self.athena,self.journal,authorized_sha256=sha256(self.raw),authorization_reference='TEST_ONLY owner ref',**kwargs)

    def test_frozen_18_statement_budget_and_no_replace_or_create_database(self):
        plan=json.loads(self.raw)
        self.assertEqual(Counter(s['kind'] for s in plan['statements']),{'DDL':5,'SELECT':11,'DESCRIBE':2})
        self.assertFalse(self.proposal['execute'])
        self.assertEqual(self.raw,a.build_plan(self.proposal,self.inspection,self.root/'local',self.expected,self.settings,'test-round'))
        for statement in plan['statements']:
            self.assertEqual(statement['sql_sha256'],sha256(statement['sql'].encode()))
            self.assertNotIn('IF NOT EXISTS',statement['sql']);self.assertNotIn('OR REPLACE',statement['sql'])
            self.assertNotIn('CREATE DATABASE',statement['sql'])
        self.assertTrue(all(uri.endswith('/analytics/sbom_'+name+'/') for name,uri in
                            [('observations',self.proposal['locations']['sbom_observations']),('packages',self.proposal['locations']['sbom_packages'])]))

    def test_session_policy_small_scoped_intersection_and_read_only_planning(self):
        for execute in (False,True):
            policy=a.session_policy(self.expected,self.settings,execute=execute)
            self.assertLessEqual(len(json.dumps(policy,separators=(',',':'))),2048)
            actions={v for s in policy['Statement'] for v in s['Action']}
            self.assertFalse(any(v.startswith(('iam:','ecr:')) or '*' in v or 'Delete' in v for v in actions))
            self.assertEqual('athena:StartQueryExecution' in actions,execute)
            for s in policy['Statement']:
                if 's3:PutObject' in s['Action']:
                    self.assertTrue(s['Resource'].endswith('/query-results/poc-v1/*'))
            table=policy['Statement'][-1]['Resource'][-1]
            self.assertIn('poc_snapshot_'+self.expected['snapshot_id']+'_*',table)
            self.assertNotIn('tfstate',json.dumps(policy))

    def test_real_package_records_but_fake_cloud_full_sequence_without_producer_inputs(self):
        with patch.object(poc,'load_plan',side_effect=AssertionError('no producer fallback')),patch('socket.socket',side_effect=AssertionError('no cloud')):
            result=a.run(self.s3,self.sts,self.athena,self.glue,self.expected,self.settings,self.session,'test-round',self.root/'reports',self.root/'recovered',authorized_sha256=sha256(self.raw),authorization_reference='TEST_ONLY owner ref')
        self.assertEqual(result['query_executions'],18)
        self.assertEqual(result['code'],'ATHENA_RESULTS_VERIFIED')
        self.assertTrue(result['snapshot_bytes_and_versions_unchanged'])
        self.assertEqual(len(result['raw_traceability']),6)
        self.assertEqual(len(self.glue.tables),5)
        self.assertFalse(any(name=='PutObject' for name,_ in self.s3.calls))
        self.assertFalse(result['publication_authority'])

    def test_planning_has_no_query_or_resource_mutation(self):
        result=a.run(self.s3,self.sts,self.athena,self.glue,self.expected,self.settings,self.session,'test-round',self.root/'reports',self.root/'recovered')
        self.assertEqual(result['status'],'PROPOSED');self.assertFalse(result['execute'])
        self.assertEqual(self.athena.calls,[]);self.assertEqual(self.glue.tables,{})

    def test_parameters_are_encoded_not_interpolated_and_tokens_cover_context(self):
        plan=json.loads(self.raw);statement=plan['statements'][5]
        statement['parameters']=[a._literal("a'b\nUNION ALL SELECT")]
        request=a.request(statement,plan)
        self.assertEqual(request['ExecutionParameters'],["'a''b\nUNION ALL SELECT'"])
        self.assertNotIn("a''b",request['QueryString'])
        self.assertEqual(request,a.request(statement,plan))
        changed=copy.deepcopy(plan);changed['round_id']='other'
        self.assertNotEqual(request['ClientRequestToken'],a.request(statement,changed)['ClientRequestToken'])
        with self.assertRaises(IngestionError):a._literal(True)

    def test_no_authorization_or_wrong_hash_stops_before_start(self):
        for hash_value,reference in [('a'*64,'owner'),(sha256(self.raw),''),(None,'owner')]:
            with self.subTest(hash=hash_value),self.assertRaises(IngestionError):
                a.execute_plan(self.raw,self.athena,self.journal,authorized_sha256=hash_value,authorization_reference=reference)
        self.assertEqual(self.athena.calls,[])

    def test_lost_success_response_retry_same_persisted_request_not_extra_execution(self):
        self.athena.lost_response=True
        with self.assertRaisesRegex(IngestionError,'ATHENA_START_OUTCOME_UNKNOWN'):self.execute()
        persisted=json.loads(self.journal.read_bytes())
        self.assertEqual(persisted['executions']['table-0']['request'],self.athena.calls[0])
        self.execute()
        self.assertEqual(len(self.athena.tokens),18)
        self.assertEqual(self.athena.calls[0],self.athena.calls[1])

    def test_verified_restart_does_not_start_any_more_queries(self):
        self.execute();before=len(self.athena.calls)
        self.execute()
        self.assertEqual(len(self.athena.calls),before)
        self.assertEqual(len(self.athena.tokens),18)

    def test_journal_request_conflict_and_changed_round_rejected(self):
        self.athena.lost_response=True
        with self.assertRaises(IngestionError):self.execute()
        journal=json.loads(self.journal.read_bytes());journal['executions']['table-0']['request']['WorkGroup']='wrong'
        self.journal.write_bytes(canonical(journal))
        with self.assertRaisesRegex(IngestionError,'JOURNAL_CONFLICT'):self.execute()
        self.assertEqual(len(self.athena.calls),1)

    def test_timeout_includes_service_wait_and_cancels_one_query_then_stops(self):
        self.athena.running=True
        ticks=iter((0,121))
        with self.assertRaisesRegex(IngestionError,'QUERY_TIMEOUT'):
            self.execute(clock=lambda:next(ticks),sleep=lambda _:None)
        self.assertEqual(self.athena.stopped,'q-1');self.assertEqual(len(self.athena.tokens),1)
        journal=json.loads(self.journal.read_bytes())
        self.assertEqual(journal['executions']['table-0']['cancellation_observation']['Status']['State'],'CANCELLED')
        with self.assertRaisesRegex(IngestionError,'PRIOR_EXECUTION_FAILED'):self.execute()

    def test_failure_stops_sequence_and_keeps_query_id(self):
        self.athena.failure='FAILED'
        with self.assertRaisesRegex(IngestionError,'QUERY_FAILED'):self.execute()
        self.assertEqual(len(self.athena.tokens),1)
        self.assertEqual(json.loads(self.journal.read_bytes())['executions']['table-0']['query_id'],'q-1')

    def test_result_reuse_engine_context_destination_and_scan_guards(self):
        changes=[lambda r:r['Statistics']['ResultReuseInformation'].update(ReusedPreviousResult=True),
                 lambda r:r['EngineVersion'].update(EffectiveEngineVersion='wrong'),
                 lambda r:r.update(WorkGroup='wrong'),
                 lambda r:r['ResultConfiguration'].update(OutputLocation='s3://wrong/out'),
                 lambda r:r['Statistics'].update(DataScannedInBytes=104857601)]
        for change in changes:
            self.athena.changed=change
            self.journal.unlink(missing_ok=True)
            with self.subTest(change=change),self.assertRaises(IngestionError):self.execute()
        self.assertFalse(any(s['statement']['kind']=='SELECT' for s in self.athena.tokens.values()))

    def test_pagination_and_duplicate_sensitive_row_comparison(self):
        self.athena.page_size=40
        self.execute()
        journal=json.loads(self.journal.read_bytes())
        result=journal['executions']['nested_values']['results']
        self.assertEqual(len(result['rows']),300);self.assertGreater(len(result['pages']),1)
        rows=json.loads(self.raw)['statements'][5]['expected_rows']
        self.assertNotEqual(Counter(canonical(r) for r in rows),Counter(canonical(r) for r in rows+rows[:1]))

    def test_mismatching_duplicate_rows_are_preserved_and_rejected(self):
        original=self.athena.get_query_results
        def changed(**kwargs):
            result=original(**kwargs)
            result['ResultSet']['Rows'].append(copy.deepcopy(result['ResultSet']['Rows'][-1]))
            return result
        self.athena.get_query_results=changed
        with self.assertRaisesRegex(IngestionError,'RESULTS_DIFFER'):self.execute()
        journal=json.loads(self.journal.read_bytes())
        self.assertIn('results',journal['executions']['01_find_images'])
        self.assertEqual(len(self.athena.tokens),6)

    def test_unknown_schema_boolean_limits_and_oversized_session_rejected(self):
        for key,value in [('protocol_version',2),('execution_limit',True),('result_reuse',True),('results_prefix','snapshots/')]:
            config=dict(type(self).settings);config[key]=value
            path=self.root/'settings.json';path.write_bytes(canonical(config))
            with self.subTest(key=key),self.assertRaises(IngestionError):a.config(path)
        expected=copy.deepcopy(self.expected);expected['destination']['prefix']='p'*500
        with self.assertRaisesRegex(IngestionError,'SESSION_POLICY_TOO_LARGE'):
            a.session_policy(expected,self.settings,execute=True)

    def test_budget_extra_statement_cannot_start_and_datetimes_are_recorded(self):
        bad=json.loads(self.raw);bad['statements'].append(copy.deepcopy(bad['statements'][-1]));raw=canonical(bad)
        with self.assertRaisesRegex(IngestionError,'BUDGET_DIFFERS'):
            a.execute_plan(raw,self.athena,self.journal,authorized_sha256=sha256(raw),authorization_reference='TEST_ONLY owner ref')
        self.assertEqual(self.athena.calls,[])
        import datetime
        self.athena.changed=lambda r:r['Status'].update(SubmissionDateTime=datetime.datetime(2026,1,1,tzinfo=datetime.timezone.utc))
        self.execute()
        self.assertIn('2026-01-01T00:00:00+00:00',self.journal.read_text())

    def test_result_tokens_header_or_column_changes_and_unknown_nested_types_rejected(self):
        original=self.athena.get_query_results
        for scenario in ('token','header','metadata'):
            self.journal.unlink(missing_ok=True)
            calls=[]
            def changed(**kwargs):
                result=original(**kwargs);calls.append(kwargs)
                if scenario=='token':result['NextToken']='same'
                if scenario=='header':result['ResultSet']['Rows'][0]={'Data':[{'VarCharValue':'wrong'}]}
                if scenario=='metadata' and len(calls)>1:result['ResultSet']['ResultSetMetadata']['ColumnInfo'][0]['Type']='boolean'
                if scenario=='metadata':result['NextToken']='0' if len(calls)==1 else '1'
                return result
            self.athena.get_query_results=changed
            with self.subTest(scenario=scenario),self.assertRaises(IngestionError):self.execute()
        with self.assertRaisesRegex(IngestionError,'JSON_RESULT_TYPE_DIFFERS'):
            a._cell({'VarCharValue':'[]'},dict(Name='purls',Type='array(varchar)'),('purls',))

    def test_workgroup_enforcement_and_complete_catalog_required(self):
        original=self.athena.get_work_group
        def changed(**kwargs):
            result=original(**kwargs);result['WorkGroup']['Configuration']['EnforceWorkGroupConfiguration']=False
            return result
        self.athena.get_work_group=changed
        with self.assertRaisesRegex(IngestionError,'WORKGROUP_DIFFERS'):
            a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal)
        self.athena.get_work_group=original
        with self.assertRaisesRegex(IngestionError,'CATALOG_INCOMPLETE'):
            a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,require_complete=True)

    def test_view_pretty_printing_is_allowed_but_different_logic_is_not(self):
        sql="SELECT o.a FROM db.t o JOIN db.u p ON o.hash = p.hash WHERE o.scope = 'platform' AND p.subject = false"
        rendered='SELECT "o"."a"\nFROM "db"."t" AS "o" JOIN "db"."u" AS "p" ON ("o"."hash" = "p"."hash") WHERE ("o"."scope" = \'platform\') AND ("p"."subject" = false)'
        self.assertEqual(a._view_tokens(sql),a._view_tokens(rendered))
        self.assertNotEqual(a._view_tokens(sql),a._view_tokens(sql.replace("'platform'","'index'")))
        self.assertNotEqual(a._view_tokens(sql),a._view_tokens(sql.replace('db.u','db.other')))
        with self.assertRaisesRegex(IngestionError,'SQL_UNSUPPORTED'):a._view_tokens(sql.replace(' AND ',' OR '))

        with self.assertRaisesRegex(IngestionError,'SQL_UNSUPPORTED'):a._view_tokens('SELECT o.a() FROM db.t o')

    def test_null_empty_string_number_and_nested_json_are_distinct(self):
        self.assertIsNone(a._cell({},dict(Name='s',Type='varchar'),()))
        self.assertEqual(a._cell({'VarCharValue':''},dict(Name='s',Type='varchar'),()),'')
        self.assertEqual(a._cell({'VarCharValue':'12'},dict(Name='i',Type='bigint'),()),12)
        self.assertEqual(a._cell({'VarCharValue':'[]'},dict(Name='purls',Type='varchar'),('purls',)),[])
        self.assertIsNone(a._cell({},dict(Name='purls',Type='varchar'),('purls',)))
        self.assertEqual(a._cell({'VarCharValue':'["a,b", "[x]"]'},dict(Name='purls',Type='varchar'),('purls',)),['a,b','[x]'])
        with self.assertRaises(ValueError):a._cell({'VarCharValue':'{"x":1,"x":2}'},dict(Name='ref',Type='varchar'),('ref',))

    def test_catalog_collision_is_not_absence_and_access_denied_not_legacy(self):
        name=next(iter(self.proposal['table_names'].values())).split('.')[1]
        self.glue.tables[name]={'Name':name}
        with self.assertRaisesRegex(IngestionError,'NAME_CONFLICT'):
            a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal)
        self.assertEqual(self.athena.calls,[])
        self.glue.error=ServiceError(403,'AccessDeniedException')
        with self.assertRaisesRegex(IngestionError,'GLUE_READ_ERROR'):
            a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal)

    def test_owned_catalog_resume_and_changed_view_location_columns_rejected(self):
        self.execute();journal=json.loads(self.journal.read_bytes())
        a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,journal,require_complete=True)
        table=next(v for v in self.glue.tables.values() if v['TableType']=='EXTERNAL_TABLE')
        table['StorageDescriptor']['Columns'][0]['Comment']='optional API metadata'
        a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,journal,require_complete=True)
        table['StorageDescriptor']['Columns'][0]['Type']='binary'
        with self.assertRaisesRegex(IngestionError,'COLUMNS_CONFLICT'):
            a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,journal)
        table['StorageDescriptor']['Columns'][0]['Type']='string'
        table['StorageDescriptor']['Location']='s3://wrong/'
        with self.assertRaisesRegex(IngestionError,'LOCATION_CONFLICT'):
            a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,journal)
        table['StorageDescriptor']['Location']=self.proposal['locations']['sbom_observations']
        view=next(v for v in self.glue.tables.values() if v['TableType']=='VIRTUAL_VIEW')
        view['ViewOriginalText']='/* Presto View: '+base64.b64encode(canonical(dict(originalSql='SELECT observation_id FROM other.table',catalog=self.settings['catalog'],schema=self.settings['database']))).decode()+' */'
        with self.assertRaisesRegex(IngestionError,'VIEW_CONFLICT'):
            a.resource_readback(self.athena,self.glue,self.expected,self.settings,self.proposal,journal)

    def test_wrong_role_or_snapshot_stops_before_athena(self):
        sts=SimpleNamespace(get_caller_identity=lambda:dict(Account='712107929769',Arn='admin',UserId='admin'))
        with self.assertRaisesRegex(IngestionError,'STS_IDENTITY_DIFFERS'):
            a.run(self.s3,sts,self.athena,self.glue,self.expected,self.settings,self.session,'test-round',self.root/'reports',self.root/'recovered')
        settings=dict(self.settings,manifest_sha256='a'*64)
        with self.assertRaisesRegex(IngestionError,'SNAPSHOT_REFERENCE_DIFFERS'):
            a.run(self.s3,self.sts,self.athena,self.glue,self.expected,settings,self.session,'test-round',self.root/'reports',self.root/'recovered')
        self.assertEqual(self.athena.calls,[])

    def test_unknown_saved_request_cannot_start_during_reconciliation(self):
        reports=self.root/'reports';reports.mkdir()
        journal=dict(plan_sha256=sha256(self.raw),authorization_reference='TEST_ONLY owner ref',executions={
            'unapproved':dict(query_id=None,request={'QueryString':'SELECT 1'})})
        (reports/'execution-journal.json').write_bytes(canonical(journal))
        with self.assertRaisesRegex(IngestionError,'JOURNAL_CONFLICT'):
            a.run(self.s3,self.sts,self.athena,self.glue,self.expected,self.settings,self.session,'test-round',reports,self.root/'recovered',
                  authorized_sha256=sha256(self.raw),authorization_reference='TEST_ONLY owner ref')
        self.assertEqual(self.athena.calls,[])

    def test_missing_temporary_credentials_and_failure_json_without_sdk_message(self):
        with patch.dict('os.environ',{},clear=True),self.assertRaisesRegex(IngestionError,'TEMPORARY_CREDENTIALS_REQUIRED'):
            a.aws_clients(self.expected)
        report=self.root/'diagnostic/result.json'
        with patch.object(a,'aws_clients',side_effect=ServiceError(403,'AccessDenied')),redirect_stdout(io.StringIO()):
            status=a.main(['--config',str(ROOT/'policies/analytics/lab-poc.json'),'--athena-config',str(ROOT/'policies/analytics/athena-lab-poc.json'),
                           '--report',str(report),'--output',str(self.root/'out'),'--session-name',self.session,'--round-id','test-round'])
        self.assertEqual(status,1);self.assertEqual(json.loads(report.read_bytes())['code'],'AccessDenied')
        self.assertEqual(json.loads(report.read_bytes())['snapshot_id'],self.expected['snapshot_id'])
        self.assertNotIn('SECRET',report.read_text())

    def test_bad_arguments_report_json_without_secret(self):
        report=self.root/'bad.json'
        with redirect_stdout(io.StringIO()):status=a.main(['--report',str(report),'--bad','SECRET'])
        self.assertEqual(status,1);self.assertEqual(json.loads(report.read_bytes())['code'],'ATHENA_ARGUMENTS_INVALID')
        self.assertNotIn('SECRET',report.read_text())

    def test_manual_workflow_guards_session_and_evidence_not_cloud_admin(self):
        text=(ROOT/'.github/workflows/sbom-analytics-athena-lab-poc.yml').read_text()
        workflow=yaml.load(text,Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow['on']),{'workflow_dispatch'})
        job=workflow['jobs']['athena']
        self.assertIn("github.ref == 'refs/heads/develop'",job['if'])
        self.assertIn("github.event_name == 'workflow_dispatch'",job['if'])
        self.assertEqual(job['environment'],'DEV');self.assertEqual(job['timeout-minutes'],'45')
        credential=next(s for s in job['steps'] if s.get('id')=='credentials')
        self.assertEqual(credential['with']['role-duration-seconds'],'3600')
        self.assertIn('steps.session.outputs.policy',credential['with']['inline-session-policy'])
        checkout=job['steps'][0]
        self.assertNotIn('tests/fixtures',checkout['with']['sparse-checkout'])
        self.assertEqual(job['steps'][-1]['if'],'always()')
        for forbidden in ('Tomas-Instructor','terraform apply','put-role-policy','workflow.yml','publish_reported','smoke('):
            self.assertNotIn(forbidden,text)


if __name__ == '__main__':
    unittest.main()
