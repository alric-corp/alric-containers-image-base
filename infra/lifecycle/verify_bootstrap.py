#!/usr/bin/env python3
"""Read-back of Factory accounts, roles, source grants and release storage."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.pipeline.release.release_manifest import configuration
from scripts.pipeline.release.validate_ecr_repository import validate_repository


def main():
    cfg = configuration()
    catalog = sorted(p.stem for p in (ROOT/'frameworks').glob('*.yaml'))
    evidence = {'checked_at':datetime.now(timezone.utc).isoformat(), 'environments':{},
                'oidc_execution_verified':False, 'hom_promotion_verified':False}
    for env, profile in [('DEV','default'),('HOM','revolution-dev')]:
        conf = cfg[env]
        def aws(*args):
            raw = subprocess.run(['aws',*args,'--profile',profile,'--region',conf['region'],'--output','json'],
                                 check=True,capture_output=True,text=True,timeout=60).stdout
            return json.loads(raw)
        assert aws('sts','get-caller-identity')['Account']==conf['account_id']
        role = aws('iam','get-role','--role-name',conf['role_name'])['Role']
        trust = role['AssumeRolePolicyDocument']['Statement']
        assert len(trust)==1
        assert trust[0]['Action']=='sts:AssumeRoleWithWebIdentity'
        assert trust[0]['Condition']['StringEquals']=={
            'token.actions.githubusercontent.com:aud':'sts.amazonaws.com',
            'token.actions.githubusercontent.com:sub':cfg['subject_prefix']+':environment:'+env}
        assert role['MaxSessionDuration']==10800
        bucket = conf['release_bucket']
        assert aws('s3api','get-bucket-versioning','--bucket',bucket)['Status']=='Enabled'
        assert all(aws('s3api','get-public-access-block','--bucket',bucket)['PublicAccessBlockConfiguration'].values())
        rules=aws('s3api','get-bucket-encryption','--bucket',bucket)['ServerSideEncryptionConfiguration']['Rules']
        assert rules[0]['ApplyServerSideEncryptionByDefault']['SSEAlgorithm']=='AES256'
        repositories=aws('ecr','describe-repositories')['repositories']
        repositories=[r for r in repositories if r['repositoryName'].startswith('image-base-')]
        assert sorted(r['repositoryName'].removeprefix('image-base-') for r in repositories)==catalog
        for repo in repositories:
            validate_repository({'repositories':[repo]},repo['repositoryName'],conf['account_id'],conf['region'])
            if env=='DEV':
                policy=json.loads(aws('ecr','get-repository-policy','--repository-name',repo['repositoryName'])['policyText'])
                reader=next(s for s in policy['Statement'] if s['Sid']=='FactoryHomReadExactSource')
                assert reader['Principal']['AWS']==f'arn:aws:iam::{cfg["HOM"]["account_id"]}:role/{cfg["HOM"]["role_name"]}'
                assert not any('Put' in a or 'Delete' in a or 'Upload' in a for a in reader['Action'])
        evidence['environments'][env]={'account':conf['account_id'],'region':conf['region'],
            'role':role['Arn'],'exact_environment_subject':True,'release_bucket':bucket,
            'versioned_encrypted_private_bucket':True,'catalog_count':len(repositories),
            'stable_only_mutability':True}
    directory=ROOT/'docs/evidence/dev-hom-bootstrap'
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'aws-readback.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__ == '__main__':
    main()
