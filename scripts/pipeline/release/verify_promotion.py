#!/usr/bin/env python3
"""Exige plataformas, assinatura e provenance da develop antes da promoção DEV."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from scripts.pipeline.artifacts.image_reference import require_digest_reference

IDENTITIES = Path(__file__).resolve().parents[3] / 'policies/release/signing-identities.json'


def verify_repository_identity(provenance, repository, expected):
    """Bind a renamed repository to signed immutable IDs, never just its old name."""
    for entry in provenance:
        certificate = entry.get('verificationResult', {}).get('signature', {}).get('certificate', {})
        required = {
            'sourceRepositoryIdentifier': expected['repository_id'],
            'sourceRepositoryOwnerIdentifier': expected['owner_id'],
            'sourceRepositoryURI': f'https://github.com/{repository}',
            'sourceRepositoryRef': 'refs/heads/develop',
        }
        if any(certificate.get(key) != value for key, value in required.items()):
            raise ValueError('provenance não confirma os IDs e a origem do repositório renomeado')


def verify_promotion(image, repository, reports=Path("reports"), source_sha=None):
    require_digest_reference(image)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repositório de origem inválido")
    reports.mkdir(parents=True, exist_ok=True)
    raw = subprocess.run(["docker", "buildx", "imagetools", "inspect", "--raw", image],
                         check=True, capture_output=True, text=True).stdout
    index = json.loads(raw)
    if index.get("mediaType") not in {
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    }:
        raise ValueError("candidato não é índice multi-arquitetura")
    platforms = [f"{entry['platform']['os']}/{entry['platform']['architecture']}"
                 for entry in index["manifests"]]
    if sorted(platforms) != ["linux/amd64", "linux/arm64"]:
        raise ValueError("índice deve conter exatamente amd64 e arm64")
    (reports / "candidate-index.json").write_text(raw)
    expected = json.loads(IDENTITIES.read_text()).get(repository)
    signers = [repository] + (expected['previous_names'] if expected else [])
    for name in ('signature', 'provenance', 'verified-identity'):
        (reports / f'{name}.json').unlink(missing_ok=True)
    for position, signer in enumerate(signers):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", signer):
            raise ValueError('identidade histórica inválida')
        workflow = f"{signer}/.github/workflows/build-base-images.yml"
        commands = {
            "signature": ["cosign", "verify", "--certificate-identity",
                          f"https://github.com/{workflow}@refs/heads/develop",
                          "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com", image],
            "provenance": ["gh", "attestation", "verify", f"oci://{image}", "--repo", signer,
                           "--signer-workflow", workflow, "--source-ref", "refs/heads/develop", "--format", "json"],
        }
        if source_sha is not None:
            if not re.fullmatch(r'[0-9a-f]{40}', source_sha):
                raise ValueError('invalid expected provenance revision')
            commands['provenance'].extend(['--source-digest', source_sha])
        evidence = {}
        try:
            for name, command in commands.items():
                output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
                parsed = json.loads(output)
                if not isinstance(parsed, list) or not parsed:
                    raise ValueError(f"nenhuma evidência verificada: {name}")
                if name == 'provenance' and expected:
                    verify_repository_identity(parsed, signer, expected)
                evidence[name] = output
        except subprocess.CalledProcessError:
            if position == len(signers) - 1:
                raise
            continue
        # Both verifiers must accept the SAME signer and digest. Never mix attempts.
        for name, output in evidence.items():
            (reports / f'{name}.json').write_text(output)
        if expected:
            (reports / 'verified-identity.json').write_text(json.dumps({
                'repository': repository, 'signer_repository': signer,
                'repository_id': expected['repository_id'], 'owner_id': expected['owner_id'],
                'legacy_name': signer != repository, 'image': image,
            }, indent=2) + '\n')
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("repository")
    args = parser.parse_args()
    try:
        verify_promotion(args.image, args.repository)
    except subprocess.CalledProcessError as error:
        print(error.stderr or str(error), file=sys.stderr)
        return error.returncode
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"verificação da promoção falhou: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
