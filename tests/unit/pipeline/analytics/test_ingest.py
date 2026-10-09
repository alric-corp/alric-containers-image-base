from contextlib import redirect_stdout
from dataclasses import asdict
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics.ingest import main, publish_reported
from scripts.pipeline.analytics.ingestion_types import Destination
from scripts.pipeline.analytics.normalize import export, prepare
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import load_plan, prepare_snapshot
from scripts.pipeline.analytics.spdx import canonical
from tests.unit.pipeline.analytics.fixture_support import synthetic
from tests.unit.pipeline.analytics.s3_support import FakeS3, ServiceError


class IngestDiagnosticTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sbom-ingest-cli-');self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = Destination('analytics-example','offline/poc','test-region-1','000000000000')
        self.batch = Path(export(prepare(synthetic(self.root/'input')),self.root/'output')['path'])
        self.config = self.root/'config.json'
        self.config.write_bytes(canonical(dict(protocol_version=1,destination=asdict(self.target))))
        self.plan_dir, self.report = self.root/'frozen-plan', self.root/'diagnostics/plan.json'

    def arguments(self):
        return ['--batch',str(self.batch),'--config',str(self.config),'--plan-dir',str(self.plan_dir),'--report',str(self.report)]

    def run_cli(self, argv):
        stream = io.StringIO()
        with redirect_stdout(stream):status = main(argv)
        return status, json.loads(stream.getvalue())

    def test_offline_cli_freezes_plan_and_retry_without_sdk_network_or_credentials(self):
        def forbidden(*args,**kwargs):raise AssertionError('network/build call from offline planner')
        with patch('socket.socket',side_effect=forbidden), patch('urllib.request.urlopen',side_effect=forbidden), \
                patch('subprocess.run',side_effect=forbidden), patch.dict('os.environ',{},clear=True):
            status,result = self.run_cli(self.arguments())
            self.assertEqual(status,0);self.assertEqual(result['code'],'PLAN_CREATED')
            self.assertEqual(result,json.loads(self.report.read_bytes()))
            plan = load_plan(self.plan_dir)
            self.assertEqual(result['snapshot_id'],plan.snapshot_id)
            self.assertEqual(result['cloud_calls'],0);self.assertFalse(result['complete']);self.assertFalse(result['catalog_eligible'])
            status,result = self.run_cli(self.arguments())
            self.assertEqual(status,0);self.assertEqual(result['code'],'PLAN_ALREADY_PRESENT_IDENTICAL')

    def test_invalid_input_produces_failure_json_with_known_batch_and_no_plan(self):
        (self.batch/'reports/records.json').write_bytes(b'private SPDX SECRET signed URL')
        status,result = self.run_cli(self.arguments())
        self.assertEqual(status,1);self.assertEqual(result['code'],'BATCH_BYTES_DIFFER')
        self.assertEqual(result['batch_id'],self.batch.name)
        self.assertFalse(result['complete']);self.assertFalse(self.plan_dir.exists())
        self.assertEqual(result,json.loads(self.report.read_bytes()))
        self.assertNotIn('SECRET',self.report.read_text())

    def test_invalid_arguments_and_configuration_produce_json_including_failures(self):
        status,result = self.run_cli(['--report',str(self.report),'--unknown','SECRET'])
        self.assertEqual(status,1);self.assertEqual(result['code'],'INVALID_ARGUMENTS')
        self.assertEqual(result,json.loads(self.report.read_bytes()))
        for body in (b'{',b'{"protocol_version":1,"protocol_version":1}',
                     canonical(dict(protocol_version=True,destination=asdict(self.target)))):
            self.config.write_bytes(body)
            status,result = self.run_cli(self.arguments())
            self.assertEqual(status,1);self.assertEqual(result['status'],'ERROR')
            self.assertFalse(result['catalog_eligible']);self.assertEqual(result,json.loads(self.report.read_bytes()))

    def test_diagnostics_cannot_overwrite_batch_plan_or_configuration_even_on_argument_failure(self):
        original = self.config.read_bytes()
        for report in (self.batch/'forbidden.json',self.plan_dir/'forbidden.json',self.config):
            args = self.arguments();args[-1] = str(report)
            for invalid in (False,True):
                status,result = self.run_cli(args + (['--bad','SECRET'] if invalid else []))
                self.assertEqual(status,1);self.assertEqual(result['stage'],'DIAGNOSTIC')
                self.assertFalse(result['complete'])
            if report != self.config:self.assertFalse(report.exists())
        self.assertEqual(self.config.read_bytes(),original)

    def test_non_local_report_and_symlink_report_are_rejected(self):
        report = self.root/'symlink.json';report.symlink_to(self.config)
        for destination in (report,Path('s3://not-authorized/report.json')):
            args = self.arguments();args[-1] = str(destination)
            status,result = self.run_cli(args)
            self.assertEqual(status,1);self.assertEqual(result['stage'],'DIAGNOSTIC')
            self.assertFalse(self.plan_dir.exists())

    def test_report_write_failure_cannot_be_returned_as_planning_success(self):
        with patch('scripts.pipeline.analytics.ingest.os.replace',side_effect=PermissionError('SECRET')):
            status,result = self.run_cli(self.arguments())
        self.assertEqual(status,1);self.assertEqual(result['code'],'REPORT_WRITE_FAILED')
        self.assertEqual(result['observed']['operation_code'],'PLAN_CREATED')
        self.assertFalse(result['complete']);self.assertNotIn('SECRET',canonical(result).decode())

    def test_ingestion_success_failure_and_reconciliation_have_separate_json_reports(self):
        plan = prepare_snapshot(self.batch,self.target);client = FakeS3();adapter = S3Adapter(client,self.target)
        failure_key = plan.key(plan.objects[1].path)
        def deny(op,request):
            if op == 'PutObject' and request['Key'] == failure_key:raise ServiceError(403,'AccessDenied')
        client.before = deny
        result = publish_reported(plan,adapter,self.report,protected_roots=(self.batch,))
        self.assertEqual(result['status'],'ERROR');self.assertEqual(result['code'],'ACCESS_DENIED')
        self.assertEqual(result['object'],failure_key);self.assertEqual(result['operation'],'PutObject')
        self.assertFalse(result['complete']);self.assertFalse(result['catalog_eligible']);self.assertFalse(result['retryable'])
        self.assertEqual(result,json.loads(self.report.read_bytes()));self.assertNotIn('SECRET',self.report.read_text())
        self.assertNotIn((self.target.bucket,plan.key('ingestion-manifest.json')),client.current)
        client.before = None
        result = publish_reported(plan,adapter,self.report,protected_roots=(self.batch,))
        self.assertTrue(result['complete']);self.assertEqual(result,json.loads(self.report.read_bytes()))
        self.assertTrue((self.batch/'complete.json').is_file())

    def test_failed_report_after_upload_reports_error_and_requires_reconciliation(self):
        plan = prepare_snapshot(self.batch,self.target);client = FakeS3();adapter = S3Adapter(client,self.target)
        with patch('scripts.pipeline.analytics.ingest.os.replace',side_effect=OSError('SECRET')):
            result = publish_reported(plan,adapter,self.report)
        self.assertEqual(result['code'],'REPORT_WRITE_FAILED');self.assertFalse(result['complete'])
        self.assertIn((self.target.bucket,plan.key('ingestion-manifest.json')),client.current)
        result = publish_reported(plan,adapter,self.report)
        self.assertEqual(result['code'],'SNAPSHOT_ALREADY_PRESENT_IDENTICAL')
        self.assertTrue(result['complete'])

    def test_invalid_diagnostic_destination_prevents_all_transport_operations(self):
        plan = prepare_snapshot(self.batch,self.target);client = FakeS3();adapter = S3Adapter(client,self.target)
        result = publish_reported(plan,adapter,self.batch/'reports/new-diagnostic.json')
        self.assertEqual(result['code'],'REPORT_INSIDE_INPUT');self.assertEqual(client.calls,[])
        self.assertFalse((self.batch/'reports/new-diagnostic.json').exists())
