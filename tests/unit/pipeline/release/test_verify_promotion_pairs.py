"""Tests for pair discovery across a promote-stable.yml run's requested
frameworks (RFC-013/ADR-0005)."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.pipeline.release.verify_promotion_pairs import discover_pairs, main


def write_evidence(root, framework, attempt, tag, digest, skipped=False):
    directory = Path(root) / f'promotion-{framework}-{attempt}'
    directory.mkdir(parents=True)
    (directory / 'promotion-evidence.json').write_text(json.dumps({
        'repository': f'image-base-{framework}', 'tag': tag,
        'candidate_digest': digest, 'skipped': skipped,
    }))


class DiscoverPairsTests(unittest.TestCase):
    def test_pair_present_when_both_requested(self):
        self.assertEqual(discover_pairs(['go1-26', 'go1-26-dev']), ['go1-26'])

    def test_no_pair_when_dev_not_requested(self):
        self.assertEqual(discover_pairs(['go1-26']), [])

    def test_dev_only_framework_is_not_its_own_pair(self):
        self.assertEqual(discover_pairs(['go1-26-dev']), [])

    def test_framework_without_dev_variant_has_no_pair(self):
        self.assertEqual(discover_pairs(['python3-13']), [])

    def test_multiple_pairs_discovered(self):
        self.assertEqual(discover_pairs(['go1-26', 'go1-26-dev', 'java21', 'java21-dev']),
                         ['go1-26', 'java21'])


class MainIntegrationTests(unittest.TestCase):
    def run_main(self, frameworks, evidence_dir, attempt, json_output=None):
        argv = [json.dumps(frameworks), str(evidence_dir), str(attempt)]
        if json_output:
            argv += ['--json', str(json_output)]
        import sys
        old_argv = sys.argv
        sys.argv = ['verify_promotion_pairs.py'] + argv
        try:
            return main()
        finally:
            sys.argv = old_argv

    def test_no_pairs_requested_passes_trivially(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_main(['python3-13'], tmp, 1), 0)

    def test_matching_pair_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_evidence(tmp, 'go1-26', 1, '160926-0242-r111-a1', 'sha256:' + 'a' * 64)
            write_evidence(tmp, 'go1-26-dev', 1, '160926-0242-r111-a1', 'sha256:' + 'b' * 64)
            self.assertEqual(self.run_main(['go1-26', 'go1-26-dev'], tmp, 1), 0)

    def test_mismatched_pair_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_evidence(tmp, 'go1-26', 1, '160926-0242-r111-a1', 'sha256:' + 'a' * 64)
            write_evidence(tmp, 'go1-26-dev', 1, '160926-0300-r222-a1', 'sha256:' + 'b' * 64)
            self.assertEqual(self.run_main(['go1-26', 'go1-26-dev'], tmp, 1), 1)

    def test_missing_evidence_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_evidence(tmp, 'go1-26', 1, '160926-0242-r111-a1', 'sha256:' + 'a' * 64)
            # go1-26-dev evidence never written.
            self.assertEqual(self.run_main(['go1-26', 'go1-26-dev'], tmp, 1), 1)

    def test_json_output_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_evidence(tmp, 'go1-26', 1, '160926-0242-r111-a1', 'sha256:' + 'a' * 64)
            write_evidence(tmp, 'go1-26-dev', 1, '160926-0242-r111-a1', 'sha256:' + 'b' * 64)
            out = Path(tmp) / 'result.json'
            self.run_main(['go1-26', 'go1-26-dev'], tmp, 1, json_output=out)
            data = json.loads(out.read_text())
            self.assertEqual(len(data['pairs']), 1)
            self.assertEqual(data['failures'], [])


if __name__ == '__main__':
    unittest.main()
