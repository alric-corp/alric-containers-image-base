"""Verify the exact index, build provenance and original signed SPDX subjects."""
import base64
import json
from pathlib import Path

from scripts.pipeline.consumer_apps.inventory import json_document, require
from scripts.pipeline.release.release_manifest import checksum
from scripts.pipeline.release.release_store import command
from scripts.pipeline.release.verify_promotion import verify_promotion
from scripts.pipeline.release.verify_publication import verify_publication


def read_index(image, item, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'index.json'
    command('oras', 'manifest', 'fetch', '--output', str(path), image)
    return verify_publication(item, item['digest'], path.read_bytes(),
                              image.split('@')[0].split(':stable')[0] + '@' + item['digest'])


def statements(raw):
    """Cosign versions emit either a JSON array or one DSSE envelope per line."""
    try:
        documents = json_document(raw)
        documents = documents if isinstance(documents, list) else [documents]
    except json.JSONDecodeError:
        documents = [json_document(line) for line in raw.splitlines() if line.strip()]
    return [json_document(base64.b64decode(item['payload'], validate=True)) for item in documents]


def verify_spdx(raw, expected):
    for statement in statements(raw):
        if (statement.get('predicateType') == 'https://spdx.dev/Document'
                and any(s.get('digest', {}).get('sha256') == expected['subject'][7:]
                        for s in statement.get('subject', []))
                and checksum(statement.get('predicate')) == expected['predicate_digest']):
            return
    raise ValueError('verified SPDX attestation does not match the original release SBOM')


def verify_image(manifest, framework, target_registry, directory):
    item = manifest['images'][framework]
    image = f'{target_registry}/image-base-{framework}@{item["digest"]}'
    directory = Path(directory)
    read_index(image, item, directory)
    verify_promotion(image, manifest['repository'], directory, source_sha=manifest['source_sha'])
    provenance = json_document((directory / 'provenance.json').read_bytes())
    invocation = (f'https://github.com/{manifest["repository"]}/actions/runs/'
                  f'{manifest["run_id"]}/attempts/{manifest["attempt"]}')
    require(any(entry.get('verificationResult', {}).get('statement', {}).get('predicate', {})
                .get('runDetails', {}).get('metadata', {}).get('invocationId') == invocation
                for entry in provenance), 'provenance does not bind the exact build run and attempt')
    identity = (f'https://github.com/{manifest["repository"]}/.github/workflows/'
                f'build-base-images.yml@refs/heads/{manifest["branch"]}')
    for sbom in item['sboms']:
        subject = image.split('@')[0] + '@' + sbom['subject']
        raw = command('cosign', 'verify-attestation', '--type', 'spdxjson',
                      '--certificate-identity', identity,
                      '--certificate-oidc-issuer', 'https://token.actions.githubusercontent.com',
                      '--certificate-github-workflow-sha', manifest['source_sha'], subject)
        verify_spdx(raw, sbom)
        (directory / (sbom['subject'][7:] + '-spdx.json')).write_bytes(raw)


def copy_image(manifest, framework, target_registry):
    item = manifest['images'][framework]
    source = f'{manifest["source_registry"]}/image-base-{framework}@{item["digest"]}'
    target = f'{target_registry}/image-base-{framework}:{item["tag"]}'
    # ORAS traverses OCI 1.1 referrers, including bundles and build provenance.
    # Cosign also carries legacy .sig/.att/.sbom tags on index and children.
    # Both use existing manifests/layers; no package resolution or rebuild.
    command('oras', 'cp', '--recursive', source, target, timeout=1200)
    command('cosign', 'copy', source, target, timeout=1200)
