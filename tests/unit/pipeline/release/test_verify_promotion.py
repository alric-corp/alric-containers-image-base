import json
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr

from scripts.pipeline.release.verify_promotion import main, verify_promotion, verify_repository_identity


IMAGE = "example.invalid/test@sha256:" + "a" * 64
REPO = "owner/repository"


def index(arches=("amd64", "arm64")):
    return json.dumps({"mediaType": "application/vnd.oci.image.index.v1+json",
                       "manifests": [{"platform": {"os": "linux", "architecture": arch}} for arch in arches]})


class VerificationTests(unittest.TestCase):
    def test_cli_expected_errors_are_clean_and_nonzero(self):
        for error in (ValueError("digest inválido"), KeyError("platform"),
                      TypeError("Metadata null"), FileNotFoundError("cosign"),
                      subprocess.CalledProcessError(10, ["cosign"], stderr="no signatures found")):
            with self.subTest(error=error), patch("sys.argv", ["verify_promotion.py", IMAGE, REPO]), \
                  patch("scripts.pipeline.release.verify_promotion.verify_promotion", side_effect=error), \
                 redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main(), 10 if isinstance(error, subprocess.CalledProcessError) else 1)
                self.assertTrue(stderr.getvalue().strip())
                self.assertNotIn("Traceback", stderr.getvalue())

    def test_both_verifiers_receive_digest_and_restricted_identity(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.pipeline.release.verify_promotion.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0, stdout=output) for output in (index(), '[{"verified":true}]', '[{"verified":true}]')
        ]) as run:
            verify_promotion(IMAGE, REPO, Path(directory))
            signature = run.call_args_list[1].args[0]
            provenance = run.call_args_list[2].args[0]
            self.assertEqual(signature[-1], IMAGE)
            self.assertIn(f"https://github.com/{REPO}/.github/workflows/build-base-images.yml@refs/heads/develop", signature)
            self.assertIn("refs/heads/develop", provenance)
            self.assertNotIn("--certificate-identity-regexp", signature)
            self.assertFalse(any("refs/heads/main" in value for value in signature + provenance))
            self.assertIn(f"oci://{IMAGE}", provenance)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 3)

    def test_missing_or_duplicate_platform_blocks_verification(self):
        for arches in (("amd64",), ("amd64", "amd64"), ("amd64", "arm64", "unknown")):
            with self.subTest(arches=arches), tempfile.TemporaryDirectory() as directory, patch(
                "scripts.pipeline.release.verify_promotion.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=index(arches))
            ) as run:
                with self.assertRaises(ValueError):
                    verify_promotion(IMAGE, REPO, Path(directory))
                self.assertEqual(run.call_count, 1)

    def test_failed_signature_or_provenance_blocks_promotion(self):
        for failure_at in (1, 2):
            results = [subprocess.CompletedProcess([], 0, stdout=index())]
            if failure_at == 2:
                results.append(subprocess.CompletedProcess([], 0, stdout='[{"verified":true}]'))
            results.append(subprocess.CalledProcessError(1, ["verifier"]))
            with self.subTest(failure_at=failure_at), tempfile.TemporaryDirectory() as directory, patch(
                "scripts.pipeline.release.verify_promotion.subprocess.run", side_effect=results
            ) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    verify_promotion(IMAGE, REPO, Path(directory))
                self.assertEqual(run.call_count, failure_at + 1)

    def test_empty_verification_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.pipeline.release.verify_promotion.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0, stdout=index()), subprocess.CompletedProcess([], 0, stdout="[]")
        ]):
            with self.assertRaises(ValueError):
                verify_promotion(IMAGE, REPO, Path(directory))


CURRENT = 'alric-corp/alric-containers-image-base'
LEGACY = 'alric-corp/itau-xj7-containers-image-base'
IDENTITY = {'repository_id': '1360616627', 'owner_id': '178685987'}


def provenance(signer):
    return [{'verificationResult': {'signature': {'certificate': {
        'sourceRepositoryIdentifier': IDENTITY['repository_id'],
        'sourceRepositoryOwnerIdentifier': IDENTITY['owner_id'],
        'sourceRepositoryURI': f'https://github.com/{signer}',
        'sourceRepositoryRef': 'refs/heads/develop',
    }}}}]


def success(output):
    return subprocess.CompletedProcess([], 0, stdout=output)


class RepositoryRenameTests(unittest.TestCase):
    def test_new_identity_requires_signed_repository_and_owner_ids(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                'scripts.pipeline.release.verify_promotion.subprocess.run', side_effect=[
                    success(index()), success('[{}]'), success(json.dumps(provenance(CURRENT)))]) as run:
            reports = Path(directory)
            verify_promotion(IMAGE, CURRENT, reports)
            identity = json.loads((reports / 'verified-identity.json').read_text())
            self.assertEqual(identity['signer_repository'], CURRENT)
            self.assertFalse(identity['legacy_name'])
            self.assertEqual(run.call_count, 3)

    def test_renamed_repository_signature_and_provenance_use_same_develop_identity(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                'scripts.pipeline.release.verify_promotion.subprocess.run', side_effect=[
                    success(index()), subprocess.CalledProcessError(1, ['cosign']),
                    success('[{}]'), success(json.dumps(provenance(LEGACY)))]) as run:
            reports = Path(directory)
            verify_promotion(IMAGE, CURRENT, reports)
            signature = run.call_args_list[2].args[0]
            attestation = run.call_args_list[3].args[0]
            self.assertIn(f'https://github.com/{LEGACY}/.github/workflows/build-base-images.yml@refs/heads/develop', signature)
            self.assertEqual(attestation[attestation.index('--repo') + 1], LEGACY)
            self.assertNotIn('--certificate-identity-regexp', signature)
            self.assertTrue(json.loads((reports / 'verified-identity.json').read_text())['legacy_name'])

    def test_reused_name_wrong_owner_and_other_branch_are_rejected(self):
        for key, value in [('sourceRepositoryIdentifier', '999'),
                           ('sourceRepositoryOwnerIdentifier', '999'),
                           ('sourceRepositoryURI', f'https://github.com/{CURRENT}'),
                           ('sourceRepositoryRef', 'refs/heads/other'),
                           ('sourceRepositoryRef', 'refs/heads/main')]:
            proof = provenance(LEGACY)
            proof[0]['verificationResult']['signature']['certificate'][key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                verify_repository_identity(proof, LEGACY, IDENTITY)

    def test_main_provenance_cannot_authorize_dev_promotion(self):
        proof = provenance(CURRENT)
        proof[0]['verificationResult']['signature']['certificate']['sourceRepositoryRef'] = 'refs/heads/main'
        with tempfile.TemporaryDirectory() as directory, patch(
                'scripts.pipeline.release.verify_promotion.subprocess.run', side_effect=[
                    success(index()), success('[{}]'), success(json.dumps(proof))]) as run:
            reports = Path(directory)
            with self.assertRaises(ValueError):
                verify_promotion(IMAGE, CURRENT, reports)
            self.assertEqual(run.call_count, 3)
            for evidence in ('signature', 'provenance', 'verified-identity'):
                self.assertFalse((reports / f'{evidence}.json').exists())

    def test_unverified_predicate_cannot_supply_the_immutable_identity(self):
        proof = [{'verificationResult': {'statement': {'predicate': {
            'sourceRepositoryIdentifier': IDENTITY['repository_id'],
            'sourceRepositoryOwnerIdentifier': IDENTITY['owner_id'],
        }}}}]
        with self.assertRaises(ValueError):
            verify_repository_identity(proof, LEGACY, IDENTITY)

    def test_missing_certificate_id_fails_closed(self):
        proof = provenance(LEGACY)
        del proof[0]['verificationResult']['signature']['certificate']['sourceRepositoryIdentifier']
        with self.assertRaises(ValueError):
            verify_repository_identity(proof, LEGACY, IDENTITY)

    def test_signature_and_provenance_cannot_mix_current_and_legacy_signers(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                'scripts.pipeline.release.verify_promotion.subprocess.run', side_effect=[
                    success(index()), success('[{}]'), subprocess.CalledProcessError(1, ['gh']),
                    subprocess.CalledProcessError(1, ['cosign'])]):
            reports = Path(directory)
            (reports / 'signature.json').write_text('["stale"]')
            with self.assertRaises(subprocess.CalledProcessError):
                verify_promotion(IMAGE, CURRENT, reports)
            self.assertFalse((reports / 'signature.json').exists())
            self.assertFalse((reports / 'provenance.json').exists())


if __name__ == "__main__":
    unittest.main()
