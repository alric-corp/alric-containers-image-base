"""Regression tests for scripts/verify-image.sh: the actual shell script
runs against stubbed aws/docker/cosign/gh binaries -- no network, no real
AWS/GitHub credentials. Guard-rail cases run with no stubs at all, since
they must fail before any external command executes."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

from tests.helpers.subprocess_env import bash_command

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/verify-image.sh'
GOOD_DIGEST = 'sha256:' + 'a' * 64
GOOD_ACCOUNT = '712107929769'

STUB_AWS = '''#!/bin/bash
set -euo pipefail
if [[ "$1" == "ecr" && "$2" == "get-login-password" ]]; then
  echo "fake-password"
  exit 0
fi
if [[ "$1" == "ecr" && "$2" == "describe-images" ]]; then
  echo "${VERIFY_STUB_DIGEST:-%(digest)s}"
  exit 0
fi
echo "unexpected aws invocation: $*" >&2
exit 9
''' % {'digest': GOOD_DIGEST}

STUB_DOCKER = '''#!/bin/bash
set -euo pipefail
if [[ "$1" == "login" ]]; then
  cat >/dev/null
  exit 0
fi
echo "unexpected docker invocation: $*" >&2
exit 9
'''

STUB_COSIGN = '''#!/bin/bash
set -euo pipefail
if [[ "$1" == "verify" ]]; then
  exit "${VERIFY_STUB_COSIGN_VERIFY_EXIT:-0}"
fi
if [[ "$1" == "verify-attestation" ]]; then
  exit "${VERIFY_STUB_COSIGN_ATTEST_EXIT:-0}"
fi
echo "unexpected cosign invocation: $*" >&2
exit 9
'''

STUB_GH = '''#!/bin/bash
set -euo pipefail
if [[ "$1" == "attestation" && "$2" == "verify" ]]; then
  exit "${VERIFY_STUB_GH_EXIT:-0}"
fi
echo "unexpected gh invocation: $*" >&2
exit 9
'''


def _write_stub(directory: Path, name: str, content: str) -> None:
    path = directory / name
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class VerifyImageGuardRailTests(unittest.TestCase):
    """These must fail before touching aws/docker/cosign/gh -- no stubs,
    real PATH, so a bug that reaches a real network call fails loudly."""

    def _run(self, *args):
        return subprocess.run(bash_command(str(SCRIPT), *args),
                               capture_output=True, text=True, encoding='utf-8')

    def test_missing_account_rejected(self):
        result = self._run('go1-26', GOOD_DIGEST)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--account', result.stderr)

    def test_invalid_framework_name_rejected(self):
        result = self._run('Go_1.26', GOOD_DIGEST, '--account', GOOD_ACCOUNT)
        self.assertEqual(result.returncode, 2)
        self.assertIn('framework inválido', result.stderr)

    def test_invalid_account_rejected(self):
        result = self._run('go1-26', GOOD_DIGEST, '--account', '123')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--account', result.stderr)

    def test_missing_arguments_show_usage(self):
        result = self._run('go1-26')
        self.assertEqual(result.returncode, 2)
        self.assertIn('Uso:', result.stderr)


class VerifyImageStubbedRunTests(unittest.TestCase):
    """Full control-flow with every external dependency stubbed."""

    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix='verify-image-tests-')
        cls.addClassCleanup(cls.storage.cleanup)
        stub_bin = Path(cls.storage.name) / 'bin'
        stub_bin.mkdir()
        _write_stub(stub_bin, 'aws', STUB_AWS)
        _write_stub(stub_bin, 'docker', STUB_DOCKER)
        _write_stub(stub_bin, 'cosign', STUB_COSIGN)
        _write_stub(stub_bin, 'gh', STUB_GH)
        cls.stub_bin = stub_bin

    def _run(self, *args, env_overrides=None):
        env = dict(os.environ)
        env['PATH'] = str(self.stub_bin) + os.pathsep + env['PATH']
        env.update(env_overrides or {})
        return subprocess.run(bash_command(str(SCRIPT), *args),
                               capture_output=True, text=True, encoding='utf-8', env=env)

    def test_digest_input_skips_tag_resolution_and_passes(self):
        result = self._run('go1-26', GOOD_DIGEST, '--account', GOOD_ACCOUNT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RESULTADO: PASS', result.stdout)
        self.assertIn(GOOD_DIGEST, result.stdout)

    def test_tag_input_resolves_digest_via_ecr(self):
        result = self._run('go1-26', '160926-0054-r1-a1', '--account', GOOD_ACCOUNT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"-> {GOOD_DIGEST}", result.stdout)

    def test_ecr_resolution_failure_is_rejected(self):
        result = self._run('go1-26', 'no-such-tag', '--account', GOOD_ACCOUNT,
                            env_overrides={'VERIFY_STUB_DIGEST': 'None'})
        self.assertEqual(result.returncode, 4)
        self.assertIn("não resolveu", result.stderr)

    def test_signature_failure_still_runs_all_checks_and_reports_fail(self):
        result = self._run('go1-26', GOOD_DIGEST, '--account', GOOD_ACCOUNT,
                            env_overrides={'VERIFY_STUB_COSIGN_VERIFY_EXIT': '1'})
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL: assinatura', result.stdout)
        # As outras duas verificações continuam rodando (sem early-exit).
        self.assertIn('PASS: attestation SBOM', result.stdout)
        self.assertIn('PASS: provenance', result.stdout)
        self.assertIn('RESULTADO: FAIL', result.stdout)
        self.assertIn('signature', result.stdout.split('RESULTADO: FAIL')[-1])

    def test_provenance_failure_reported_independently(self):
        result = self._run('go1-26', GOOD_DIGEST, '--account', GOOD_ACCOUNT,
                            env_overrides={'VERIFY_STUB_GH_EXIT': '1'})
        self.assertEqual(result.returncode, 1)
        self.assertIn('PASS: assinatura', result.stdout)
        self.assertIn('PASS: attestation SBOM', result.stdout)
        self.assertIn('FAIL: provenance', result.stdout)


if __name__ == '__main__':
    unittest.main()
