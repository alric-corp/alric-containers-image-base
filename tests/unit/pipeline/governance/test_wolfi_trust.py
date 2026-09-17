import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from scripts.pipeline.artifacts import build_image
from scripts.pipeline.governance import pin_inventory, wolfi_trust


class WolfiTrustTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'melange').mkdir()
        shutil.copytree(wolfi_trust.ROOT / 'melange/keys', self.root / 'melange/keys')
        # A regra de keyring da composição mora no contrato por fonte, então a
        # fixture espelha a composição real e a policy que ele lê.
        shutil.copytree(wolfi_trust.ROOT / 'distroless', self.root / 'distroless')
        shutil.copytree(wolfi_trust.ROOT / 'frameworks', self.root / 'frameworks')
        (self.root / 'policies/sources').mkdir(parents=True)
        for relative in ('melange/image-base-ca-certificates.yaml',
                         'policies/sources/package-sources.json'):
            shutil.copy(wolfi_trust.ROOT / relative, self.root / relative)
        self.key = self.root / wolfi_trust.KEY
        self.policy = self.root / wolfi_trust.POLICY

    def pin(self, data):
        policy = json.loads(self.policy.read_text())
        policy['expected_sha256'] = hashlib.sha256(data).hexdigest()
        self.policy.write_text(json.dumps(policy))

    def test_correct_reviewed_key_is_accepted_with_expected_and_actual_digest(self):
        entry = wolfi_trust.require_key(self.root)
        self.assertEqual(entry['expected_sha256'], entry['actual_sha256'])
        self.assertEqual(entry['actual_sha256'], hashlib.sha256(self.key.read_bytes()).hexdigest())
        self.assertEqual(entry['managers'], ['human-review'])
        self.assertEqual(pin_inventory.lint([entry]), [])
        self.assertEqual(wolfi_trust.config_errors(self.root), [])

    def test_modified_key_is_rejected_without_repin_even_if_pem_still_parses(self):
        self.key.write_bytes(self.key.read_bytes().replace(b'\n', b'\r\n'))
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            wolfi_trust.require_key(self.root)

    def test_missing_key_is_rejected(self):
        self.key.unlink()
        with self.assertRaisesRegex(ValueError, 'invalid or missing key'):
            wolfi_trust.require_key(self.root)

    def test_wrong_expected_fingerprint_is_rejected(self):
        self.pin(b'wrong fingerprint')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            wolfi_trust.require_key(self.root)

    def test_missing_policy_is_rejected(self):
        self.policy.unlink()
        with self.assertRaisesRegex(ValueError, 'invalid or missing policy'):
            wolfi_trust.require_key(self.root)

    def test_invalid_format_is_rejected_even_if_fingerprint_is_updated(self):
        for data in (b'not a public key\n',
                     b'-----BEGIN PUBLIC KEY-----\nYmFk\n-----END PUBLIC KEY-----\n',
                     self.key.read_bytes() + self.key.read_bytes()):
            with self.subTest(data=data[:30]):
                self.key.write_bytes(data)
                self.pin(data)
                with self.assertRaisesRegex(ValueError, 'invalid or missing key'):
                    wolfi_trust.require_key(self.root)

    def test_another_valid_rsa_key_is_rejected(self):
        private = self.root / 'fixture-private.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:2048', '-out', str(private)],
                       check=True, capture_output=True, timeout=20)
        subprocess.run(['openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(self.key)],
                       check=True, capture_output=True, timeout=10)
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            wolfi_trust.require_key(self.root)

    def test_symlink_cannot_replace_versioned_regular_key(self):
        target = self.root / 'key.pub'
        self.key.rename(target)
        self.key.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'not a symlink'):
            wolfi_trust.require_key(self.root)

    def test_build_rejects_missing_key_before_lock_replay_or_any_command(self):
        (self.root / 'frameworks/example.yaml').write_text('contents: {}\n')
        self.key.unlink()
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.root)
        with patch.object(build_image, 'command') as command, \
                patch.object(build_image.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'invalid or missing key'):
                build_image.build('example', 'example.oci', lockfile='replay.lock.json')
            command.assert_not_called()
            run.assert_not_called()
            self.assertFalse((self.root / 'example.oci').exists())

    def test_remote_keyring_reintroduction_is_rejected_in_both_configs(self):
        for relative, local in [('distroless/sources/wolfi.yaml', str(wolfi_trust.KEY)),
                                ('melange/image-base-ca-certificates.yaml', 'keys/wolfi-signing.rsa.pub')]:
            with self.subTest(config=relative):
                path = self.root / relative
                original = path.read_text()
                path.write_text(original.replace(local, 'https://packages.wolfi.dev/os/wolfi-signing.rsa.pub'))
                self.assertTrue(wolfi_trust.config_errors(self.root))
                path.write_text(original)

    def test_remote_key_cannot_appear_in_new_nested_or_inline_recipe(self):
        path = self.root / 'melange/additional.yml'
        for text in (
            'environment: {contents: {keyring: [https://packages.wolfi.dev/os/new.rsa.pub]}}',
            'test: {environment: {contents: {keyring: [https://other.example/key.pub]}}}',
        ):
            with self.subTest(text=text):
                path.write_text(text)
                self.assertTrue(wolfi_trust.config_errors(self.root))

    def test_missing_keyring_or_extra_local_key_is_rejected(self):
        path = self.root / 'distroless/sources/wolfi.yaml'
        for keyring in (None, [], [str(wolfi_trust.KEY), 'other-key.pub']):
            with self.subTest(keyring=keyring):
                path.write_text(yaml.safe_dump(
                    {'include': 'distroless/image-base.yaml',
                     'contents': {'repositories': ['https://packages.wolfi.dev/os'],
                                  'keyring': keyring}}))
                self.assertTrue(wolfi_trust.config_errors(self.root))

    def test_monitor_reports_same_divergent_and_unavailable_without_writes(self):
        entry = wolfi_trust.require_key(self.root)
        initial = (self.key.read_bytes(), self.policy.read_bytes())
        same = wolfi_trust.upstream_status(entry, lambda url: initial[0])
        different = wolfi_trust.upstream_status(entry, lambda url: b'new remote key')

        def unavailable(url):
            raise OSError('endpoint unavailable')

        missing = wolfi_trust.upstream_status(entry, unavailable)
        self.assertEqual([item['remote_status'] for item in (same, different, missing)],
                         ['same', 'divergent', 'unavailable'])
        self.assertEqual([item['available'] for item in (same, different, missing)], [True, False, False])
        self.assertEqual((self.key.read_bytes(), self.policy.read_bytes()), initial)
        # A failed remote observation cannot change the subsequent offline decision.
        self.assertEqual(wolfi_trust.require_key(self.root)['errors'], [])
        self.assertIn('divergent', pin_inventory.render([different]))

    def test_monitor_does_not_fetch_when_local_trust_is_invalid(self):
        self.key.unlink()
        with patch.object(wolfi_trust, 'urlopen') as remote:
            entry = wolfi_trust.upstream_status(wolfi_trust.local_pin(self.root))
        remote.assert_not_called()
        self.assertFalse(entry['available'])
        self.assertEqual(entry['remote_status'], 'local-invalid')

    def test_trust_cli_is_offline_and_failure_returns_nonzero(self):
        with patch.object(pin_inventory, 'ROOT', self.root), \
                patch('sys.argv', ['pin_inventory', 'trust']), \
                patch('builtins.print'), patch.object(wolfi_trust, 'urlopen') as remote:
            self.assertEqual(pin_inventory.main(), 0)
            self.key.unlink()
            self.assertEqual(pin_inventory.main(), 1)
        remote.assert_not_called()


class RepositoryWiringTests(unittest.TestCase):
    def test_all_configs_use_local_key_and_public_key_is_not_gitignored(self):
        self.assertEqual(wolfi_trust.config_errors(), [])
        result = subprocess.run(['git', 'check-ignore', str(wolfi_trust.KEY)],
                                cwd=wolfi_trust.ROOT, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)

    def test_both_ci_build_paths_require_offline_trust_before_reusable(self):
        workflow = yaml.safe_load((wolfi_trust.ROOT / '.github/workflows/validate-base-images.yml').read_text())
        for job in ('validate', 'image-trust'):
            self.assertEqual(workflow['jobs'][job]['needs'], 'wolfi-trust')
        commands = [step.get('run', '') for step in workflow['jobs']['wolfi-trust']['steps']]
        self.assertTrue(any('pin_inventory trust' in command for command in commands))


if __name__ == '__main__':
    unittest.main()
