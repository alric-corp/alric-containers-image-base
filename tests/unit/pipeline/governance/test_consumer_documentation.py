"""Offline drift checks for consumer examples; no registry commands are executed."""
import json
from pathlib import Path
import re
import shlex
from string import Template
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlsplit

from scripts.pipeline.governance.workflow_dependencies import dependencies
from scripts.pipeline.release.publish_sboms import publish
from scripts.pipeline.release.verify_promotion import IDENTITIES, verify_promotion
from tools.check_ai_context import link_targets

ROOT = Path(__file__).resolve().parents[4]
CONTRACT = ROOT / "docs/consumer-verification-contract.md"
SPEC = ROOT / "specs/2026-09-13-consumer-contract-rfc-refresh"
DOCUMENTS = [ROOT / name for name in (
    "README.md", "RFC-013-Image-Base-Completa-com-Mermaid.md", "docs/README.md",
    "docs/repository-architecture.md", "docs/m09-m12-reusable-workflows.md",
)] + [CONTRACT] + [SPEC / name for name in (
    "spec.md", "acceptance.md", "plan.md", "tasks.md", "evidence.md", "handoff.md",
)]


class ConsumerDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.document = CONTRACT.read_text(encoding="utf-8")
        self.bash = "\n".join(re.findall(r"(?ms)^```bash\n(.*?)^```$", self.document))
        self.policy = json.loads(IDENTITIES.read_text())
        self.variables = {"INDEX_DIGEST": "sha256:" + "a" * 64}
        # Only the assignments used by these examples, never shell evaluation.
        for name in ("AWS_ACCOUNT_ID", "AWS_REGION", "REGISTRY", "IMAGE_REPOSITORY",
                     "SOURCE_REPO", "SIGNER_WORKFLOW", "CERT_IDENTITY", "OIDC_ISSUER",
                     "IMAGE_REF"):
            value = re.search(rf"(?m)^{name}=(.+)$", self.bash)[1]
            self.variables[name] = Template(shlex.split(value)[0]).substitute(self.variables)

    def command(self, prefix, variables=None):
        lines = self.bash.replace("\\\n", " ").splitlines()
        matches = [line for line in lines if line.startswith(prefix + " ")]
        self.assertEqual(len(matches), 1, prefix)
        return [Template(token).substitute(variables or self.variables)
                for token in shlex.split(matches[0].split(" > ")[0])]

    def test_local_links_in_consumer_docs_and_spec_exist(self):
        for path in DOCUMENTS:
            for target in link_targets(path.read_text(encoding="utf-8")):
                parsed = urlsplit(target)
                if parsed.scheme in ("https", "http", "mailto") or not parsed.path:
                    continue
                with self.subTest(document=path.relative_to(ROOT), target=target):
                    self.assertFalse(parsed.scheme or parsed.netloc)
                    destination = (path.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(destination.is_relative_to(ROOT))
                    self.assertTrue(destination.exists())

    def test_consumer_bash_examples_have_valid_syntax(self):
        self.assertTrue(self.bash)
        result = subprocess.run(["bash", "-n"], input=self.bash,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_documented_identity_matches_release_policy(self):
        repository = self.variables["SOURCE_REPO"]
        self.assertIn(repository, self.policy)
        for label, value in (
            ("Repository de origem", repository),
            ("Repository ID", self.policy[repository]["repository_id"]),
            ("Owner ID", self.policy[repository]["owner_id"]),
        ):
            self.assertIn(f"| {label} | `{value}` |", self.document)

    def test_architecture_docs_reference_the_current_shared_workflow_pin(self):
        pin = dependencies(ROOT)[0]["ref"]
        for name in ("RFC-013-Image-Base-Completa-com-Mermaid.md",
                     "docs/m09-m12-reusable-workflows.md"):
            with self.subTest(document=name):
                self.assertIn(pin, (ROOT / name).read_text(encoding="utf-8"))

    def test_signature_and_provenance_examples_match_promotion_verifier(self):
        repository, image = self.variables["SOURCE_REPO"], self.variables["IMAGE_REF"]
        expected = self.policy[repository]
        index = {"mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [
            {"platform": {"os": "linux", "architecture": arch}} for arch in ("amd64", "arm64")]}
        certificate = {"sourceRepositoryIdentifier": expected["repository_id"],
                       "sourceRepositoryOwnerIdentifier": expected["owner_id"],
                       "sourceRepositoryURI": f"https://github.com/{repository}",
                       "sourceRepositoryRef": "refs/heads/main"}
        proof = [{"verificationResult": {"signature": {"certificate": certificate}}}]
        outputs = [subprocess.CompletedProcess([], 0, stdout=json.dumps(value))
                   for value in (index, [{}], proof)]
        with tempfile.TemporaryDirectory() as directory, patch(
                "scripts.pipeline.release.verify_promotion.subprocess.run", side_effect=outputs) as run:
            verify_promotion(image, repository, Path(directory))
        self.assertEqual(self.command("cosign verify"), run.call_args_list[1].args[0])
        provenance = self.command("gh attestation verify")
        # The example makes the CLI's provenance predicate restriction explicit.
        offset = provenance.index("--predicate-type")
        self.assertEqual(provenance[offset + 1], "https://slsa.dev/provenance/v1")
        del provenance[offset:offset + 2]
        self.assertEqual(provenance, run.call_args_list[2].args[0])
        self.assertEqual(self.command("python3 -B -m"), [
            "python3", "-B", "-m", "scripts.pipeline.release.verify_promotion", image, repository])

    def test_sbom_example_matches_publisher_type_subject_and_verified_identity(self):
        image = self.variables["IMAGE_REF"]
        evidence = {"digest": self.variables["INDEX_DIGEST"], "sboms": [
            {"path": f"sbom-{name}.spdx.json", "subject": "sha256:" + digit * 64}
            for name, digit in (("index", "a"), ("amd64", "b"), ("arm64", "c"))]}
        run = Mock()
        with tempfile.TemporaryDirectory() as directory, patch(
                "scripts.pipeline.release.publish_sboms.verify", return_value=evidence):
            layout = Path(directory)
            (layout / "validated-index.json").write_text(json.dumps(evidence))
            records = publish(layout, image, layout / "publication.json", run=run)
        self.assertEqual(len(records), 3)
        for call, sbom in zip(run.call_args_list, evidence["sboms"]):
            self.assertEqual(call.args[0][-1], image.split("@")[0] + "@" + sbom["subject"])
        self.assertIn("VERIFIED_SIGNER=$(jq -er '.signer_repository' reports/verified-identity.json)",
                      self.bash)
        value = re.search(r"(?m)^SBOM_CERT_IDENTITY=(.+)$", self.bash)[1]
        publication = run.call_args_list[0].args[0]
        repository = self.variables["SOURCE_REPO"]
        for signer in [repository] + self.policy[repository]["previous_names"]:
            with self.subTest(signer=signer):
                variables = dict(self.variables, VERIFIED_SIGNER=signer)
                variables["SBOM_CERT_IDENTITY"] = Template(shlex.split(value)[0]).substitute(variables)
                identity = f"https://github.com/{signer}/.github/workflows/build-base-images.yml@refs/heads/main"
                self.assertEqual(self.command("cosign verify-attestation", variables), [
                    "cosign", "verify-attestation", "--certificate-identity", identity,
                    "--certificate-oidc-issuer", variables["OIDC_ISSUER"], "--type",
                    publication[publication.index("--type") + 1], publication[-1]])


if __name__ == "__main__":
    unittest.main()
