"""Verified artifact restoration; no credentials, SDK clients or AWS calls."""
from dataclasses import asdict, replace
import copy
import io
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import yaml
from scripts.pipeline.analytics import athena_restore as r, athena_poc as a
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics import test_athena_reconciliation as support

ROOT, FIXTURE, AUTH, PLAN_HASH = support.ROOT, support.FIXTURE, support.AUTH, support.PLAN_HASH


def archive(members):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,body in members:
            if isinstance(name,zipfile.ZipInfo):z.writestr(name,body)
            else:z.writestr(name,body)
    return stream.getvalue()


class GitHub:
    """Selected real API metadata; synthetic ZIP, with externally frozen hashes."""
    def __init__(self, source, raw):
        self.metadata=json.loads((FIXTURE/'github-metadata.json').read_bytes())
        self.metadata['artifact'].update(size_in_bytes=len(raw),digest='sha256:'+sha256(raw))
        self.raw=raw;self.calls=[]

    def get_json(self, path):
        self.calls.append(path)
        if '/workflows/' in path:return {'id':self.metadata['run']['workflow_id'],'path':r.WORKFLOW}
        if '/artifacts/' in path:return copy.deepcopy(self.metadata['artifact'])
        if '/jobs?' in path:return copy.deepcopy(self.metadata['jobs'])
        return copy.deepcopy(self.metadata['run'])

    def download(self, artifact_id):
        self.calls.append(artifact_id);return self.raw


class AthenaRestoreTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.members=[('athena-reports/'+name,(FIXTURE/name).read_bytes()) for name in (
            'execution-journal.json','sql-plan.json','authentication.json')]
        self.raw=archive(self.members)
        self.source=r.ResumeSource(38080824102,1,11679714087,'2702c4010e8d7bff561388bd27e9a6109f878d6d',sha256(self.raw),len(self.raw),
            '714c2e35c113c2f4185892f2431007d0e3ed945e1e5220627528fcc21e71f9ff',2414,PLAN_HASH,257893)
        self.client=GitHub(self.source,self.raw)
        self.sha='a'*40;self.snapshot='6ae0d5a463a20961e4431cb86d7d969ff2157bf25428a22dd08aa119632548b6'

    def restore(self, **kwargs):
        return r.restore(self.client,self.source,self.root/'reports',self.root/'originals',executor_sha=self.sha,
                         authorized_sha256=PLAN_HASH,authorization_reference=AUTH,round_id='lab-sbom-athena-v1',
                         snapshot_id=self.snapshot,**kwargs)

    def test_source_exact_schema_types_and_unknowns(self):
        self.assertEqual(r.source_document(canonical(asdict(self.source))),self.source)
        for name,value in [('attempt',True),('zip_bytes',True),('source_sha','x'),('journal_sha256','x'),('extra',1)]:
            source=asdict(self.source);source[name]=value
            with self.subTest(name=name),self.assertRaises(IngestionError):r.source_document(canonical(source))
        with self.assertRaises(ValueError):r.source_document(b'{"attempt":1,"attempt":2}')

    def test_exact_private_originals_and_working_copy_and_provenance(self):
        receipt=self.restore()
        self.assertEqual(receipt['status'],'RESTORED_VERIFIED')
        self.assertEqual(receipt['restored_executions'],1)
        self.assertEqual(receipt['remaining_unreserved_executions'],17)
        self.assertEqual(receipt['source']['source_sha'],'2702c4010e8d7bff561388bd27e9a6109f878d6d')
        self.assertEqual(receipt['executor_source_sha'],self.sha)
        self.assertEqual(receipt['acquisition']['producer_job_id'],114297196683)
        self.assertEqual((self.root/'originals/source-artifact.zip').read_bytes(),self.raw)
        for name in ('execution-journal.json','sql-plan.json'):
            self.assertEqual((self.root/'reports'/name).read_bytes(),(FIXTURE/name).read_bytes())
            self.assertEqual((self.root/'originals'/name).read_bytes(),(FIXTURE/name).read_bytes())
        r.validate_working_restore(self.root/'reports/resume-receipt.json',self.root/'reports',executor_sha=self.sha,
                                  plan_sha256=PLAN_HASH,authorization_reference=AUTH,round_id='lab-sbom-athena-v1',snapshot_id=self.snapshot)
        (self.root/'reports/execution-journal.json').write_bytes(b'changed')
        self.assertEqual((self.root/'originals/execution-journal.json').read_bytes(),(FIXTURE/'execution-journal.json').read_bytes())
        with self.assertRaisesRegex(IngestionError,'WORKING_BYTES_DIFFER'):
            r.validate_working_restore(self.root/'reports/resume-receipt.json',self.root/'reports',executor_sha=self.sha,
                                      plan_sha256=PLAN_HASH,authorization_reference=AUTH,round_id='lab-sbom-athena-v1',snapshot_id=self.snapshot)

    def test_wrong_run_attempt_repository_commit_workflow_producer_and_api_digest(self):
        base=copy.deepcopy(self.client.metadata)
        mutations=[lambda m:m['run'].update(id=1),lambda m:m['run'].update(run_attempt=2),
                   lambda m:m['run']['repository'].update(full_name='other/repo'),
                   lambda m:m['run'].update(head_sha='b'*40),lambda m:m['run'].update(event='pull_request'),
                   lambda m:m['run'].update(path='.github/workflows/other.yml'),
                   lambda m:m['run'].update(head_branch='other'),
                   lambda m:m['artifact'].update(digest='sha256:'+'f'*64),lambda m:m['artifact'].update(expired=True),
                   lambda m:m['artifact']['workflow_run'].update(head_repository_id=1),
                   lambda m:m['jobs']['jobs'][0].update(run_attempt=2),
                   lambda m:m['artifact'].update(created_at='2026-10-10T20:42:36Z')]
        for mutate in mutations:
            self.client.metadata=copy.deepcopy(base);mutate(self.client.metadata)
            with self.subTest(mutate=mutate),self.assertRaises(IngestionError):self.restore()
            self.assertFalse((self.root/'reports/execution-journal.json').exists())
            self.assertNotIn(self.source.artifact_id,self.client.calls)
        self.client.metadata=base
        self.restore()  # Positive after negatives; expected failed source accepted.

    def test_download_hash_failure_keeps_zip_no_working_journal(self):
        self.client.raw=self.raw[:-1]+b'x'
        with self.assertRaisesRegex(IngestionError,'ZIP_DIGEST_DIFFERS'):self.restore()
        self.assertEqual((self.root/'originals/source-artifact.zip').read_bytes(),self.client.raw)
        self.assertFalse((self.root/'reports/execution-journal.json').exists())

    def test_journal_and_plan_digest_and_size_checked_before_working_copy(self):
        base=self.source
        for field,value in [('journal_sha256','a'*64),('journal_bytes',2413),('sql_plan_bytes',257892)]:
            with self.subTest(field=field):
                tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
                self.source=replace(base,**{field:value})
                guard='PLAN_DIGEST_DIFFERS' if field.startswith('sql_plan') else 'JOURNAL_DIGEST_DIFFERS'
                with self.assertRaisesRegex(IngestionError,guard):self.restore()
                self.assertFalse((self.root/'reports/execution-journal.json').exists())

    def test_wrong_round_authentication_and_journal_prefix_even_with_refrozen_test_hash(self):
        original=json.loads((FIXTURE/'execution-journal.json').read_bytes())
        for change in (lambda j:j.update(authorization_reference='other'),lambda j:j.update(protocol_version=2),
                       lambda j:j['executions'].update({'table-1':copy.deepcopy(j['executions']['table-0'])}),
                       lambda j:j['executions']['table-0']['request'].update(ClientRequestToken='f'*64)):
            with self.subTest(change=change):
                value=copy.deepcopy(original);change(value);body=canonical(value)
                self.raw=archive([(self.members[0][0],body)]+self.members[1:])
                self.source=replace(self.source,zip_sha256=sha256(self.raw),zip_bytes=len(self.raw),
                                    journal_sha256=sha256(body),journal_bytes=len(body))
                self.client=GitHub(self.source,self.raw)
                tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
                with self.assertRaises(IngestionError):self.restore()
                self.assertFalse((self.root/'reports/execution-journal.json').exists())

    def test_authentication_source_attempt_is_not_artifact_name_alone(self):
        auth=json.loads(self.members[2][1]);auth['attempt']='2'
        raw=archive(self.members[:2]+[(self.members[2][0],canonical(auth))])
        self.source=replace(self.source,zip_sha256=sha256(raw),zip_bytes=len(raw));self.client=GitHub(self.source,raw)
        with self.assertRaisesRegex(IngestionError,'AUTHENTICATION_DIFFERS'):self.restore()
        self.assertFalse((self.root/'reports/execution-journal.json').exists())

    def test_missing_truncated_duplicate_traversal_symlink_special_and_extra_zip(self):
        symlink=zipfile.ZipInfo(self.members[0][0]);symlink.create_system=3;symlink.external_attr=(stat.S_IFLNK|0o777)<<16
        special=zipfile.ZipInfo(self.members[0][0]);special.create_system=3;special.external_attr=(stat.S_IFIFO|0o600)<<16
        directory=zipfile.ZipInfo(self.members[0][0]);directory.external_attr=((stat.S_IFREG|0o600)<<16)|0x10
        invalid=[self.raw[:-20],archive(self.members[1:]),archive(self.members+[self.members[0]]),
                 archive(self.members+[('../evil',b'x')]),archive(self.members+[('/absolute',b'x')]),
                 archive(self.members+[('athena-reports\\evil',b'x')]),
                 archive([(symlink,self.members[0][1])]+self.members[1:]),
                 archive([(special,self.members[0][1])]+self.members[1:]),
                 archive([(directory,self.members[0][1])]+self.members[1:]),
                 archive(self.members+[('athena-reports/extra.json',b'{}')]),self.raw+b'unlisted']
        for raw in invalid:
            with self.subTest(size=len(raw)),self.assertRaises(IngestionError):r.archive_members(raw)
        selected,_=r.archive_members(self.raw);self.assertEqual(selected[self.members[0][0]],self.members[0][1])

    def test_local_central_crc_and_expansion_limits(self):
        raw=bytearray(self.raw);raw[30]^=1
        with self.assertRaises(IngestionError):r.archive_members(bytes(raw))
        raw=bytearray(self.raw);raw[14]^=1
        with self.assertRaises(IngestionError):r.archive_members(bytes(raw))
        with patch.object(r,'EXPANSION_LIMIT',3000),self.assertRaisesRegex(IngestionError,'EXPANSION_LIMIT'):
            r.archive_members(self.raw)
        with patch.object(r,'MEMBER_LIMIT',2),self.assertRaises(IngestionError):r.archive_members(self.raw)

    def test_false_uncompressed_size_does_not_hide_actual_expansion(self):
        raw=bytearray(self.raw)
        with zipfile.ZipFile(io.BytesIO(self.raw)) as z:
            info=z.getinfo('athena-reports/sql-plan.json')
            struct.pack_into('<I',raw,info.header_offset+22,1)
            central=z.start_dir
        while True:
            name_bytes,extra_bytes,comment_bytes=struct.unpack_from('<3H',raw,central+28)
            name=bytes(raw[central+46:central+46+name_bytes]).decode()
            if name=='athena-reports/sql-plan.json':
                struct.pack_into('<I',raw,central+24,1);break
            central+=46+name_bytes+extra_bytes+comment_bytes
        with self.assertRaisesRegex(IngestionError,'SIZE_DIFFERS'):r.archive_members(bytes(raw))
        with patch.object(r,'EXPANSION_LIMIT',3000),self.assertRaisesRegex(IngestionError,'EXPANSION_LIMIT'):
            r.archive_members(bytes(raw))

    def test_truncated_or_duplicate_json_journal_never_becomes_working_history(self):
        base=self.source
        for body in (self.members[0][1][:-5], b'{"protocol_version":1,"protocol_version":1}'):
            tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
            raw=archive([(self.members[0][0],body)]+self.members[1:])
            self.source=replace(base,zip_sha256=sha256(raw),zip_bytes=len(raw),journal_sha256=sha256(body),journal_bytes=len(body))
            self.client=GitHub(self.source,raw)
            with self.assertRaises(ValueError):self.restore()
            self.assertFalse((self.root/'reports/execution-journal.json').exists())

    def test_preexisting_symlinked_working_destinations_are_not_overwritten(self):
        (self.root/'reports').mkdir();(self.root/'reports/execution-journal.json').write_bytes(b'keep')
        with self.assertRaisesRegex(IngestionError,'DESTINATION_EXISTS'):self.restore()
        self.assertEqual((self.root/'reports/execution-journal.json').read_bytes(),b'keep')
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        (self.root/'target').mkdir();(self.root/'reports').symlink_to(self.root/'target')
        with self.assertRaisesRegex(IngestionError,'DESTINATION_EXISTS'):self.restore()

    def test_restore_failure_json_and_cli_execute_without_receipt_never_constructs_aws(self):
        source=self.root/'source.json';source.write_bytes(canonical(asdict(self.source)))
        report=self.root/'reports/restore.json'
        argv=['--source',str(source),'--reports',str(self.root/'reports'),'--originals',str(self.root/'originals'),
              '--report',str(report),'--executor-sha',self.sha,'--authorized-plan-sha256',PLAN_HASH,
              '--authorization-reference',AUTH,'--round-id','lab-sbom-athena-v1','--snapshot-id',self.snapshot]
        with patch.object(r,'GitHubActions',return_value=self.client),patch.object(self.client,'get_json',side_effect=TimeoutError('SECRET')):
            with patch('sys.stdout',new_callable=io.StringIO):self.assertEqual(r.main(argv),1)
        self.assertEqual(json.loads(report.read_bytes())['code'],'RESUME_INVALID');self.assertNotIn('SECRET',report.read_text())
        with patch.object(a,'aws_clients') as clients,patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(a.main(['--config',str(ROOT/'policies/analytics/lab-poc.json'),'--athena-config',str(ROOT/'policies/analytics/athena-lab-poc.json'),
                '--report',str(self.root/'reports/execute.json'),'--output',str(self.root/'recovered'),'--session-name','test',
                '--round-id','lab-sbom-athena-v1','--authorized-plan-sha256',PLAN_HASH,'--authorization-reference',AUTH]),1)
            clients.assert_not_called()

    def test_workflow_restore_before_oidc_and_real_reports_path_and_no_fallback(self):
        value=yaml.load((ROOT/'.github/workflows/sbom-analytics-athena-lab-poc.yml').read_text(),Loader=yaml.BaseLoader)
        job=value['jobs']['athena'];steps=job['steps']
        self.assertEqual(job['permissions'],{'contents':'read','actions':'read','id-token':'write'})
        restore=next(i for i,s in enumerate(steps) if s['name']=='Restore exact prior journal before AWS authentication')
        credentials=next(i for i,s in enumerate(steps) if s.get('id')=='credentials')
        execution=next(i for i,s in enumerate(steps) if 'Recover S3 snapshot' in s['name'])
        self.assertLess(restore,credentials);self.assertLess(credentials,execution)
        self.assertIn('GH_TOKEN',steps[restore]['env']);self.assertNotIn('GH_TOKEN',job.get('env',{}))
        self.assertIn('--reports "$RUNNER_TEMP/athena-reports"',steps[restore]['run'])
        self.assertIn('--resume-receipt "$RUNNER_TEMP/athena-reports/resume-receipt.json"',steps[execution]['run'])
        self.assertIn('assert os.environ[\'RESUME_SOURCE\']',steps[2]['run'])
        self.assertEqual(set(value['on']),{'workflow_dispatch'})
        self.assertIn('athena-resume-source',steps[-1]['with']['path'])


if __name__=='__main__':unittest.main()
