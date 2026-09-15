"""Publication continuation for the P1-02 retry/reuse laboratory.

Consumes the real gate result already produced by lab-retry in the SAME
run/attempt (retry_lab.valid_gate); never re-implements artifact selection.
Publishes only to the two allowlisted, pre-provisioned lab ECR repositories
(never image-base-* operational names) with a tag computed internally
(never accepted as input), and verifies signature/provenance/SBOM under the
laboratory's OWN workflow identity, never the product's. Profile A: the two
repositories are assumed already provisioned and IMMUTABLE; this module only
ever reads their configuration back, it never provisions or reconfigures one.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from scripts.pipeline.artifacts.image_reference import require_digest_reference
from scripts.pipeline.runtime import retry_lab
from scripts.pipeline.runtime.contract_evidence import digest, read_json

ACCOUNT_ID = '712107929769'
REGION = 'us-east-1'
ROLE_ARN = 'arn:aws:iam::712107929769:role/github-actions-image-base-p102-lab'
REPOSITORIES = {'runtime': 'p102-lab-go1-26', 'dev': 'p102-lab-go1-26-dev'}
FORBIDDEN_PREFIX = 'image-base-'
FORBIDDEN_TAGS = {'stable', 'latest'}
LAB_WORKFLOW = f'{retry_lab.REPOSITORY}/{retry_lab.WORKFLOW}'
LAB_CERTIFICATE_IDENTITY = f'https://github.com/{LAB_WORKFLOW}@refs/heads/main'
OIDC_ISSUER = 'https://token.actions.githubusercontent.com'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def require_allowlisted_repository(name):
    """The only guard that decides which ECR repository the lab may ever touch."""
    require(isinstance(name, str) and name, 'missing repository name')
    require(not name.startswith(FORBIDDEN_PREFIX),
            'lab repository must not use the operational image-base- prefix')
    require(name in REPOSITORIES.values(), f'{name!r} is not in the lab repository allowlist')


def tag(run_id, attempt):
    """Deterministic, never accepted as input; the only valid lab tag shape."""
    require(re.fullmatch(r'[1-9][0-9]*', str(run_id)), 'invalid run_id for tag computation')
    require(attempt in (1, 2), 'invalid attempt for tag computation')
    return f'p1-02-lab-{run_id}-{attempt}'


def require_lab_tag(value, run_id, attempt):
    require(value not in FORBIDDEN_TAGS, 'stable/latest are never valid lab tags')
    require(value == tag(run_id, attempt),
            'tag must be the deterministic lab tag, never external input')


def resolve_target(env):
    """Fail closed if the future LAB_* repository variables are missing or wrong."""
    region = env.get('LAB_AWS_REGION')
    role = env.get('LAB_AWS_ROLE_ARN')
    runtime_repo = env.get('LAB_ECR_REPOSITORY_RUNTIME')
    dev_repo = env.get('LAB_ECR_REPOSITORY_DEV')
    require(region == REGION, 'LAB_AWS_REGION must be the approved lab region')
    require(role == ROLE_ARN, 'LAB_AWS_ROLE_ARN must be the approved isolated lab role')
    require(runtime_repo == REPOSITORIES['runtime'],
            'LAB_ECR_REPOSITORY_RUNTIME must be the exact allowlisted lab repository')
    require(dev_repo == REPOSITORIES['dev'],
            'LAB_ECR_REPOSITORY_DEV must be the exact allowlisted lab repository')
    for name in (runtime_repo, dev_repo):
        require_allowlisted_repository(name)
    return {'account_id': ACCOUNT_ID, 'region': region, 'role_arn': role,
            'repositories': {'runtime': runtime_repo, 'dev': dev_repo}}


def bind(env, event, gate):
    """The single fail-closed checkpoint required before any AWS auth."""
    ctx = retry_lab.context(env, event)
    require(ctx['run_attempt'] == 2, 'publication only continues from a validated attempt 2')
    retry_lab.valid_gate(gate, ctx)
    require(gate['reused'] is True,
            'publication requires reused evidence from attempt 1, not a fresh producer')
    target = resolve_target(env)
    tag_value = tag(ctx['run_id'], ctx['run_attempt'])
    return {'context': ctx, 'gate': gate, 'target': target, 'tag': tag_value}


def require_gate_layout_binding(gate, verified_runtime_digest, verified_dev_digest):
    """validated-oci-* is uploaded with overwrite:true — the OCI lab-publish just
    revalidated is never assumed to be the one the gate approved; it must be
    proven equal to gate.index_digest/dev_index_digest before any AWS auth."""
    gate_runtime_digest = digest(gate['index_digest'])
    gate_dev_digest = digest(gate['dev_index_digest'])
    verified_runtime_digest = digest(verified_runtime_digest)
    verified_dev_digest = digest(verified_dev_digest)
    require(verified_runtime_digest == gate_runtime_digest,
            'revalidated runtime OCI digest differs from the gate-approved digest')
    require(verified_dev_digest == gate_dev_digest,
            'revalidated dev OCI digest differs from the gate-approved digest')
    return {'gate_index_digest': gate_runtime_digest, 'gate_dev_index_digest': gate_dev_digest,
            'verified_runtime_digest': verified_runtime_digest,
            'verified_dev_digest': verified_dev_digest, 'status': 'LAYOUT_BOUND_TO_GATE'}


def preflight(descriptor, expected_name):
    """Validate a read-only DescribeRepositories result; never corrects drift."""
    require_allowlisted_repository(expected_name)
    require(descriptor.get('repositoryName') == expected_name,
            'preflight repository name does not match the expected lab repository')
    require(descriptor.get('imageTagMutability') == 'IMMUTABLE',
            'lab repository must be IMMUTABLE, with no mutability exclusions')
    require(not descriptor.get('imageTagMutabilityExclusionFilters'),
            'lab repository must not declare any mutability exclusion filter')
    return {'repository': expected_name, 'imageTagMutability': descriptor['imageTagMutability'],
            'status': 'PREFLIGHT_OK'}


def verify_signature(image_ref, run=subprocess.run):
    require_digest_reference(image_ref)
    repository = image_ref.split('@', 1)[0].rsplit('/', 1)[-1]
    require_allowlisted_repository(repository)
    result = run(['cosign', 'verify', '--certificate-identity', LAB_CERTIFICATE_IDENTITY,
                 '--certificate-oidc-issuer', OIDC_ISSUER, image_ref],
                check=True, capture_output=True, text=True, timeout=180)
    parsed = json.loads(result.stdout)
    require(isinstance(parsed, list) and parsed, 'no verified lab signature evidence')
    return {'image_ref': image_ref, 'certificate_identity': LAB_CERTIFICATE_IDENTITY,
            'oidc_issuer': OIDC_ISSUER, 'status': 'VERIFIED'}


def verify_provenance(image_ref, run=subprocess.run):
    require_digest_reference(image_ref)
    repository = image_ref.split('@', 1)[0].rsplit('/', 1)[-1]
    require_allowlisted_repository(repository)
    result = run(['gh', 'attestation', 'verify', f'oci://{image_ref}', '--repo', retry_lab.REPOSITORY,
                 '--signer-workflow', LAB_WORKFLOW, '--source-ref', 'refs/heads/main',
                 '--format', 'json'], check=True, capture_output=True, text=True, timeout=180)
    parsed = json.loads(result.stdout)
    require(isinstance(parsed, list) and parsed, 'no verified lab provenance evidence')
    return {'image_ref': image_ref, 'signer_workflow': LAB_WORKFLOW,
            'source_ref': 'refs/heads/main', 'status': 'VERIFIED'}


def verify_sbom(image_ref, run=subprocess.run):
    require_digest_reference(image_ref)
    repository = image_ref.split('@', 1)[0].rsplit('/', 1)[-1]
    require_allowlisted_repository(repository)
    result = run(['cosign', 'verify-attestation', '--type', 'spdxjson',
                 '--certificate-identity', LAB_CERTIFICATE_IDENTITY,
                 '--certificate-oidc-issuer', OIDC_ISSUER, image_ref],
                check=True, capture_output=True, text=True, timeout=180)
    require(bool(result.stdout.strip()), 'no verified lab SBOM attestation evidence')
    return {'image_ref': image_ref, 'certificate_identity': LAB_CERTIFICATE_IDENTITY,
            'oidc_issuer': OIDC_ISSUER, 'status': 'VERIFIED'}


def digest_equal(publication):
    """Equality alone is not enough: each value must first be a real sha256 digest."""
    values = (publication['validated_digest'], publication['copied_digest'],
             publication['remote_digest'])
    for value in values:
        digest(value)
    return values[0] == values[1] == values[2]


def finalize(binding, layout_binding, runtime_publication, dev_publication, runtime_signature,
            dev_signature, runtime_provenance, dev_provenance, runtime_sbom, dev_sbom):
    """PASS only if every mandatory check is present and consistent; never a partial PASS."""
    ctx, gate, target, tag_value = (binding['context'], binding['gate'],
                                    binding['target'], binding['tag'])
    require(ctx['run_attempt'] == 2 and gate['selected_attempt'] == 1 and gate['reused'] is True,
            'finalize requires a bound attempt-2 continuation of attempt-1 evidence')
    require_lab_tag(tag_value, ctx['run_id'], ctx['run_attempt'])
    require(layout_binding.get('status') == 'LAYOUT_BOUND_TO_GATE'
            and layout_binding.get('gate_index_digest') == digest(gate['index_digest'])
            and layout_binding.get('gate_dev_index_digest') == digest(gate['dev_index_digest']),
            'layout binding is missing or does not reference this gate')
    gate_digests = {'runtime': layout_binding['gate_index_digest'],
                    'dev': layout_binding['gate_dev_index_digest']}
    verified_digests = {'runtime': layout_binding['verified_runtime_digest'],
                        'dev': layout_binding['verified_dev_digest']}
    for key, publication in (('runtime', runtime_publication), ('dev', dev_publication)):
        require_allowlisted_repository(target['repositories'][key])
        require(digest_equal(publication),
                f'{key} validated/copied/remote digest mismatch — publication rejected')
        require(publication['validated_digest'] == verified_digests[key] == gate_digests[key],
                f'{key} published digest is not the one the retry/reuse gate approved')
    for evidence in (runtime_signature, dev_signature):
        require(evidence.get('certificate_identity') == LAB_CERTIFICATE_IDENTITY
                and evidence.get('status') == 'VERIFIED', 'signature verification incomplete')
    for evidence in (runtime_provenance, dev_provenance):
        require(evidence.get('signer_workflow') == LAB_WORKFLOW
                and evidence.get('status') == 'VERIFIED', 'provenance verification incomplete')
    for evidence in (runtime_sbom, dev_sbom):
        require(evidence.get('certificate_identity') == LAB_CERTIFICATE_IDENTITY
                and evidence.get('status') == 'VERIFIED', 'SBOM verification incomplete')
    return {
        'run_id': ctx['run_id'], 'run_attempt': ctx['run_attempt'], 'revision': ctx['head_sha'],
        'framework': ctx['framework'], 'selected_attempt': gate['selected_attempt'],
        'reused': gate['reused'], 'tag': tag_value, 'repositories': target['repositories'],
        'runtime': {'gate_digest': gate_digests['runtime'],
                    'verified_digest': verified_digests['runtime'],
                    'validated_digest': runtime_publication['validated_digest'],
                    'copied_digest': runtime_publication['copied_digest'],
                    'remote_digest': runtime_publication['remote_digest'],
                    'signature': runtime_signature, 'provenance': runtime_provenance,
                    'sbom': runtime_sbom},
        'dev': {'gate_digest': gate_digests['dev'],
               'verified_digest': verified_digests['dev'],
               'validated_digest': dev_publication['validated_digest'],
               'copied_digest': dev_publication['copied_digest'],
               'remote_digest': dev_publication['remote_digest'],
               'signature': dev_signature, 'provenance': dev_provenance, 'sbom': dev_sbom},
        'stable_touched': False, 'status': 'PASS',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('bind', 'verify-layout-binding', 'preflight',
                                         'verify-signature', 'verify-provenance', 'verify-sbom',
                                         'finalize'))
    parser.add_argument('--gate')
    parser.add_argument('--runtime-digest')
    parser.add_argument('--dev-digest')
    parser.add_argument('--descriptor')
    parser.add_argument('--repository-key', choices=('runtime', 'dev'))
    parser.add_argument('--image-ref')
    parser.add_argument('--bind')
    parser.add_argument('--layout-binding')
    parser.add_argument('--runtime-publication')
    parser.add_argument('--dev-publication')
    parser.add_argument('--runtime-signature')
    parser.add_argument('--dev-signature')
    parser.add_argument('--runtime-provenance')
    parser.add_argument('--dev-provenance')
    parser.add_argument('--runtime-sbom')
    parser.add_argument('--dev-sbom')
    parser.add_argument('--output')
    args = parser.parse_args()
    code = 0
    try:
        if args.mode == 'bind':
            event, _ = read_json(os.environ['GITHUB_EVENT_PATH'])
            result = bind(os.environ, event, read_json(args.gate)[0])
        elif args.mode == 'verify-layout-binding':
            result = require_gate_layout_binding(read_json(args.gate)[0],
                                                 args.runtime_digest, args.dev_digest)
        elif args.mode == 'preflight':
            result = preflight(read_json(args.descriptor)[0], REPOSITORIES[args.repository_key])
        elif args.mode == 'verify-signature':
            result = verify_signature(args.image_ref)
        elif args.mode == 'verify-provenance':
            result = verify_provenance(args.image_ref)
        elif args.mode == 'verify-sbom':
            result = verify_sbom(args.image_ref)
        else:
            result = finalize(
                read_json(args.bind)[0], read_json(args.layout_binding)[0],
                read_json(args.runtime_publication)[0], read_json(args.dev_publication)[0],
                read_json(args.runtime_signature)[0], read_json(args.dev_signature)[0],
                read_json(args.runtime_provenance)[0], read_json(args.dev_provenance)[0],
                read_json(args.runtime_sbom)[0], read_json(args.dev_sbom)[0])
    except (KeyError, ValueError, TypeError, OSError, AttributeError, StopIteration,
           subprocess.SubprocessError, json.JSONDecodeError) as error:
        code, result = 1, {'status': 'INVALID_SCENARIO', 'error': str(error)}
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
