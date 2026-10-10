"""No AWS credentials, network or SDK initialization; service-shaped injected clients."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import yaml

from scripts.pipeline.analytics import poc
from scripts.pipeline.analytics.ingestion_types import Destination, IngestionError
from scripts.pipeline.analytics.snapshot import load_plan
from scripts.pipeline.analytics.spdx import canonical, sha256
from scripts.pipeline.analytics.normalize import export, prepare
from tests.unit.pipeline.analytics.fixture_support import synthetic
from tests.unit.pipeline.analytics.s3_support import FakeS3, ServiceError

ROOT = Path(__file__).resolve().parents[4]


class Client(FakeS3):
    def __init__(self):
        super().__init__('us-east-1')
        self.probe = None

    def put_object(self, **kwargs):
        if 'IfNoneMatch' not in kwargs:
            error = ServiceError(403, 'AccessDenied')
            error.response['Error']['Message'] = 'with an explicit deny in a resource-based policy'
            raise error
        return super().put_object(**kwargs)

    def get_bucket_location(self, **kwargs):
        return {'LocationConstraint': None}

    def get_bucket_versioning(self, **kwargs):
        return {'Status':'Enabled'}

    def get_bucket_ownership_controls(self, **kwargs):
        return {'OwnershipControls':{'Rules':[{'ObjectOwnership':'BucketOwnerEnforced'}]}}

    def get_bucket_encryption(self, **kwargs):
        return {'ServerSideEncryptionConfiguration':{'Rules':[{'ApplyServerSideEncryptionByDefault':{'SSEAlgorithm':'AES256'}}]}}

    def get_public_access_block(self, **kwargs):
        return {'PublicAccessBlockConfiguration':dict.fromkeys(('BlockPublicAcls','IgnorePublicAcls','BlockPublicPolicy','RestrictPublicBuckets'),True)}

    def get_bucket_policy(self, **kwargs):
        return {'Policy':json.dumps({'Version':'2012-10-17','Statement':[]})}


class PocTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.expected = poc.config(ROOT/'policies/analytics/lab-poc.json')
        self.package = ROOT/'tests/fixtures/sbom-analytics/lab-frozen-plan.zip'
        self.descriptor = ROOT/'tests/fixtures/sbom-analytics/lab-frozen-plan.json'
        self.client = Client()
        role = self.expected['expected_role_arn']
        account = role.split(':')[4]
        self.session = 'poc-test-session'
        self.identity = {'Account':account,'Arn':f'arn:aws:sts::{account}:assumed-role/{role.split("/")[-1]}/{self.session}',
                         'UserId':self.expected['expected_role_id']+':'+self.session}
        self.sts = SimpleNamespace(get_caller_identity=lambda:self.identity)

    def unpack(self):
        poc.unpack(self.package,self.descriptor,self.root/'plan',self.expected)
        return self.root/'plan'

    def test_original_frozen_bytes_are_preserved_and_validated_offline(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')), patch('subprocess.run',side_effect=AssertionError('code execution forbidden')):
            path = self.unpack()
        plan = load_plan(path)
        self.assertEqual(len(plan.objects),19)
        self.assertEqual(sum(len(o.body) for o in plan.objects),630308)
        self.assertEqual(plan.snapshot_id,self.expected['snapshot_id'])
        with zipfile.ZipFile(self.package) as z:
            for info in z.infolist():
                self.assertEqual((path/info.filename).read_bytes(),z.read(info))

    def test_package_hash_failure_before_cloud_or_destination(self):
        raw = self.root/'package.zip'; raw.write_bytes(self.package.read_bytes()+b'tampered')
        with self.assertRaisesRegex(IngestionError,'PACKAGE_BYTES_DIFFER'):
            poc.unpack(raw,self.descriptor,self.root/'plan',self.expected)
        self.assertFalse((self.root/'plan').exists())
        self.assertEqual(self.client.calls,[])

    def test_duplicate_traversal_symlink_or_extra_members_rejected(self):
        for member in ('../escape','/absolute','batch\\file','batch/unexpected.json','plan.json'):
            raw=self.root/'changed.zip'
            with zipfile.ZipFile(self.package) as old, zipfile.ZipFile(raw,'w') as new:
                for i in old.infolist():new.writestr(i,old.read(i))
                new.writestr(member,b'bad')
            d=json.loads(self.descriptor.read_bytes());d.update(package_sha256=sha256(raw.read_bytes()),package_bytes=raw.stat().st_size)
            desc=self.root/'desc.json';desc.write_bytes(canonical(d))
            with self.subTest(member=member),self.assertRaises((IngestionError,ValueError)):
                poc.unpack(raw,desc,self.root/'plan',self.expected)
        with zipfile.ZipFile(self.package) as old, zipfile.ZipFile(raw,'w') as new:
            for i in old.infolist():
                i.external_attr=0o120777<<16
                new.writestr(i,old.read(i))
        d.update(package_sha256=sha256(raw.read_bytes()),package_bytes=raw.stat().st_size);desc.write_bytes(canonical(d))
        with self.assertRaisesRegex(IngestionError,'MEMBER_TYPE'):
            poc.unpack(raw,desc,self.root/'plan',self.expected)

    def test_expected_snapshot_or_frozen_contents_differ_before_transport(self):
        path=self.unpack()
        expected=copy.deepcopy(self.expected);expected['snapshot_id']='a'*64
        with self.assertRaisesRegex(IngestionError,'IDENTITY_DIFFERS'):
            poc.publish(path,self.client,self.sts,expected,self.session,self.root/'reports','test')
        (path/'batch/complete.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):
            poc.publish(path,self.client,self.sts,self.expected,self.session,self.root/'reports','test')
        self.assertEqual(self.client.calls,[])

    def test_admin_wrong_account_role_or_roleid_rejected_before_object_calls(self):
        path=self.unpack()
        for field,value in [('Account','000000000000'),('Arn','arn:aws:iam::712107929769:user/Tomas-Instructor'),('UserId','AROA_OTHER:session')]:
            original=dict(self.identity);self.identity[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(IngestionError,'STS_IDENTITY_DIFFERS'):
                poc.publish(path,self.client,self.sts,self.expected,self.session,self.root/'reports','test')
            self.identity=original
        self.assertEqual(self.client.calls,[])

    def test_publication_retry_and_recovery_with_original_input_hidden(self):
        path=self.unpack()
        result=poc.publish(path,self.client,self.sts,self.expected,self.session,self.root/'reports','test')
        self.assertTrue(result['publication']['complete']);self.assertEqual(result['retry']['code'],'SNAPSHOT_ALREADY_PRESENT_IDENTICAL')
        self.assertEqual(result['retry_put_calls'],0)
        self.assertEqual(result['smoke']['deny_source'],'RESOURCE_POLICY_EXPLICIT_DENY')
        shutil.rmtree(path)
        # Reader has only client and external expectations; no producer paths.
        with patch.object(poc,'load_plan',side_effect=AssertionError('producer fallback forbidden')):
            recovered=poc.recover(self.client,self.sts,self.expected,self.session,self.root/'recovered')
        self.assertEqual(recovered['inspection']['observations'],6);self.assertEqual(recovered['inspection']['packages'],300)
        self.assertFalse(recovered['github_artifact_fallback'])
        for o in recovered['inspection']['raw_traceability']:
            self.assertEqual(sha256((self.root/'recovered'/o['raw_spdx_path']).read_bytes()),o['sbom_sha256'])

    def test_partial_failure_does_not_approve_or_delete(self):
        path=self.unpack()
        original=self.client.before
        def fail(name,request):
            if name=='PutObject' and request['Key'].endswith('reports/records.json'):
                raise ServiceError(403,'AccessDenied')
        self.client.before=fail
        with self.assertRaises(IngestionError):
            poc.publish(path,self.client,self.sts,self.expected,self.session,self.root/'reports','test')
        self.assertFalse(json.loads((self.root/'reports/publication.json').read_bytes())['complete'])
        self.assertFalse(any(k.endswith('ingestion-manifest.json') for b,k in self.client.current))
        self.client.before=original
        # Resume integrated publication with the same frozen request, not a new smoke identity.
        from scripts.pipeline.analytics.ingest import publish_reported
        from scripts.pipeline.analytics.s3_ingestion import S3Adapter
        result=publish_reported(load_plan(path),S3Adapter(self.client,Destination(**self.expected['destination'])),self.root/'reports/resume.json')
        self.assertTrue(result['complete'])

    def test_writer_and_reader_sessions_have_no_nonanalytics_or_delete_permissions(self):
        for writer in (True,False):
            policy=poc.session_policy(self.expected,writer=writer)
            actions={a for s in policy['Statement'] for a in s['Action']}
            self.assertEqual('s3:PutObject' in actions,writer)
            self.assertFalse(any(a.startswith(('iam:','ecr:')) or 'Delete' in a or a=='s3:*' for a in actions))
            objects=next(s for s in policy['Statement'] if 's3:GetObject' in s['Action'])
            self.assertTrue(objects['Resource'].endswith('/sbom-analytics/poc-v1/snapshots/*'))
            self.assertNotIn('query-results',json.dumps(policy));self.assertNotIn('tfstate',json.dumps(policy))

    def test_failure_cli_json_does_not_expose_sdk_message_or_discover_credentials(self):
        report=self.root/'report.json'
        with patch.object(poc,'aws_clients',side_effect=ServiceError(403,'AccessDenied')),redirect_stdout(io.StringIO()):
            status=poc.main(['recover','--config',str(ROOT/'policies/analytics/lab-poc.json'),'--report',str(report),'--output',str(self.root/'out'),'--session-name',self.session])
        self.assertEqual(status,1);self.assertEqual(json.loads(report.read_bytes())['code'],'AccessDenied')
        self.assertNotIn('SECRET',report.read_text())
        with patch.dict('os.environ',{},clear=True),self.assertRaisesRegex(IngestionError,'TEMPORARY_CREDENTIALS_REQUIRED'):
            poc.aws_clients(self.expected)

    def test_invalid_arguments_still_emit_safe_failure_json(self):
        report=self.root/'diagnostic.json'
        with redirect_stdout(io.StringIO()) as stdout:
            status=poc.main(['--report',str(report),'--unknown','SECRET'])
        self.assertEqual(status,1)
        self.assertEqual(json.loads(report.read_bytes())['code'],'POC_ARGUMENTS_INVALID')
        self.assertNotIn('SECRET',stdout.getvalue())
        original=self.package.read_bytes()
        with redirect_stdout(io.StringIO()):
            status=poc.main(['--package',str(self.package),'--report',str(self.package),'--unknown'])
        self.assertEqual(status,1);self.assertEqual(self.package.read_bytes(),original)

    def test_reader_workflow_manual_guards_and_sparse_inputs(self):
        doc=yaml.safe_load((ROOT/'.github/workflows/sbom-analytics-lab-poc.yml').read_text())
        self.assertEqual(doc.get('on',doc.get(True)),{'workflow_dispatch':{}})
        self.assertEqual(doc['permissions'],{})
        for name,job in doc['jobs'].items():
            self.assertEqual(job['environment'],'DEV');self.assertIn("github.ref == 'refs/heads/develop'",job['if'])
            self.assertIn("github.event_name == 'workflow_dispatch'",job['if'])
            self.assertEqual(job['permissions'],{'contents':'read','id-token':'write'})
            commands='\n'.join(s.get('run','') for s in job['steps'])
            self.assertNotIn('terraform',commands);self.assertNotIn('aws ecr',commands);self.assertNotIn('assume-role',commands)
            action=next(s for s in job['steps'] if s.get('uses','').startswith('aws-actions/configure-aws-credentials@'))
            self.assertEqual(action['with']['role-to-assume'],'${{ steps.pipeline.outputs.AWS_ROLE_ARN }}')
            self.assertIs(action['with']['use-existing-credentials'],False)
            self.assertIn('inline-session-policy',action['with'])
        reader=doc['jobs']['recover'];checkout=next(s for s in reader['steps'] if s.get('uses','').startswith('actions/checkout@'))
        self.assertNotIn('tests',checkout['with']['sparse-checkout'])
        self.assertIn('frameworks',checkout['with']['sparse-checkout'])
        self.assertFalse(any(s.get('uses','').startswith('actions/download-artifact') for s in reader['steps']))

    def test_corporate_document_layout_with_explicit_synthetic_context(self):
        ctx=synthetic(self.root/'input',framework='nodejs22')
        ctx['origin'].update(repository='example/corporate-factory',ref='refs/heads/development',event='workflow_dispatch')
        ctx['images'][0]['image_repository']='registry.corporate.example/image-base-nodejs22'
        names=['sbom-index.spdx.json','sbom-x86_64.spdx.json','sbom-aarch64.spdx.json']
        folder=self.root/'corporate-structure';(folder/'sbom').mkdir(parents=True)
        for item,name in zip(ctx['images'][0]['documents'],names):
            new=folder/'sbom'/name;new.write_bytes(Path(item['path']).read_bytes());item['path']=str(new)
        for name in ('apko.lock.json','build-inputs.json','validated-index.json'):
            (folder/name).write_bytes(canonical({'fixture':'SYNTHETIC_STRUCTURE_ONLY','schema_not_claimed':True}))
        result=export(prepare(ctx),self.root/'out')
        data=poc.read_completed(result['path'])
        self.assertEqual(len(data['observations']),3)
        self.assertTrue(all(r['repository']=='example/corporate-factory' and r['publication_authority'] is False for r in data['observations']))
        self.assertTrue(all(r['validation_record_sha256'] is None for r in data['observations']))


if __name__=='__main__':unittest.main()
