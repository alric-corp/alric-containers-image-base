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

from scripts.pipeline.analytics.artifact_identity import IdentityError, verify_identity
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
                      'subjects_source'), ('producer_workflow', 'run_record'), label='bound artifact')
        integer(item['artifact_id'], 'artifact_id')
        for key in ('framework', 'name', 'path', 'api_record', 'subjects_source'):
            check(text(item[key], key) != '', 'BINDING_MANIFEST_INVALID', key + ' required')
        subjects = item['expected_subjects']
        fields(subjects, ('index',) + PLATFORMS, label='expected_subjects')
        for key in ('index',) + PLATFORMS:
            digest(subjects[key], 'expected_subjects.' + key, oci=True)
    return value


def _api_record(raw, item, manifest):
    """Cross-check the saved GitHub artifact record through the single identity contract.

    The actual comparison lives in `artifact_identity.verify_identity`, shared
    with the D2 intake, so there is one contract and one set of negatives. The
    artifacts endpoint cannot prove the run attempt or the producing workflow;
    `verify_identity` records them as declared-not-verifiable, and the binding
    receipt carries that verdict. `IdentityError` and this module's
    `AnalyticsError` share the exact `CODE: message` shape, so error codes and
    the CLI's code extraction are unchanged.
    """
    record = document(raw, limit=LIMITS['context_bytes'])
    origin, framework = manifest['origin'], item['framework']
    declared = dict(framework=framework, artifact_id=item['artifact_id'], artifact_name=item['name'],
                    repository_id=manifest['repository_id'], run_id=origin['run_id'],
                    run_attempt=origin['run_attempt'], source_sha=origin['source_sha'], ref=origin.get('ref'))
    if type(item.get('producer_workflow')) is dict:
        declared['workflow'] = item['producer_workflow']
    run_record = None
    if 'run_record' in item:
        run_record = document(read_local(Path(manifest['_base']) / item['run_record'],
                                         LIMITS['context_bytes']), limit=LIMITS['context_bytes'])
    try:
        identity = verify_identity(declared, record, run_record)
    except IdentityError as error:
        refuse(error.code, str(error).split(': ', 1)[1])
    # Translate the shared verified tier back to this module's receipt keys.
    verified = identity['verified']
    checks = dict(artifact_id='MATCHED', name='MATCHED', run='MATCHED', repository='MATCHED', source='MATCHED',
                  head_repository=verified['head_repository_id'],
                  branch={'MATCHED': 'MATCHED', 'NOT_PROVIDED': 'NOT_PROVIDED',
                          'NOT_APPLICABLE': 'NOT_APPLICABLE'}[verified['head_branch']])
    if 'run_attempt' in verified:
        checks['run_attempt'] = verified['run_attempt']
        checks['workflow_identity'] = verified['workflow_path']
    return record, checks, identity


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
    manifest['_base'] = str(base)  # so _api_record can resolve an optional run_record path
    with tempfile.TemporaryDirectory(prefix='.sbom-artifact-binding-', dir=work.parent) as temporary:
        root = Path(temporary)
        copies = root / 'inputs'
        copies.mkdir()
        selection, bound, frameworks = [], [], set()
        producer_identity_verified = True
        for item in manifest['artifacts']:
            framework = item['framework']
            check(framework not in frameworks, 'BINDING_MANIFEST_INVALID', 'duplicate framework ' + framework)
            frameworks.add(framework)
            # The attempt-name check now lives in the shared identity contract.
            api_raw = read_local(base / item['api_record'], LIMITS['context_bytes'])
            record, checks, identity = _api_record(api_raw, item, manifest)
            producer_identity_verified = producer_identity_verified and identity['producer_identity_verified']
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
                              subjects_source=item['subjects_source'],
                              producer_identity_verified=identity['producer_identity_verified'],
                              corporate_acceptance=identity['corporate_acceptance'],
                              identity=identity, checks=checks))
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
                       producer_identity_verified=producer_identity_verified,
                       corporate_acceptance='ELIGIBLE' if producer_identity_verified else 'FORBIDDEN',
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
