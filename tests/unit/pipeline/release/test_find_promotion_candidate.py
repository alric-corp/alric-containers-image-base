import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.pipeline.release.find_promotion_candidate import (
    load_quarantined_digests, select_candidate)


NOW = datetime.datetime(2026, 9, 8, 9, tzinfo=datetime.timezone.utc)
INDEX = "application/vnd.oci.image.index.v1+json"
ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / 'scripts/pipeline/release/find_promotion_candidate.py'


def image(tag="070926-0000", hours=8, digest="sha256:build", media_type=INDEX):
    return {
        "imageTags": [tag],
        "imagePushedAt": (NOW - datetime.timedelta(hours=hours)).isoformat(),
        "imageDigest": digest,
        "imageManifestMediaType": media_type,
    }


class CandidateTests(unittest.TestCase):
    def select(self, details, soak=6):
        return select_candidate(details, soak, NOW)

    def test_empty_repository(self):
        self.assertIsNone(self.select([]))

    def test_label_uses_chronology_then_numeric_run_and_attempt(self):
        for tags, expected in (
            (["310826-2300", "010926-0100"], "010926-0100"),
            (["311225-2300", "010126-0100"], "010126-0100"),
            (["010926-0100-r9-a9", "010926-0100-r10-a2", "010926-0100-r10-a10"],
             "010926-0100-r10-a10"),
        ):
            candidate = image()
            candidate["imageTags"] = tags
            with self.subTest(tags=tags):
                selected = self.select([candidate])
                self.assertEqual(selected[1], expected)
                self.assertEqual(selected[2], candidate["imageDigest"])

    def test_run_and_attempt_tags_are_accepted(self):
        self.assertIsNotNone(self.select([image(tag="080926-0000-r12345-a2")]))
        for tag in ("080926-0000-r0-a1", "080926-0000-r123-a0", "080926-0000-r123"):
            with self.subTest(tag=tag):
                self.assertIsNone(self.select([image(tag=tag)]))

    def test_newest_eligible_build_wins_regardless_of_input_order(self):
        old = image(hours=12, digest="sha256:old")
        new = image(hours=8, digest="sha256:new")
        for details in ([old, new], [new, old]):
            self.assertEqual(self.select(details)[2], "sha256:new")

    def test_recent_build_does_not_hide_eligible_build(self):
        # Às 09h, o push das 03h20 ainda não completou seis horas.
        recent = image(hours=5 + 40 / 60, digest="sha256:recent")
        self.assertEqual(self.select([recent, image()])[2], "sha256:build")
        self.assertIsNone(self.select([recent]))

    def test_exact_soak_boundary_is_eligible(self):
        self.assertIsNotNone(self.select([image(hours=6)]))

    def test_zero_soak_still_rejects_future_timestamp(self):
        self.assertIsNotNone(self.select([image(hours=0)], soak=0))
        self.assertIsNone(self.select([image(hours=-1)], soak=0))

    def test_timezone_offset_is_respected(self):
        candidate = image()
        candidate["imagePushedAt"] = "2026-09-08T00:00:00-03:00"
        self.assertIsNotNone(self.select([candidate]))

    def test_invalid_soak_fails_closed(self):
        for soak in (-1, float("nan"), float("inf"), -float("inf")):
            with self.subTest(soak=soak), self.assertRaises(ValueError):
                self.select([image()], soak)

    def test_invalid_timestamp_fails_closed(self):
        for timestamp in ("invalid", "2026-09-08T00:00:00"):
            candidate = image()
            candidate["imagePushedAt"] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.select([candidate])

    def test_signature_and_non_build_tags_are_ignored(self):
        for tag in ("sha256-example.sig", "sha256-example.att", "latest", "stable",
                    "310226-1200", "080926-2500", "080926-0000-extra"):
            with self.subTest(tag=tag):
                self.assertIsNone(self.select([image(tag=tag)]))

    def test_only_multiarch_index_media_types_are_eligible(self):
        for media_type in (None, "application/vnd.oci.image.manifest.v1+json",
                           "application/vnd.oci.artifact.manifest.v1+json"):
            with self.subTest(media_type=media_type):
                self.assertIsNone(self.select([image(media_type=media_type)]))
        docker_index = "application/vnd.docker.distribution.manifest.list.v2+json"
        self.assertIsNotNone(self.select([image(media_type=docker_index)]))

    def test_untagged_images_are_ignored(self):
        candidate = image()
        del candidate["imageTags"]
        self.assertIsNone(self.select([candidate]))

    def test_stable_is_not_promoted_again_or_rolled_back(self):
        stable = image(hours=8, digest="sha256:stable")
        stable["imageTags"].append("stable")
        for old_hours in (8, 12):
            with self.subTest(old_hours=old_hours):
                self.assertIsNone(self.select([stable, image(hours=old_hours)]))
        self.assertEqual(self.select([stable, image(hours=7)])[2], "sha256:build")

    def test_stable_without_build_tag_still_prevents_rollback(self):
        stable = image(tag="stable", hours=8)
        self.assertIsNone(self.select([stable, image(hours=12, digest="sha256:old")]))

    def test_quarantined_digest_is_excluded_even_when_otherwise_eligible(self):
        newer = image(hours=7, digest="sha256:bad")
        older = image(hours=9, digest="sha256:good")
        self.assertEqual(
            select_candidate([newer, older], 6, NOW, frozenset({"sha256:bad"}))[2],
            "sha256:good",
        )
        # Sem nada elegível além do quarentenado, o resultado é skip (None).
        self.assertIsNone(select_candidate([newer], 6, NOW, frozenset({"sha256:bad"})))

    def test_quarantine_does_not_affect_unrelated_digests(self):
        candidate = image(hours=8, digest="sha256:build")
        self.assertEqual(
            select_candidate([candidate], 6, NOW, frozenset({"sha256:unrelated"}))[2],
            "sha256:build",
        )

    def test_load_quarantined_digests_missing_file_returns_empty(self):
        self.assertEqual(load_quarantined_digests("/nonexistent/path.json", "image-base-go1-26"),
                          frozenset())

    def test_load_quarantined_digests_filters_by_repo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quarantine.json"
            path.write_text(json.dumps({
                "image-base-go1-26": [{"digest": "sha256:aaa", "reason": "x"}],
                "image-base-java21": [{"digest": "sha256:bbb", "reason": "y"}],
            }))
            self.assertEqual(load_quarantined_digests(str(path), "image-base-go1-26"),
                              frozenset({"sha256:aaa"}))
            self.assertEqual(load_quarantined_digests(str(path), "image-base-python3-13"),
                              frozenset())

    def test_cli_quarantine_argument_excludes_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "images.json"
            output = Path(directory) / "output"
            quarantine = Path(directory) / "quarantine.json"
            details = [image(digest="sha256:build")]
            details[0]["imagePushedAt"] = "2020-01-01T00:00:00+00:00"
            source.write_text(json.dumps({"imageDetails": details}))
            quarantine.write_text(json.dumps({"test": [{"digest": "sha256:build"}]}))
            output.write_text("")
            evidence = Path(directory) / "reports" / "promotion-evidence.json"
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), str(source), "6",
                 "example.invalid", "test", str(quarantine), "--evidence", str(evidence)],
                env={**os.environ, "GITHUB_OUTPUT": str(output)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            # M11: o motivo do skip é output do gate, não só texto de log —
            # é ele que aparece na tabela por framework do run.
            emitted = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(emitted["skip"], "true")
            self.assertIn("quarentena", emitted["reason"])
            recorded = json.loads(evidence.read_text())
            self.assertFalse(recorded["promoted"])
            self.assertIn("quarentena", recorded["reason"])
            self.assertEqual(recorded["repository"], "test")
            self.assertIsNone(recorded["stable_digest"])
            self.assertIsNone(recorded["candidate_digest"])
            self.assertIsNone(recorded["stable_digest_observed"])
            self.assertEqual(recorded["read_back_status"], "not_run")

    def test_cli_github_output_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "images.json"
            output = Path(directory) / "output"
            evidence = Path(directory) / "promotion-evidence.json"
            for details, expected in (
                ([image()], {"skip": "false", "reason": "candidato elegível",
                             "tag": "070926-0000", "digest": "sha256:build",
                             "image": "example.invalid/test"}),
                ([], {"skip": "true",
                      "reason": "nenhum índice multi-arquitetura com tag de build "
                                "no repositório"}),
            ):
                # Fixture antiga para não depender do relógio do runner.
                if details:
                    details[0]["imagePushedAt"] = "2020-01-01T00:00:00+00:00"
                source.write_text(json.dumps({"imageDetails": details}))
                output.write_text("")
                result = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), str(source), "6",
                     "example.invalid", "test", "--evidence", str(evidence)],
                    env={**os.environ, "GITHUB_OUTPUT": str(output)},
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(dict(line.split("=", 1) for line in
                                      output.read_text().splitlines()), expected)
                recorded = json.loads(evidence.read_text())
                self.assertFalse(recorded["promoted"])
                self.assertEqual(recorded["candidate_digest"], expected.get("digest"))
                self.assertIsNone(recorded["stable_digest_observed"])
                self.assertEqual(recorded["read_back_status"], "not_run")


class QuarantineWiringTests(unittest.TestCase):
    def test_promotion_uses_the_versioned_quarantine_after_migration(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/promote-stable.yml').read_text())
        candidates = [step for job in workflow['jobs'].values()
                      for step in job.get('steps', []) if step.get('name') == 'Promote exact eligible release to HOM']
        self.assertEqual(len(candidates), 1)
        policy = 'policies/release/promotion-quarantine.json'
        from scripts.pipeline.release import lifecycle
        import inspect
        self.assertIn(policy, inspect.getsource(lifecycle.promote_hom))
        entries = json.loads((ROOT / policy).read_text())
        for repository, records in entries.items():
            if repository.startswith('_'):
                continue
            self.assertEqual(load_quarantined_digests(str(ROOT / policy), repository),
                             frozenset(record['digest'] for record in records))


if __name__ == "__main__":
    unittest.main()
