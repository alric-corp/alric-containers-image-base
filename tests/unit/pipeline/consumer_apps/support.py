"""Offline inputs for consumer execution tests; no cloud/image interaction."""
import hashlib

from scripts.pipeline.consumer_apps.model import ARCHITECTURES, CATALOG, scenario


def digest(value):
    return 'sha256:' + hashlib.sha256(value.encode()).hexdigest()


def inventory():
    candidates = {}
    for framework in CATALOG:
        identity = digest(framework)
        candidates[framework] = {
            'framework': framework, 'repository': f'image-base-{framework}',
            'immutable_tag': '210926-0422-r12345-a1', 'digest': identity,
            'image_ref': f'123456789012.dkr.ecr.us-east-1.amazonaws.com/image-base-{framework}@{identity}',
            'imagePushedAt': '2026-09-21T07:22:00Z',
            'platforms': {arch: digest(framework + arch) for arch in ARCHITECTURES},
        }
    return {'schema_version': 1, 'source_run_id': 12345, 'source_run_attempt': 1,
            'source_sha': 'a' * 40, 'candidates': candidates}


def good_result(framework='go1-26', architecture='amd64'):
    source = inventory()
    expected = scenario(framework)
    result = {key: source[key] for key in ('source_run_id', 'source_run_attempt', 'source_sha')}
    security = {'uid': 10000, 'gid': 10000, 'read_only_root': True, 'writable_tmp': True,
                'writable_app_work': True, 'no_new_privileges': True, 'cap_eff': '0000000000000000'}
    result.update(schema_version=1, framework=framework, platform='linux/' + architecture,
                  execution_mode='native' if architecture == 'amd64' else 'emulated',
                  build_seconds=2.0, startup_seconds=0.5, container_started=True, build_passed=True,
                  runtime_base_verified=True, container_hardening_verified=True,
                  graceful_shutdown=True, shutdown_exit_code=0, shutdown_marker_observed=True,
                  oom_killed=False, status='PASS', **security)
    result['health'] = {'http_status': 200, 'body': {'status': 'ok'}}
    result['ready'] = {'http_status': 200, 'body': {'status': 'ok'}}
    result['info'] = {'http_status': 200, 'body': {'status': 'ok', 'runtime': expected['family'],
                      'runtime_version': expected['expected_version'] + '.1',
                      'architecture': architecture, 'security': security.copy()}}
    for role, name in (('runtime', framework), ('dev', expected['dev_framework'])):
        candidate = source['candidates'].get(name)
        result[role + '_image_ref'] = candidate['image_ref'] if candidate else None
        result[role + '_digest'] = candidate['digest'] if candidate else None
        result[role + '_manifest_digest'] = candidate['platforms'][architecture] if candidate else None
    return result
