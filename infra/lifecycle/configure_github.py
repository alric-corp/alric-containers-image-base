#!/usr/bin/env python3
"""Prepare DEV/HOM Environments for the reviewed Factory configuration.

Does not merge code, change the default branch, or enable promotion. Existing
review gates are preserved. GitHub Environment branch policies allow only the
code branch; neither account is represented by a Git branch.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT/'policies/release/environments.json').read_text())
REPO = CONFIG['repository']


def api(path, method='GET', payload=None, missing=False):
    args = ['gh', 'api', f'repos/{REPO}/{path}'.rstrip('/'), '--method', method]
    if payload is not None:
        args += ['--input', '-']
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, check=False, timeout=60)
    if missing and result.returncode and 'HTTP 404' in result.stderr:
        return None
    if result.returncode:
        raise RuntimeError(f'GitHub {method} {path} failed: {result.stderr}')
    return json.loads(result.stdout) if result.stdout.strip() else None


def variable(path, name, value):
    exists = api(f'{path}/{name}', missing=True)
    api(f'{path}/{name}' if exists else path, 'PATCH' if exists else 'POST',
        {'name':name, 'value':value})


def main():
    for env in ('DEV', 'HOM'):
        cfg = CONFIG[env]
        path = f'environments/{env}'
        existing = api(path, missing=True)
        if existing:
            rules = existing.get('protection_rules', [])
            if any(r['type'] not in ('branch_policy',) for r in rules):
                raise ValueError(f'{env} has existing review gates; preserve them for an explicit migration')
        api(path, 'PUT', {'deployment_branch_policy': {'protected_branches':False, 'custom_branch_policies':True},
                         'can_admins_bypass':False})
        policies = api(f'{path}/deployment-branch-policies')['branch_policies']
        if any(r['name'] != CONFIG['branch'] or r.get('type') != 'branch' for r in policies):
            raise ValueError(f'{env} allows an unexpected ref; reconcile explicitly before activation')
        if not policies:
            api(f'{path}/deployment-branch-policies', 'POST', {'name':CONFIG['branch'], 'type':'branch'})
        arn = f'arn:aws:iam::{cfg["account_id"]}:role/{cfg["role_name"]}'
        for key, value in {'AWS_REGION':cfg['region'], 'AWS_ACCOUNT_ID':cfg['account_id'],
                           'AWS_ROLE_ARN':arn, 'RELEASE_BUCKET':cfg['release_bucket']}.items():
            variable(path+'/variables', key, value)
        for key, value in {f'{env}_ROLE_ARN':arn, f'{env}_ACCOUNT_ID':cfg['account_id'],
                           f'{env}_REGION':cfg['region']}.items():
            variable('actions/variables', key, value)
    # CODEOWNERS and CONTRIBUTING require both repository checks and a code
    # owner review on the code branch. Bootstrap can precede branch creation.
    if api('branches/develop', missing=True):
        api('branches/develop/protection', 'PUT', {
            'required_status_checks': {'strict': True, 'contexts': [
                'Unit & integration tests', 'Repository & workflow lint']},
            'enforce_admins': True,
            'required_pull_request_reviews': {'dismiss_stale_reviews': True,
                'require_code_owner_reviews': True, 'required_approving_review_count': 1},
            'restrictions': None, 'allow_force_pushes': False, 'allow_deletions': False,
        })
    print('DEV/HOM prepared; develop is the only allowed deployment branch. Promotion switch unchanged.')


def verify():
    protection = api('branches/develop/protection')
    record = dict(checked_at=datetime.now(timezone.utc).isoformat(),
        default_branch=api('')['default_branch'], code_branch='develop',
        required_checks=protection['required_status_checks']['contexts'],
        required_code_owner_reviews=protection['required_pull_request_reviews']['require_code_owner_reviews'],
        required_approvals=protection['required_pull_request_reviews']['required_approving_review_count'],
        enforce_admins=protection['enforce_admins']['enabled'], environments={})
    for env in ('DEV', 'HOM'):
        policies = api(f'environments/{env}/deployment-branch-policies')['branch_policies']
        assert [(p['name'], p['type']) for p in policies] == [('develop', 'branch')]
        record['environments'][env] = {'allowed_refs': [{'name':p['name'], 'type':p['type']} for p in policies]}
    variables = {v['name']:v['value'] for v in api('actions/variables')['variables']}
    record['automatic_hom_promotion_enabled'] = variables.get('STABLE_PROMOTION_AUTHORIZED') == 'true'
    path = ROOT / 'docs/evidence/dev-hom-bootstrap/github-readback.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--verify-only']:
        verify()
    elif not sys.argv[1:]:
        main()
    else:
        raise SystemExit('usage: configure_github.py [--verify-only]')
