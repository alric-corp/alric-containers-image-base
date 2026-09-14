"""Evidence-only retry laboratory. No build, network, registry or signing calls.

The workflow runs runtime_images --gate first. This module verifies the lab
scenario and compares GitHub metadata; it never manufactures functional PASS.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from scripts.pipeline.runtime.contract_evidence import digest, entries, number, read_json

REPOSITORY = 'alric-corp/alric-containers-image-base'
WORKFLOW = '.github/workflows/partial-retry-lab.yml'
CONFIRMATION = 'P1-02-evidence-only'
CONSUMER = 'Lab retry gate'
BARRIER = 'Controlled attempt-1 barrier'
RECORD = 'Record lab execution and compare inherited evidence'
BASELINE_UPLOAD = 'Preserve attempt-1 baseline'
PRODUCER_PREFIXES = ('Lab build / ', 'Lab contract / ')
REQUIRED_LEAVES = {'Compile certs with melange', 'Validate go1-26',
                   'Validate go1-26-dev', 'Runtime go1-26 (both architectures)'}
BOUND_FIELDS = ('framework', 'repository', 'run_id', 'revision',
                'selected_artifact_id', 'selected_artifact', 'selected_attempt',
                'index_digest', 'platforms', 'dev_index_digest', 'dev_platforms',
                'report_sha256')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def context(env, event):
    """Only explicit dispatch of this workflow/revision in the sandbox."""
    revision = env.get('GITHUB_SHA', '')
    expected_ref = f'{REPOSITORY}/{WORKFLOW}@refs/heads/main'
    require(env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY') == REPOSITORY
            and env.get('GITHUB_REF') == 'refs/heads/main'
            and env.get('GITHUB_WORKFLOW_REF') == expected_ref,
            'laboratory requires its own sandbox main workflow_dispatch')
    require(re.fullmatch(r'[0-9a-f]{40}', revision)
            and env.get('GITHUB_WORKFLOW_SHA') == revision, 'invalid workflow revision')
    require(event.get('inputs') == {'confirmation': CONFIRMATION, 'reviewed-sha': revision},
            'explicit confirmation and exact reviewed-sha are required; no other inputs')
    attempt = number(env.get('GITHUB_RUN_ATTEMPT'))
    require(attempt in (1, 2), 'laboratory allows only attempts 1 and 2')
    return {'repository': REPOSITORY, 'run_id': str(number(env.get('GITHUB_RUN_ID'))),
            'run_attempt': attempt, 'head_sha': revision, 'workflow_ref': expected_ref,
            'framework': 'go1-26'}


def moment(value):
    require(isinstance(value, str), 'missing timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(result.tzinfo is not None, 'timestamp must have timezone')
    return result


def artifact_inventory(document, ctx, now):
    """Only three immutable identities matter; names alone never prove reuse."""
    names = {'validated-oci-go1-26', 'validated-oci-go1-26-dev', 'runtime-go1-26-1'}
    result = {}
    all_items = entries(document, 'artifacts')
    for item in all_items:
        require(str(number(item['workflow_run']['id'])) == ctx['run_id']
                and item['workflow_run']['head_sha'] == ctx['head_sha'],
                'artifact run/revision mismatch')
        name = item['name']
        if name not in names:
            continue
        require(name not in result, 'ambiguous laboratory artifact')
        require(item['expired'] is False and moment(item['expires_at']) > now,
                'laboratory artifact expired')
        digest(item['digest'])
        require(type(item['size_in_bytes']) is int and item['size_in_bytes'] > 0,
                'invalid artifact size')
        moment(item['created_at'])
        result[name] = {key: item[key] for key in
                        ('id', 'name', 'digest', 'size_in_bytes', 'created_at', 'expires_at')}
    require(set(result) == names, 'missing runtime/dev OCI or functional artifact')
    return result


def execution(job):
    require(job['status'] == 'completed' and job['conclusion'] == 'success',
            'producer did not complete successfully')
    require(moment(job['completed_at']) >= moment(job['started_at']), 'invalid job timing')
    require(isinstance(job['steps'], list) and job['steps'], 'missing producer steps')
    fields = ('number', 'name', 'status', 'conclusion', 'started_at', 'completed_at')
    return {'started_at': job['started_at'], 'completed_at': job['completed_at'],
            'steps': [{key: step.get(key) for key in fields} for step in job['steps']]}


def job_inventory(document, ctx):
    jobs = entries(document, 'jobs')
    by_name = {}
    consumer = None
    for job in jobs:
        require(str(number(job['run_id'])) == ctx['run_id']
                and job['head_sha'] == ctx['head_sha'], 'job run/revision mismatch')
        attempt = number(job['run_attempt'])
        require(attempt <= ctx['run_attempt'], 'future job attempt')
        name = job['name']
        if name == CONSUMER:
            if attempt == ctx['run_attempt']:
                require(consumer is None, 'ambiguous current consumer')
                consumer = job
            continue
        require(name == 'Lab request' or name.startswith(PRODUCER_PREFIXES),
                'unexpected job in laboratory run')
        versions = by_name.setdefault(name, {})
        require(attempt not in versions, 'ambiguous producer attempt')
        versions[attempt] = job
    require(consumer is not None, 'current consumer missing from GitHub metadata')
    require(consumer['status'] == 'in_progress' and consumer['conclusion'] is None,
            'consumer is not the currently executing job')
    consumer_start = moment(consumer['started_at'])
    leaves = {name.split(' / ')[-1] for name in by_name}
    require(REQUIRED_LEAVES <= leaves and 'Lab request' in by_name,
            'required build/contract/request jobs missing')
    latest = {}
    for name, versions in by_name.items():
        job = versions[max(versions)]
        latest[name] = {'id': job['id'], 'run_attempt': job['run_attempt'],
                        'execution': execution(job)}
        require(moment(job['completed_at']) <= consumer_start,
                'producer did not finish before consumer started')
    return jobs, consumer, latest


def valid_gate(gate, ctx):
    require(gate['passed'] is True and gate['framework'] == 'go1-26'
            and gate['repository'] == ctx['repository']
            and str(number(gate['run_id'])) == ctx['run_id']
            and gate['revision'] == ctx['head_sha']
            and type(gate['run_attempt']) is int
            and gate['run_attempt'] == ctx['run_attempt'], 'real gate did not approve this context')
    require(type(gate['selected_attempt']) is int and gate['selected_attempt'] == 1
            and gate['selected_artifact'] == 'runtime-go1-26-1'
            and gate['reused'] is (ctx['run_attempt'] == 2), 'unexpected selected attempt/reuse')
    for key in ('index_digest', 'dev_index_digest'):
        digest(gate[key])
    for key in ('platforms', 'dev_platforms'):
        require(set(gate[key]) == {'linux/amd64', 'linux/arm64'}, 'missing platform identity')
        for value in gate[key].values():
            digest(value)
    require(set(gate['report_sha256']) == {'amd64', 'arm64'}, 'missing report hashes')
    for value in gate['report_sha256'].values():
        require(re.fullmatch(r'[0-9a-f]{64}', value), 'invalid report hash')


def assess(ctx, gate, artifacts, jobs, baseline=None, now=None):
    """Observe retained objects and inherited executions, without asserting job success."""
    now = now or datetime.now(timezone.utc)
    valid_gate(gate, ctx)
    inventory = artifact_inventory(artifacts, ctx, now)
    all_jobs, consumer, producers = job_inventory(jobs, ctx)
    require(inventory['runtime-go1-26-1']['id'] == gate['selected_artifact_id'],
            'gate selected a different artifact ID')
    runtime_name = next(name for name in producers
                        if name.endswith(' / Runtime go1-26 (both architectures)'))
    require(producers[runtime_name]['id'] == gate['latest_producer_job_id']
            and producers[runtime_name]['run_attempt'] == gate['latest_producer_attempt'],
            'gate producer differs from GitHub metadata')
    comparison = []
    if ctx['run_attempt'] == 2:
        require(baseline is not None and baseline['schema_version'] == 1,
                'attempt 2 requires the preserved baseline')
        previous = dict(ctx, run_attempt=1)
        require(baseline['context'] == previous, 'baseline context mismatch')
        valid_gate(baseline['gate'], previous)
        require(all(baseline['gate'][key] == gate[key] for key in BOUND_FIELDS),
                'gate identity/report hashes changed since attempt 1')
        require(baseline['artifacts'] == inventory, 'artifact overwritten or metadata changed')
        require(set(baseline['producers']) == set(producers), 'producer inventory changed')
        for name, current in producers.items():
            original = baseline['producers'][name]
            require(original['run_attempt'] == 1
                    and original['execution'] == current['execution'],
                    'producer executed again or execution evidence differs')
            comparison.append({'name': name, 'original_job_id': original['id'],
                               'observed_job_id': current['id'],
                               'observed_run_attempt': current['run_attempt'],
                               'execution_metadata_equal': True})
        failed = [j for j in all_jobs if j['id'] == baseline['consumer_job_id']
                  and j['name'] == CONSUMER and number(j['run_attempt']) == 1]
        require(len(failed) == 1 and failed[0]['status'] == 'completed'
                and failed[0]['conclusion'] == 'failure', 'missing failed attempt-1 consumer')
        steps = failed[0]['steps']
        require([s['name'] for s in steps if s['conclusion'] == 'failure'] == [BARRIER],
                'attempt 1 did not fail solely at the controlled barrier')
        by_name = {s['name']: s for s in steps}
        require(len(by_name) == len(steps)
                and by_name[RECORD]['conclusion'] == 'success'
                and by_name[BASELINE_UPLOAD]['conclusion'] == 'success'
                and by_name[RECORD]['number'] < by_name[BASELINE_UPLOAD]['number']
                < by_name[BARRIER]['number'], 'baseline was not preserved before barrier')
        require(consumer['id'] != failed[0]['id']
                and moment(consumer['started_at']) > moment(failed[0]['completed_at']),
                'consumer rerun not demonstrated')
        baseline_name = f"runtime-lab-p1-02-baseline-{ctx['run_id']}"
        retained = [a for a in entries(artifacts, 'artifacts') if a['name'] == baseline_name]
        require(len(retained) == 1 and retained[0]['expired'] is False
                and moment(retained[0]['expires_at']) > now
                and moment(retained[0]['created_at']) < moment(failed[0]['completed_at']),
                'baseline artifact missing, ambiguous, expired or created after failure')
    else:
        require(baseline is None, 'unexpected baseline on attempt 1')
    return {'schema_version': 1, 'context': ctx, 'gate': gate, 'artifacts': inventory,
            'producers': producers, 'consumer_job_id': consumer['id'],
            'observed_at': now.isoformat(), 'producer_comparison': comparison,
            'status': 'BASELINE_VALIDATED' if ctx['run_attempt'] == 1 else 'REUSE_OBSERVED',
            'publication': 'NOT_IMPLEMENTED', 'hosted_acceptance': 'PENDING'}


def barrier(ctx, manifest):
    require(manifest['context'] == ctx and manifest['status'] ==
            ('BASELINE_VALIDATED' if ctx['run_attempt'] == 1 else 'REUSE_OBSERVED'),
            'barrier requires a validated laboratory manifest')
    valid_gate(manifest['gate'], ctx)
    code = 42 if ctx['run_attempt'] == 1 else 0
    return code, {'context': ctx, 'exit_code': code,
                  'status': 'EXPECTED_LAB_FAILURE' if code else 'LAB_BARRIER_PASSED',
                  'publication': 'NOT_IMPLEMENTED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('guard', 'record', 'barrier'))
    parser.add_argument('--gate')
    parser.add_argument('--artifacts')
    parser.add_argument('--jobs')
    parser.add_argument('--baseline')
    parser.add_argument('--manifest')
    parser.add_argument('--output')
    args = parser.parse_args()
    code = 0
    try:
        event, _ = read_json(os.environ['GITHUB_EVENT_PATH'])
        ctx = context(os.environ, event)
        if args.mode == 'guard':
            result = {'context': ctx, 'status': 'REQUEST_VALIDATED'}
        elif args.mode == 'record':
            result = assess(ctx, read_json(args.gate)[0], read_json(args.artifacts)[0],
                            read_json(args.jobs)[0],
                            read_json(args.baseline)[0] if args.baseline else None)
        else:
            code, result = barrier(ctx, read_json(args.manifest)[0])
    except (KeyError, ValueError, TypeError, OSError, AttributeError, StopIteration) as error:
        code, result = 1, {'status': 'INVALID_SCENARIO', 'error': str(error)}
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
