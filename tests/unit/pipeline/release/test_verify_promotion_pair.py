"""Tests for the runtime/dev promotion pair binding check (RFC-013/ADR-0005)."""

import unittest

from scripts.pipeline.release.verify_promotion_pair import run_identity, verify_pair


def evidence(repository, tag, digest, skipped=False):
    return {
        'repository': repository,
        'tag': tag,
        'candidate_digest': digest,
        'skipped': skipped,
    }


class RunIdentityTests(unittest.TestCase):
    def test_extracts_run_and_attempt(self):
        self.assertEqual(run_identity('160926-0242-r35060032353-a1'),
                         {'run_id': '35060032353', 'attempt': '1'})

    def test_missing_suffix_fails(self):
        with self.assertRaisesRegex(ValueError, 'não contém identificador'):
            run_identity('160926-0242')

    def test_none_fails(self):
        with self.assertRaisesRegex(ValueError, 'não contém identificador'):
            run_identity(None)


class VerifyPairTests(unittest.TestCase):
    def test_matching_pair_is_bound(self):
        runtime = evidence('image-base-go1-26', '160926-0242-r35060032353-a1', 'sha256:' + 'a' * 64)
        dev = evidence('image-base-go1-26-dev', '160926-0242-r35060032353-a1', 'sha256:' + 'b' * 64)
        result = verify_pair(runtime, dev)
        self.assertEqual(result['status'], 'PAIR_BOUND')
        self.assertEqual(result['source_run_id'], '35060032353')
        self.assertEqual(result['source_attempt'], '1')
        self.assertEqual(result['runtime_digest'], 'sha256:' + 'a' * 64)
        self.assertEqual(result['dev_digest'], 'sha256:' + 'b' * 64)

    def test_different_run_ids_rejected(self):
        runtime = evidence('image-base-go1-26', '160926-0242-r111-a1', 'sha256:' + 'a' * 64)
        dev = evidence('image-base-go1-26-dev', '160926-0300-r222-a1', 'sha256:' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'vêm de builds diferentes'):
            verify_pair(runtime, dev)

    def test_different_attempts_rejected(self):
        runtime = evidence('image-base-go1-26', '160926-0242-r111-a1', 'sha256:' + 'a' * 64)
        dev = evidence('image-base-go1-26-dev', '160926-0242-r111-a2', 'sha256:' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'vêm de builds diferentes'):
            verify_pair(runtime, dev)

    def test_runtime_skipped_rejected(self):
        runtime = evidence('image-base-go1-26', None, None, skipped=True)
        dev = evidence('image-base-go1-26-dev', '160926-0242-r111-a1', 'sha256:' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'runtime não tem candidato'):
            verify_pair(runtime, dev)

    def test_dev_skipped_rejected(self):
        runtime = evidence('image-base-go1-26', '160926-0242-r111-a1', 'sha256:' + 'a' * 64)
        dev = evidence('image-base-go1-26-dev', None, None, skipped=True)
        with self.assertRaisesRegex(ValueError, 'dev não tem candidato'):
            verify_pair(runtime, dev)

    def test_legacy_tag_without_run_suffix_rejected(self):
        # Formato anterior à identificação por run: não dá para provar
        # binding, então falha fechado em vez de assumir que bate.
        runtime = evidence('image-base-go1-26', '160926-0242', 'sha256:' + 'a' * 64)
        dev = evidence('image-base-go1-26-dev', '160926-0242', 'sha256:' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'não contém identificador'):
            verify_pair(runtime, dev)

    def test_missing_digest_rejected(self):
        runtime = {'repository': 'image-base-go1-26', 'tag': '160926-0242-r111-a1',
                  'skipped': False}
        dev = evidence('image-base-go1-26-dev', '160926-0242-r111-a1', 'sha256:' + 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'candidate_digest ausente'):
            verify_pair(runtime, dev)


if __name__ == '__main__':
    unittest.main()
