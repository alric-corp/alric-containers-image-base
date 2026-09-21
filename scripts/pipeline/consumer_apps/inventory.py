"""Resolve one completed catalog run to immutable, remotely read-back candidates.

Only attempt 1 is accepted: a run-ID-only input must not silently drift to a
rerun. GitHub ZIP digests, publication producers, exact pair evidence and ECR
are checked before the single inventory is emitted. No AWS writes are used.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

from scripts.pipeline.artifacts.oci_artifact import INDEX
from scripts.pipeline.consumer_apps.model import CATALOG
from scripts.pipeline.release.verify_publication import verify_publication
from scripts.pipeline.runtime import contract_evidence, runtime_images

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
REQUIRED_FILES = (
    'image.oci/validated-index.json', 'image.oci/build-inputs.json',
    'published.digest', 'published-index.json', 'publication-evidence.json',
    'runtime-gate-result.json',
)
REQUIRED_STEPS = (
    'Download validated OCI artifact',
    'Authorize publication with the current functional contract',
    'Require successful default trust integration',
    'Verify artifact integrity and platforms',
    'Publish validated OCI artifact (multi-arch)',
    'Sign published image (keyless)',
    'Attest original SPDX SBOMs for index and both architectures',
    'Attest build provenance (SLSA)',
    'Preserve publication evidence',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_document(raw):
    def invalid_constant(value):
        raise ValueError(f'invalid JSON constant: {value}')
    return json.loads(raw, object_pairs_hook=contract_evidence.unique_object,
                      parse_constant=invalid_constant)


def registry_identity(registry):
    match = re.fullmatch(r'([0-9]{12})\.dkr\.ecr\.([a-z]{2}(?:-gov)?-[a-z]+-[0-9])'
                         r'\.amazonaws\.com(?:\.cn)?', registry)
    require(match is not None, 'registry must be a private ECR registry hostname')
    return match.group(1), match.group(2)


def validate_source(run, source_run_id, repository):
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository),
            'invalid GitHub repository')
    require(contract_evidence.number(run['id']) == contract_evidence.number(source_run_id),
            'source workflow run ID mismatch')
    require(run['repository']['full_name'] == repository
            and run['head_repository']['full_name'] == repository
            and run['repository']['id'] == run['head_repository']['id'],
            'source workflow repository mismatch')
    require(run['path'] == '.github/workflows/catalog-certification.yml'
            and run['head_branch'] == 'main' and run['event'] == 'workflow_dispatch',
            'source must be a main catalog-certification workflow_dispatch')
    require(run['status'] == 'completed' and run['conclusion'] == 'success',
            'source catalog run has not completed successfully')
    require(contract_evidence.number(run['run_attempt']) == 1,
            'source reruns are ambiguous: only run attempt 1 is supported')
    require(re.fullmatch(r'[0-9a-f]{40}', run['head_sha']), 'invalid source revision')


def source_metadata(run, artifact_pages, job_pages):
    """Require complete inventories and successful publication/functional jobs."""
    artifacts = contract_evidence.entries(artifact_pages, 'artifacts')
    jobs = contract_evidence.entries(job_pages, 'jobs')
    run_id, revision = run['id'], run['head_sha']
    for job in jobs:
        require(job['run_id'] == run_id and job['run_attempt'] == 1
                and job['head_sha'] == revision, 'producer run/attempt/revision mismatch')
    selected = {}
    for artifact in artifacts:
        name = artifact['name']
        if not name.startswith('publication-'):
            continue
        framework = next((f for f in CATALOG if name == f'publication-{f}-1'), None)
        require(framework is not None, 'unexpected publication framework or attempt')
        require(framework not in selected, 'ambiguous publication artifact')
        origin = artifact['workflow_run']
        require(origin['id'] == run_id and origin['head_sha'] == revision
                and origin['head_branch'] == 'main'
                and origin['repository_id'] == run['repository']['id']
                and origin['head_repository_id'] == run['repository']['id'],
                'publication artifact run/revision/repository mismatch')
        require(artifact['expired'] is False, 'publication artifact has expired')
        contract_evidence.digest(artifact['digest'])
        require(type(artifact['size_in_bytes']) is int
                and 0 < artifact['size_in_bytes'] <= MAX_ARCHIVE, 'invalid archive size')
        selected[framework] = artifact
    require(set(selected) == set(CATALOG), 'missing framework publication evidence')
    producers = {}
    for framework in CATALOG:
        name = f'Build & push {framework}'
        matches = [job for job in jobs
                   if job['name'] == name or job['name'].endswith(' / ' + name)]
        require(len(matches) == 1, 'missing or ambiguous publication producer')
        job = matches[0]
        require(job['status'] == 'completed' and job['conclusion'] == 'success',
                f'{framework}: publication producer did not succeed')
        for step_name in REQUIRED_STEPS:
            steps = [step for step in job['steps'] if step['name'] == step_name]
            require(len(steps) == 1 and steps[0]['status'] == 'completed'
                    and steps[0]['conclusion'] == 'success',
                    f'{framework}: publication prerequisite did not succeed: {step_name}')
        producers[framework] = job
    publication_jobs = [job for job in jobs
                        if job['name'].split(' / ')[-1].startswith('Build & push ')]
    require(len(publication_jobs) == len(CATALOG),
            'unexpected publication producer outside the exact catalog')
    return selected, producers


def archive_files(raw, artifact):
    """Read only selected files after integrity and bounded ZIP validation.

    Nothing is extracted to the filesystem; unsafe/duplicate entries still fail
    so artifact contents have one unambiguous interpretation for every reader.
    """
    require(len(raw) == artifact['size_in_bytes'] and len(raw) <= MAX_ARCHIVE,
            'publication ZIP size differs from GitHub metadata')
    require('sha256:' + hashlib.sha256(raw).hexdigest() == artifact['digest'],
            'publication ZIP digest mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        require(len(members) <= 500 and sum(x.file_size for x in members) <= MAX_EXPANDED,
                'publication ZIP exceeds extraction limits')
        names = set()
        for entry in members:
            name = entry.filename
            path = PurePosixPath(name)
            mode = stat.S_IFMT(entry.external_attr >> 16)
            require(name and '\\' not in name and '\x00' not in name
                    and not path.is_absolute() and '..' not in path.parts
                    and path.as_posix() == name.rstrip('/')
                    and mode in (0, stat.S_IFREG, stat.S_IFDIR), 'unsafe publication ZIP entry')
            require(name not in names, 'duplicate publication ZIP entry')
            require(not entry.flag_bits & 1, 'encrypted publication ZIP entry')
            names.add(name)
        require(set(REQUIRED_FILES).issubset(names), 'publication ZIP missing required evidence')
        return {name: archive.read(name) for name in REQUIRED_FILES}


def publication(files, framework, run, repository, registry):
    expected = json_document(files['image.oci/validated-index.json'])
    recorded = json_document(files['publication-evidence.json'])
    contract_evidence.digest(expected['digest'])
    require(set(expected['platforms']) == {'linux/amd64', 'linux/arm64'},
            'publication must contain exactly both platforms')
    for digest in expected['platforms'].values():
        contract_evidence.digest(digest)
    image_ref = f'{registry}/image-base-{framework}@{expected["digest"]}'
    verified = verify_publication(expected, files['published.digest'].decode().strip(),
                                  files['published-index.json'], image_ref)
    require(recorded == verified, 'publication read-back evidence mismatch')
    build = json_document(files['image.oci/build-inputs.json'])
    require(build['revision'] == run['head_sha']
            and build['annotations']['revision'] == run['head_sha']
            and build['annotations']['source'] == f'https://github.com/{repository}',
            'publication build revision/repository mismatch')
    gate = json_document(files['runtime-gate-result.json'])
    plan = runtime_images.publication_contract(framework, list(CATALOG))
    require(all(gate.get(key) == value for key, value in plan.items()),
            'publication contract resolution mismatch')
    require(gate['passed'] is True and gate['required'] is True
            and contract_evidence.number(gate['run_id']) == run['id']
            and contract_evidence.number(gate['run_attempt']) == 1
            and contract_evidence.number(gate['selected_attempt']) == 1
            and gate['revision'] == run['head_sha'] and gate['repository'] == repository,
            'publication functional gate run/attempt/revision/status mismatch')
    return expected, gate


def validate_gate_bindings(run, candidates, gates, artifact_pages, job_pages):
    """Both compiled members must prove the same exact runtime/dev pair."""
    for framework, gate in gates.items():
        runtime = candidates[gate['runtime_framework']]
        require(gate['index_digest'] == runtime['digest']
                and gate['platforms'] == runtime['platforms'],
                'functional runtime digest/platform mismatch')
        dev = gate['dev_framework']
        if dev:
            require(gate['dev_index_digest'] == candidates[dev]['digest']
                    and gate['dev_platforms'] == candidates[dev]['platforms'],
                    'functional dev digest/platform mismatch')
        else:
            require(gate['dev_index_digest'] is None and gate['dev_platforms'] is None,
                    'unexpected functional dev evidence')
        contract = gate['contract_framework']
        available = contract_evidence.artifacts(artifact_pages, contract, run['id'], 1,
                                                 run['head_sha'])
        jobs, latest = contract_evidence.producers(job_pages, contract, run['id'], 1,
                                                  run['head_sha'])
        require(set(available) == {1} and set(jobs) == {1}
                and gate['selected_artifact_id'] == available[1]['id']
                and gate['selected_artifact'] == available[1]['name']
                and gate['latest_producer_job_id'] == latest['id']
                and gate['latest_producer_attempt'] == 1 and gate['reused'] is False,
                f'{framework}: functional producer/artifact binding mismatch')


def candidate_from_ecr(document, expected, framework, run_id, registry):
    require(not document.get('NextToken') and not document.get('nextToken'),
            'ECR inventory pagination is incomplete')
    account, _ = registry_identity(registry)
    repository = f'image-base-{framework}'
    matches = []
    for detail in document['imageDetails']:
        require(detail['repositoryName'] == repository and detail['registryId'] == account,
                'ECR repository/account mismatch')
        for tag in detail.get('imageTags', []):
            if re.fullmatch(r'[0-9]{6}-[0-9]{4}-r' + str(run_id) + r'-a1', tag):
                matches.append((tag, detail))
    require(len(matches) == 1, f'{framework}: missing or ambiguous immutable source-run tag')
    tag, detail = matches[0]
    require(detail['imageDigest'] == expected['digest'], 'ECR digest differs from publication')
    require(detail['imageManifestMediaType'] == INDEX, 'ECR candidate is not an OCI index')
    # ECR is authoritative for publication time; a tag's clock is never used.
    pushed = datetime.fromisoformat(detail['imagePushedAt'].replace('Z', '+00:00'))
    require(pushed.tzinfo is not None, 'ECR imagePushedAt must include its timezone')
    return {'framework': framework, 'repository': repository, 'immutable_tag': tag,
            'digest': expected['digest'],
            'image_ref': f'{registry}/{repository}@{expected["digest"]}',
            'imagePushedAt': pushed.astimezone(timezone.utc).isoformat(),
            'platforms': {arch: expected['platforms'][f'linux/{arch}']
                          for arch in ('amd64', 'arm64')}}


def build_inventory(source_run_id, repository, registry, run, artifact_pages, job_pages,
                    archives, ecr_documents, remote_indexes):
    """Pure boundary used by offline tests; all remote responses are explicit."""
    validate_source(run, source_run_id, repository)
    registry_identity(registry)
    metadata, producers = source_metadata(run, artifact_pages, job_pages)
    require(set(archives) == set(ecr_documents) == set(remote_indexes) == set(CATALOG),
            'source evidence must cover exactly the complete catalog')
    expected, gates = {}, {}
    for framework in CATALOG:
        files = archive_files(archives[framework], metadata[framework])
        expected[framework], gates[framework] = publication(files, framework, run,
                                                           repository, registry)
    validate_gate_bindings(run, expected, gates, artifact_pages, job_pages)
    candidates = {}
    for framework in CATALOG:
        candidate = candidate_from_ecr(ecr_documents[framework], expected[framework],
                                      framework, run['id'], registry)
        verify_publication(expected[framework], candidate['digest'], remote_indexes[framework],
                           candidate['image_ref'])
        candidate['source_publication_artifact_id'] = metadata[framework]['id']
        candidate['source_publication_archive_digest'] = metadata[framework]['digest']
        candidate['source_publication_job_id'] = producers[framework]['id']
        candidate['functional_contract'] = gates[framework]['contract_framework']
        candidate['functional_contract_status'] = 'passed'
        candidates[framework] = candidate
    return {'schema_version': 1, 'source_run_id': run['id'], 'source_run_attempt': 1,
            'source_sha': run['head_sha'], 'source_repository': repository,
            'source_workflow': run['path'], 'registry': registry, 'candidates': candidates}


def command(*args):
    result = subprocess.run(args, capture_output=True, timeout=180, check=False)
    if result.returncode:
        # Tokens are never command arguments and raw command stderr is not persisted.
        raise ValueError(f'{args[0]} read-only lookup failed (exit {result.returncode})')
    return result.stdout


def gh_json(endpoint, paginate=False):
    flags = ('--paginate', '--slurp') if paginate else ()
    return json_document(command('gh', 'api', *flags, endpoint))


def resolve(source_run_id, repository, registry):
    source_run_id = contract_evidence.number(source_run_id)
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository),
            'invalid GitHub repository')
    account, region = registry_identity(registry)
    endpoint = f'repos/{repository}/actions/runs/{source_run_id}'
    run = gh_json(endpoint)
    validate_source(run, source_run_id, repository)
    artifacts = gh_json(endpoint + '/artifacts?per_page=100', paginate=True)
    jobs = gh_json(endpoint + '/jobs?filter=all&per_page=100', paginate=True)
    metadata, _ = source_metadata(run, artifacts, jobs)
    archives, ecr, remote = {}, {}, {}
    for framework in CATALOG:
        artifact = metadata[framework]
        archives[framework] = command('gh', 'api',
                                     f'repos/{repository}/actions/artifacts/{artifact["id"]}/zip')
        expected, _ = publication(archive_files(archives[framework], artifact), framework,
                                   run, repository, registry)
        ecr[framework] = json_document(command(
            'aws', 'ecr', 'describe-images', '--registry-id', account, '--region', region,
            '--repository-name', f'image-base-{framework}', '--output', 'json'))
        candidate = candidate_from_ecr(ecr[framework], expected, framework, run['id'], registry)
        remote[framework] = command('docker', 'buildx', 'imagetools', 'inspect', '--raw',
                                    candidate['image_ref'])
    # A rerun started during inventory resolution invalidates this run-ID-only request.
    fresh_run = gh_json(endpoint)
    validate_source(fresh_run, source_run_id, repository)
    require(fresh_run['head_sha'] == run['head_sha'], 'source run changed during resolution')
    return build_inventory(source_run_id, repository, registry, run, artifacts, jobs,
                           archives, ecr, remote)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_run_id')
    parser.add_argument('--repository', required=True)
    parser.add_argument('--registry', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        inventory = resolve(args.source_run_id, args.repository, args.registry)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile,
            subprocess.TimeoutExpired) as error:
        print(f'candidate inventory rejected: {error}', file=sys.stderr)
        return 1
    print(f'Resolved {len(inventory["candidates"])} immutable source-run candidates')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
