"""Select same-run functional evidence for an already verified OCI identity.

No network, build or archive extraction here. The pinned download action
checks ZIP integrity; this gate checks reports against the actual OCI digests.
"""
import hashlib
import json
from pathlib import Path
import re

ARCHES = ('amd64', 'arm64')


def number(value):
    if isinstance(value, bool) or not re.fullmatch(r'[1-9][0-9]*', str(value)):
        raise ValueError('run, attempt and artifact/job IDs must be positive integers')
    return int(value)


def digest(value):
    if not isinstance(value, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise ValueError('missing or invalid OCI digest')
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON field: {key}')
        result[key] = value
    return result


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'missing or non-regular evidence file: {path.name}')
    raw = path.read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('evidence exceeds size limit')
    def invalid_constant(value):
        raise ValueError(f'invalid JSON constant: {value}')

    return json.loads(raw, object_pairs_hook=unique_object,
                      parse_constant=invalid_constant), hashlib.sha256(raw).hexdigest()


def entries(document, key):
    """Consume complete REST pagination, as produced by gh --paginate --slurp."""
    pages = document if isinstance(document, list) else [document]
    if not pages:
        raise ValueError(f'missing {key} metadata')
    total = pages[0]['total_count']
    if type(total) is not int or total < 0:
        raise ValueError(f'invalid {key} count')
    result = []
    for page in pages:
        if page['total_count'] != total or not isinstance(page[key], list):
            raise ValueError(f'inconsistent {key} pagination')
        result.extend(page[key])
    if len(result) != total or len({number(item['id']) for item in result}) != total:
        raise ValueError(f'incomplete or duplicate {key} metadata')
    return result


def producers(document, framework, run_id, attempt, revision):
    name = f'Runtime {framework} (both architectures)'
    matches = {}
    for job in entries(document, 'jobs'):
        if number(job['run_id']) != run_id:
            raise ValueError('job from another workflow run')
        if job['name'] != name and not job['name'].endswith(' / ' + name):
            continue
        job_attempt = number(job['run_attempt'])
        if job_attempt > attempt or job.get('head_sha', revision) != revision:
            raise ValueError('producer attempt/revision differs from current run')
        if job_attempt in matches:
            raise ValueError('ambiguous producer jobs for one framework/attempt')
        matches[job_attempt] = job
    if not matches:
        raise ValueError('missing producer job for this framework')
    latest = matches[max(matches)]
    if latest['status'] != 'completed' or latest['conclusion'] != 'success':
        raise ValueError('latest functional producer did not succeed; no fallback')
    return matches, latest


def artifacts(document, framework, run_id, attempt, revision):
    prefix = f'runtime-{framework}-'
    matches = {}
    for item in entries(document, 'artifacts'):
        name = item['name']
        # Same matching boundary as runtime-FRAMEWORK-[0-9]* in the workflow;
        # runtime-nodejs22-dev-N must not be mistaken for runtime-nodejs22-N.
        if not name.startswith(prefix) or not re.match(r'[0-9]', name[len(prefix):]):
            continue
        source_attempt = number(name[len(prefix):])
        if source_attempt > attempt:
            raise ValueError('artifact from a future attempt')
        if number(item['workflow_run']['id']) != run_id:
            raise ValueError('artifact from another workflow run')
        if item['workflow_run'].get('head_sha', revision) != revision:
            raise ValueError('artifact revision differs from current run')
        if item['expired'] is not False:
            raise ValueError('functional artifact expired')
        if source_attempt in matches:
            raise ValueError('duplicate/conflicting artifacts for the same attempt')
        matches[source_attempt] = item
    if not matches:
        raise ValueError('missing functional contract artifact')
    return matches


def report_pair(directory, framework, source_attempt, run_id, repository, revision, compiled):
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('missing or non-regular artifact directory')
    filenames = {f'runtime-{framework}-{arch}.json' for arch in ARCHES}
    if {path.name for path in directory.iterdir()} != filenames:
        raise ValueError('artifact must contain exactly both platform reports')
    reports, hashes = {}, {}
    for arch in ARCHES:
        report, hashes[arch] = read_json(directory / f'runtime-{framework}-{arch}.json')
        if (type(report['schema_version']) is not int or report['schema_version'] != 1
                or report['framework'] != framework
                or report['platform'] != f'linux/{arch}'
                or report['contract'] != ('compiled' if compiled else 'interpreted')):
            raise ValueError('report schema/framework/platform/contract mismatch')
        if (number(report['run_id']) != run_id or number(report['run_attempt']) != source_attempt
                or report['repository'] != repository or report['revision'] != revision):
            raise ValueError('report belongs to another run/attempt/repository/revision')
        digest(report['index_digest'])
        digest(report['manifest_digest'])
        if report['status'] not in ('passed', 'failed'):
            raise ValueError('invalid functional status')
        if report['status'] == 'passed' and (not isinstance(report.get('checks'), dict)
                                            or not report['checks']):
            raise ValueError('passed report has no functional checks')
        if compiled:
            if report['dev_framework'] != framework + '-dev':
                raise ValueError('wrong build variant in compiled report')
            digest(report['dev_index_digest'])
            digest(report['dev_manifest_digest'])
        reports[arch] = report
    if len({report['index_digest'] for report in reports.values()}) != 1:
        raise ValueError('conflicting platform index digests')
    if compiled and len({report['dev_index_digest'] for report in reports.values()}) != 1:
        raise ValueError('conflicting build variant index digests')
    return reports, hashes


def select(reports, framework, expected, run_id, attempt, repository, revision,
           artifact_metadata, job_metadata, dev_expected=None):
    run_id, attempt = number(run_id), number(attempt)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('missing or invalid revision')
    digest(expected['digest'])
    jobs, latest_job = producers(job_metadata, framework, run_id, attempt, revision)
    available = artifacts(artifact_metadata, framework, run_id, attempt, revision)
    root = Path(reports)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('missing functional reports directory')
    # download-artifact v8 flattens a single match, even merge-multiple:false.
    flat = len(available) == 1 and all(path.is_file() for path in root.iterdir())
    if not flat and {path.name for path in root.iterdir()} != {item['name'] for item in available.values()}:
        raise ValueError('downloaded artifacts differ from the complete run inventory')
    compatible = {}
    for source_attempt, artifact in available.items():
        directory = root if flat else root / artifact['name']
        pair, hashes = report_pair(directory, framework, source_attempt, run_id,
                                   repository, revision, dev_expected is not None)
        candidate = pair['amd64']['index_digest']
        if candidate != expected['digest']:
            continue  # Well-formed evidence for an older, different candidate.
        if any(pair[arch]['manifest_digest'] != expected['platforms'][f'linux/{arch}']
               for arch in ARCHES):
            raise ValueError('functional manifest differs from validated OCI')
        if dev_expected is not None:
            if pair['amd64']['dev_index_digest'] != dev_expected['digest']:
                continue
            if any(pair[arch]['dev_manifest_digest'] != dev_expected['platforms'][f'linux/{arch}']
                   for arch in ARCHES):
                raise ValueError('functional build manifest differs from validated OCI')
        compatible[source_attempt] = (artifact, pair, hashes)
    if not compatible:
        raise ValueError('no functional evidence matches the current validated index/pair')
    selected_attempt = max(compatible)
    artifact, pair, hashes = compatible[selected_attempt]
    if any(report['status'] != 'passed' for report in pair.values()):
        raise ValueError('latest matching contract failed; no fallback to an older PASS')
    producer = jobs.get(selected_attempt)
    if not producer or producer['status'] != 'completed' or producer['conclusion'] != 'success':
        raise ValueError('selected artifact has no successful producer in its attempt')
    return {'framework': framework, 'passed': True, 'repository': repository,
            'run_id': str(run_id), 'run_attempt': attempt, 'revision': revision,
            'selected_artifact_id': artifact['id'], 'selected_artifact': artifact['name'],
            'selected_attempt': selected_attempt, 'index_digest': expected['digest'],
            'platforms': expected['platforms'], 'dev_index_digest': dev_expected['digest'] if dev_expected else None,
            'dev_platforms': dev_expected['platforms'] if dev_expected else None,
            'report_sha256': hashes, 'latest_producer_job_id': latest_job['id'],
            'latest_producer_attempt': latest_job['run_attempt'],
            'reused': selected_attempt < attempt}
