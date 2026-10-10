"""Validated, versioned pipeline settings; GitHub variables are not inputs."""
import argparse
import json
import math
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'policies/pipeline/config.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'duplicate configuration key: {key}')
        result[key] = value
    return result


def keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected),
            f'{label}: missing or unknown configuration keys')


def match(value, pattern, label):
    require(isinstance(value, str) and re.fullmatch(pattern, value) is not None,
            f'{label}: invalid value')


def configuration(path=None):
    cfg = json.loads((CONFIG if path is None else Path(path)).read_text(),
                     object_pairs_hook=object_pairs)
    keys(cfg, ('schema_version', 'repository', 'branch', 'subject_prefix', 'DEV', 'HOM', 'infra', 'factory'), 'pipeline')
    require(type(cfg['schema_version']) is int and cfg['schema_version'] == 1, 'unsupported pipeline schema')
    match(cfg['repository'], r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', 'repository')
    # Entrypoint branch guards and OIDC Environments are reviewed boundaries.
    require(cfg['branch'] == 'develop', 'pipeline code branch must be develop')
    owner, repo = cfg['repository'].split('/')
    match(cfg['subject_prefix'], rf'repo:{re.escape(owner)}@[1-9][0-9]*/{re.escape(repo)}@[1-9][0-9]*',
          'immutable repository subject')
    for env in ('DEV', 'HOM'):
        item = cfg[env]
        keys(item, ('account_id', 'region', 'role_name', 'release_bucket'), env)
        match(item['account_id'], r'[0-9]{12}', f'{env}.account_id')
        match(item['region'], r'[a-z]{2}-[a-z]+-[0-9]+', f'{env}.region')
        match(item['role_name'], r'[A-Za-z0-9+=,.@_-]{1,64}', f'{env}.role_name')
        match(item['release_bucket'], r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', f'{env}.release_bucket')
    require(cfg['DEV']['account_id'] != cfg['HOM']['account_id'], 'DEV and HOM accounts must differ')
    require(cfg['DEV']['release_bucket'] != cfg['HOM']['release_bucket'], 'release buckets must differ')
    keys(cfg['factory'], ('operational_role_name',), 'factory')
    match(cfg['factory']['operational_role_name'], r'[A-Za-z0-9+=,.@_-]{1,64}',
          'factory.operational_role_name')
    infra = cfg['infra']
    keys(infra, ('plan_enabled', 'plan_role_name', 'apply_role_name', 'backend'), 'infra')
    require(type(infra['plan_enabled']) is bool, 'infra.plan_enabled must be boolean')
    require(infra['plan_enabled'] is False,
            'privileged PR planning requires a separately reviewed authorization design')
    for field in ('plan_role_name', 'apply_role_name'):
        match(infra[field], r'[A-Za-z0-9+=,.@_-]{1,64}', 'infra.' + field)
    require(len({infra['plan_role_name'], infra['apply_role_name'], cfg['DEV']['role_name']}) == 3,
            'legacy Terraform role names must be distinct')
    require(cfg['factory']['operational_role_name'] not in
            {infra['plan_role_name'], infra['apply_role_name'], cfg['DEV']['role_name'], cfg['HOM']['role_name']},
            'external operational role must remain separate from legacy Terraform identities')
    keys(infra['backend'], ('bucket', 'region', 'key'), 'infra.backend')
    match(infra['backend']['bucket'], r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', 'infra.backend.bucket')
    match(infra['backend']['region'], r'[a-z]{2}-[a-z]+-[0-9]+', 'infra.backend.region')
    match(infra['backend']['key'], r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*', 'infra.backend.key')
    require('..' not in infra['backend']['key'].split('/'), 'backend key cannot traverse directories')
    return cfg


def promotion_policy(environment, path=None):
    require(environment in ('DEV', 'HOM'), 'unknown promotion environment')
    path = Path(path) if path is not None else CONFIG.parent / f'promote-{environment.lower()}.json'
    policy = json.loads(path.read_text(), object_pairs_hook=object_pairs)
    keys(policy, ('schema_version', 'enabled', 'frameworks', 'soak_hours'), path.name)
    require(type(policy['schema_version']) is int and policy['schema_version'] == 1,
            'unsupported promotion policy schema')
    require(type(policy['enabled']) is bool, 'promotion enabled must be boolean')
    hours = policy['soak_hours']
    minimum = 0 if environment == 'DEV' else 6
    require(type(hours) in (int, float) and math.isfinite(hours) and minimum <= hours <= 8760,
            f'{environment} soak_hours must be finite and between {minimum} and 8760')
    frameworks = policy['frameworks']
    catalog = {p.stem for p in (ROOT / 'frameworks').glob('*.yaml')}
    require(isinstance(frameworks, list) and frameworks and all(isinstance(f, str) for f in frameworks)
            and len(frameworks) == len(set(frameworks)) and set(frameworks) <= catalog,
            f'{environment} frameworks must be a nonempty, distinct subset of the catalog')
    for dev in sorted(f for f in catalog if f.endswith('-dev')):
        pair = {dev, dev.removesuffix('-dev')}
        require(not pair.intersection(frameworks) or pair.issubset(frameworks),
                f'{environment} policy requires complete runtime/dev pair: {sorted(pair)}')
    return policy


def settings(cfg, scope):
    require(scope in ('DEV', 'HOM', 'INFRA_PLAN', 'INFRA_APPLY'), 'unknown pipeline scope')
    item = cfg['DEV' if scope.startswith('INFRA_') else scope]
    role = item['role_name']
    require(cfg['infra']['plan_enabled'] is False,
            'privileged PR planning requires a separately reviewed authorization design')
    if scope in ('DEV', 'INFRA_APPLY'):
        role = cfg['factory']['operational_role_name']
    elif scope == 'INFRA_PLAN':
        # Disabled PR checks retain the legacy name, never the central role.
        role = cfg['infra']['plan_role_name']
    values = {
        'AWS_ACCOUNT_ID': item['account_id'], 'AWS_REGION': item['region'],
        'AWS_ROLE_ARN': f'arn:aws:iam::{item["account_id"]}:role/{role}',
        'RELEASE_BUCKET': item['release_bucket'],
        'INFRA_PLAN_ENABLED': str(cfg['infra']['plan_enabled']).lower(),
    }
    if scope in ('DEV', 'HOM'):
        policy = promotion_policy(scope)
        values.update(PROMOTION_AUTHORIZED=str(policy['enabled']).lower(),
                      MINIMUM_SOAK_HOURS=str(policy['soak_hours']),
                      PROMOTION_FRAMEWORKS=json.dumps(policy['frameworks'], separators=(',', ':')))
    if scope.startswith('INFRA_'):
        backend = cfg['infra']['backend']
        values.update(TF_STATE_BUCKET=backend['bucket'], TF_STATE_KEY=backend['key'],
                      TF_BACKEND_REGION=backend['region'])
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('DEV', 'HOM', 'INFRA_PLAN', 'INFRA_APPLY'), required=True)
    parser.add_argument('--require-promotion', action='store_true')
    args = parser.parse_args(argv)
    cfg = configuration()
    if os.environ.get('GITHUB_REPOSITORY'):
        require(os.environ['GITHUB_REPOSITORY'] == cfg['repository'], 'pipeline repository mismatch')
    if os.environ.get('GITHUB_EVENT_NAME', '').startswith('pull_request'):
        require(args.scope == 'INFRA_PLAN', 'privileged role resolution is forbidden for pull requests')
    if args.require_promotion:
        require(args.scope in ('DEV', 'HOM') and promotion_policy(args.scope)['enabled'],
                f'{args.scope} promotion is disabled in promotion policy')
    values = settings(cfg, args.scope)
    # Validate everything before writing either file. Only validated single-line
    # values enter the Actions command files, never arbitrary JSON keys or env.
    payload = ''.join(f'{key}={value}\n' for key, value in values.items())
    for key in ('GITHUB_ENV', 'GITHUB_OUTPUT'):
        if os.environ.get(key):
            with Path(os.environ[key]).open('a') as output:
                output.write(payload)
    print(json.dumps(values, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f'Invalid pipeline configuration: {error}') from error
