"""Bind downloaded `sbom-<framework>-<attempt>` artifacts to their declared origin, then stage them.

Thin caller between an integrator's acquisition and the unchanged
`artifact_input.stage` → normalizer path. The integrator supplies, explicitly:
the artifact ZIPs, the GitHub REST artifact records saved with them
(`GET /repos/{owner}/{repo}/actions/artifacts/{id}`), the run origin and the
expected index/platform subjects from an independent source (publication
evidence or a verified consumer record). Before anything becomes visible this
module refuses a different artifact id/name, run, repository, source commit,
attempt, archive digest/size or subject. It never downloads, calls GitHub or
AWS, executes artifact members, or infers an absent value; absent optional
facts are recorded as NOT_PROVIDED. No HGC-04 record is required. Opt-in CLI
only: no workflow ingests through it.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from scripts.pipeline.analytics.artifact_input import stage
from scripts.pipeline.analytics.spdx import (
    AnalyticsError, LIMITS, canonical, digest, document, fields, integer, read_local, require, sha256, text,
)

CLASSIFICATIONS = ('SYNTHETIC', 'SANITIZED', 'LAB_REAL', 'REAL_AUTHORIZED')
ARCHIVE_POLICIES = ('REQUIRED', 'RECORD_ONLY')
PLATFORMS = ('linux/amd64', 'linux/arm64')
RUN_KEYS = ('id', 'repository_id', 'head_sha')
RUN_OPTIONAL = ('head_repository_id', 'head_branch')
RECORD_KEYS = ('id', 'name', 'workflow_run')


def refuse(code, message):
    raise AnalyticsError(code + ': ' + message)


def check(condition, code, message):
    if not condition:
        refuse(code, message)


def _placeholders(value):
    if isinstance(value, str):
        return [value] if '<' in value or '>' in value else []
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return [found for item in items for found in _placeholders(item)]


def _manifest(value):
    fields(value, ('schema_version', 'sample_classification', 'origin', 'repository_id', 'image_registry',
                   'repository_prefix', 'archive_digest_policy', 'artifacts'), label='binding manifest')
    check(type(value['schema_version']) is int and value['schema_version'] == 1, 'BINDING_MANIFEST_INVALID',
          'unsupported binding manifest schema')
    check(not _placeholders(value), 'BINDING_MANIFEST_INVALID', 'placeholder value in binding manifest')
    check(value['sample_classification'] in CLASSIFICATIONS, 'BINDING_MANIFEST_INVALID',
          'sample_classification must be one of ' + ', '.join(CLASSIFICATIONS))
    check(value['archive_digest_policy'] in ARCHIVE_POLICIES, 'BINDING_MANIFEST_INVALID',
          'archive_digest_policy must be REQUIRED or RECORD_ONLY')
    integer(value['repository_id'], 'repository_id')
    origin = value['origin']
    check(type(origin) is dict, 'BINDING_MANIFEST_INVALID', 'origin must be an object')
    integer(origin.get('run_id'), 'origin.run_id')
    integer(origin.get('run_attempt'), 'origin.run_attempt')
    digest(origin.get('source_sha'), 'origin.source_sha', git=True)
    artifacts = value['artifacts']
    check(type(artifacts) is list and artifacts, 'BINDING_MANIFEST_INVALID', 'artifacts must be a non-empty list')
    for item in artifacts:
        fields(item, ('framework', 'name', 'path', 'artifact_id', 'api_record', 'expected_subjects',
                      'subjects_source'), label='bound artifact')
        integer(item['artifact_id'], 'artifact_id')
        for key in ('framework', 'name', 'path', 'api_record', 'subjects_source'):
            check(text(item[key], key) != '', 'BINDING_MANIFEST_INVALID', key + ' required')
        subjects = item['expected_subjects']
        fields(subjects, ('index',) + PLATFORMS, label='expected_subjects')
        for key in ('index',) + PLATFORMS:
            digest(subjects[key], 'expected_subjects.' + key, oci=True)
    return value


def _api_record(raw, item, manifest):
    """Compare the saved GitHub artifact record with the declared identity; never fill gaps."""
    record = document(raw, limit=LIMITS['context_bytes'])
    origin, framework = manifest['origin'], item['framework']
    check(all(key in record for key in RECORD_KEYS) and type(record['workflow_run']) is dict
          and all(key in record['workflow_run'] for key in RUN_KEYS), 'ARTIFACT_RECORD_INCOMPLETE',
          framework + ': API record lacks id/name/workflow_run.{id,repository_id,head_sha}')
    run = record['workflow_run']
    checks = {}
    check(type(record['id']) is int and record['id'] == item['artifact_id'], 'ARTIFACT_ID_DIFFERS',
          framework + ': API record id differs from artifact_id')
    check(record['name'] == item['name'], 'ARTIFACT_NAME_DIFFERS', framework + ': API record name differs')
    check(type(run['id']) is int and run['id'] == origin['run_id'], 'ARTIFACT_RUN_DIFFERS',
          framework + ': artifact belongs to run %s, origin declares %s' % (run['id'], origin['run_id']))
    check(type(run['repository_id']) is int and run['repository_id'] == manifest['repository_id'],
          'ARTIFACT_REPOSITORY_DIFFERS', framework + ': artifact run repository_id differs')
    check(run['head_sha'] == origin['source_sha'], 'ARTIFACT_SOURCE_DIFFERS',
          framework + ': artifact run head_sha differs from origin source_sha')
    checks.update(artifact_id='MATCHED', name='MATCHED', run='MATCHED', repository='MATCHED', source='MATCHED')
    if 'head_repository_id' in run:
        check(run['head_repository_id'] == manifest['repository_id'], 'ARTIFACT_REPOSITORY_DIFFERS',
              framework + ': artifact run head repository differs (fork)')
        checks['head_repository'] = 'MATCHED'
    else:
        checks['head_repository'] = 'NOT_PROVIDED'
    ref = origin.get('ref')
    if type(ref) is str and ref.startswith('refs/heads/') and 'head_branch' in run:
        check(run['head_branch'] == ref[len('refs/heads/'):], 'ARTIFACT_BRANCH_DIFFERS',
              framework + ': artifact run head_branch differs from origin ref')
        checks['branch'] = 'MATCHED'
    else:
        checks['branch'] = 'NOT_PROVIDED' if 'head_branch' not in run else 'NOT_APPLICABLE'
    return record, checks


def _archive(source, record, policy, framework, copies):
    """Hash the exact bytes once and stage a private copy of them (no second read of the source)."""
    checks = {}
    if source.is_dir() and not source.is_symlink():
        check(policy == 'RECORD_ONLY', 'ARCHIVE_NOT_VERIFIABLE',
              framework + ': extracted directory cannot be bound to the API archive digest')
        target = copies / (framework + '.dir')
        shutil.copytree(source, target, symlinks=True)  # artifact_input refuses links; nothing is followed here
        checks.update(archive_digest='NOT_APPLICABLE', archive_size='NOT_APPLICABLE')
        return target, None, checks
    check(source.suffix == '.zip', 'BINDING_MANIFEST_INVALID', framework + ': artifact path must be a .zip or directory')
    raw = read_local(source, LIMITS['batch_bytes'])
    archive_sha = sha256(raw)
    if 'digest' in record and record['digest'] is not None:
        check(record['digest'] == 'sha256:' + archive_sha, 'ARCHIVE_DIGEST_DIFFERS',
              framework + ': ZIP sha256 differs from the API artifact digest')
        checks['archive_digest'] = 'MATCHED'
    else:
        check(policy == 'RECORD_ONLY', 'ARCHIVE_DIGEST_NOT_PROVIDED',
              framework + ': API record has no artifact digest and policy is REQUIRED')
        checks['archive_digest'] = 'NOT_PROVIDED'
    if 'size_in_bytes' in record:
        check(record['size_in_bytes'] == len(raw), 'ARCHIVE_SIZE_DIFFERS', framework + ': ZIP size differs from API')
        checks['archive_size'] = 'MATCHED'
    else:
        checks['archive_size'] = 'NOT_PROVIDED'
    target = copies / (framework + '.zip')
    target.write_bytes(raw)
    return target, archive_sha, checks


def bind(manifest, work, *, base_directory=Path('.')):
    """Refuse divergent identity, then stage through artifact_input; publish `work` atomically."""
    manifest = _manifest(manifest)
    work = Path(work)
    check(not work.exists() and not work.is_symlink(), 'BINDING_WORK_EXISTS', 'staging directory must not exist')
    work.parent.mkdir(parents=True, exist_ok=True)
    origin, base = manifest['origin'], Path(base_directory)
    with tempfile.TemporaryDirectory(prefix='.sbom-artifact-binding-', dir=work.parent) as temporary:
        root = Path(temporary)
        copies = root / 'inputs'
        copies.mkdir()
        selection, bound, frameworks = [], [], set()
        for item in manifest['artifacts']:
            framework = item['framework']
            check(framework not in frameworks, 'BINDING_MANIFEST_INVALID', 'duplicate framework ' + framework)
            frameworks.add(framework)
            check(item['name'] == 'sbom-%s-%d' % (framework, origin['run_attempt']), 'ARTIFACT_ATTEMPT_DIFFERS',
                  framework + ': artifact name does not carry the origin run attempt')
            api_raw = read_local(base / item['api_record'], LIMITS['context_bytes'])
            record, checks = _api_record(api_raw, item, manifest)
            source = base / item['path']
            check(not source.is_symlink(), 'BINDING_MANIFEST_INVALID', framework + ': artifact path is a symlink')
            target, archive_sha, archive_checks = _archive(source, record, manifest['archive_digest_policy'],
                                                           framework, copies)
            checks.update(archive_checks)
            selection.append(dict(framework=framework, name=item['name'], path=target.name,
                                  artifact_id=item['artifact_id'],
                                  expected_index_digest=item['expected_subjects']['index']))
            bound.append(dict(framework=framework, name=item['name'], artifact_id=item['artifact_id'],
                              api_record_sha256=sha256(api_raw), archive_sha256=archive_sha,
                              api_record_expired=record.get('expired', 'NOT_PROVIDED'),
                              subjects_source=item['subjects_source'], checks=checks))
        staged = root / 'staged'
        try:
            receipt = stage(dict(schema_version=1, origin=origin, image_registry=manifest['image_registry'],
                                 repository_prefix=manifest['repository_prefix'], artifacts=selection),
                            staged, base_directory=copies)
        except (AnalyticsError, OSError, KeyError, TypeError) as error:
            refuse('STAGING_REFUSED', str(error))
        context = document(read_local(staged / 'context.json', LIMITS['context_bytes']), limit=LIMITS['context_bytes'])
        images = {image['framework']: image for image in context['images']}
        for item, entry in zip(manifest['artifacts'], bound):
            image = images[item['framework']]
            expected = item['expected_subjects']
            check(image['image_index_digest'] == expected['index'], 'SUBJECT_DIFFERS',
                  item['framework'] + ': staged index subject differs')
            check(image['platforms'] == {key: expected[key] for key in PLATFORMS}, 'SUBJECT_DIFFERS',
                  item['framework'] + ': validated-index platform subjects differ from the expected subjects')
            entry['checks'].update(index_subject='MATCHED', platform_subjects='MATCHED')
        binding = dict(schema_version=1, status='BOUND_AND_STAGED',
                       sample_classification=manifest['sample_classification'], origin=origin,
                       repository_id=manifest['repository_id'],
                       archive_digest_policy=manifest['archive_digest_policy'], artifacts=bound,
                       staging_receipt_sha256=sha256(read_local(staged / 'staging-receipt.json', LIMITS['context_bytes'])),
                       batch_id=receipt['batch_id'], network_calls=0, cloud_calls=0,
                       cryptographic_authenticity='NOT_REVALIDATED', publication_authority=False,
                       custody_record='NOT_REQUIRED', ingestion='NOT_PERFORMED', hosted_execution='NOT_PROVEN')
        (staged / 'binding-receipt.json').write_bytes(canonical(binding))
        check(not work.exists() and not work.is_symlink(), 'BINDING_WORK_EXISTS', 'staging directory must not exist')
        os.rename(staged, work)
    return binding


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--manifest', required=True, type=Path,
                        help='binding manifest v1; artifact and API record paths are relative to it')
    parser.add_argument('--work', required=True, type=Path, help='new private staging directory')
    args = parser.parse_args(argv)
    try:
        manifest = document(read_local(args.manifest, LIMITS['context_bytes']), limit=LIMITS['context_bytes'])
        result = bind(manifest, args.work, base_directory=args.manifest.resolve().parent)
    except (OSError, ValueError, KeyError, TypeError) as error:
        code = re.match(r'([A-Z][A-Z_]+): ', str(error))
        print(canonical(dict(status='REFUSED', code=code.group(1) if code else 'BINDING_INPUT_INVALID',
                             message=str(error))).decode(), file=sys.stderr)
        return 1
    print(canonical(result).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
