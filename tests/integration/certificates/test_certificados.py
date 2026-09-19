"""Regression tests for the actual shell script; downloads are always local."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.helpers.subprocess_env import bash_command

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/certificates/certificados.sh'
FILES = ('ca_bundle.crt', 'cacorp.cer', 'cloud-s0653.cer',
         'corp-r0650.cer', 'corp-s0143.cer', 'mozilla.crt')


class CertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix='certificate-tests-')
        cls.addClassCleanup(cls.storage.cleanup)
        cls.root = Path(cls.storage.name)
        cls.bin = cls.root / 'bin'
        cls.bin.mkdir()
        cls.source = cls.root / 'fixtures'
        cls.source.mkdir()
        for tool in ('bash', 'openssl', 'jq', 'sha256sum', 'cp'):
            if not shutil.which(tool):
                raise RuntimeError(f'Missing test dependency: {tool}')
        date = shutil.which('gdate') or shutil.which('date')
        subprocess.run([date, '-d', '1970-01-01T00:00:00Z', '+%s'],
                       check=True, capture_output=True)
        (cls.bin / 'date').symlink_to(date)
        # Use the same interpreter as unittest; no AWS SDK or network required.
        downloader = f'#!{sys.executable}\n' + '''import os
from pathlib import Path
import shutil
import sys
args = sys.argv
if Path(args[0]).name == 'aws':
    assert args[1:3] == ['s3', 'cp'], args
    filename = args[3].rsplit('/', 1)[-1]
    filename = 'corp-s0143.cer' if filename == 'Corp-S0143.cer' else filename
    destination = args[4]
else:
    assert 'https://curl.se/ca/cacert.pem' in args, args
    filename = 'mozilla.crt'
    destination = args[args.index('-o') + 1]
source = Path(os.environ['CERT_TEST_FIXTURES']) / filename
if not source.is_file():
    print('Simulated download failure: ' + filename, file=sys.stderr)
    sys.exit(1)
shutil.copyfile(source, destination)
'''
        for name in ('aws', 'curl'):
            path = cls.bin / name
            path.write_text(downloader)
            path.chmod(0o755)
        cp = cls.bin / 'cp'
        cp.write_text(f'#!{sys.executable}\n' + '''import os
from pathlib import Path
import subprocess
import sys
if Path(sys.argv[-1]).name == os.environ.get('CERT_TEST_FAIL_COPY'):
    print('Simulated metadata write failure', file=sys.stderr)
    sys.exit(1)
sys.exit(subprocess.call([os.environ['CERT_TEST_REAL_CP'], *sys.argv[1:]]))
''')
        cp.chmod(0o755)
        cls.env = {**os.environ, 'PATH': str(cls.bin) + os.pathsep + os.environ['PATH'],
                   'CERT_TEST_FIXTURES': str(cls.source),
                   'CERT_TEST_REAL_CP': shutil.which('cp'),
                   'CERTIFICADOS_BUCKET_CLOUDSEC': 'fixture-cloudsec',
                   'CERTIFICADOS_BUCKET_CACERTCORP': 'fixture-corp', 'LC_ALL': 'C'}
        for i, name in enumerate(FILES):
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'ec',
                '-pkeyopt', 'ec_paramgen_curve:P-256', '-nodes', '-days', '365',
                '-subj', f'/O=TEST ONLY/CN=fixture-{i}',
                '-addext', 'basicConstraints=critical,CA:TRUE',
                '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
                '-keyout', str(cls.root / 'temporary.key'),
                '-out', str(cls.source / name),
            ], check=True, capture_output=True)
        # Multi-certificate bundle with comments between certificates.
        mozilla = cls.source / 'mozilla.crt'
        mozilla.write_bytes(b'# Synthetic public bundle\n' + mozilla.read_bytes() +
                            b'\n# Second certificate\n' +
                            (cls.source / 'ca_bundle.crt').read_bytes())
        cls.baseline = cls.root / 'baseline.sha256'
        result = subprocess.run(bash_command(str(SCRIPT), '--pin', '--lockfile',
                                 str(cls.baseline)), env=cls.env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='case-', dir=self.root)
        self.addCleanup(temp.cleanup)
        self.case = Path(temp.name)
        self.fixtures = self.case / 'fixtures'
        shutil.copytree(self.source, self.fixtures)
        self.lock = self.case / 'certificados.sha256'
        self.meta = self.case / 'certificados.metadata.txt'
        shutil.copyfile(self.baseline, self.lock)
        shutil.copyfile(self.root / 'baseline.metadata.txt', self.meta)
        self.output = self.case / 'output'
        self.env = {**type(self).env, 'CERT_TEST_FIXTURES': str(self.fixtures)}

    def run_script(self, *, pin=False, relative=False):
        args = bash_command(str(SCRIPT), '--pin' if pin else str(self.output),
                             '--lockfile', self.lock.name if relative else str(self.lock))
        return subprocess.run(args, cwd=self.case, env=self.env,
                              capture_output=True, text=True, timeout=30)

    def assert_blocked(self, result, code=None):
        self.assertNotEqual(result.returncode, 0, result.stderr)
        if code is not None:
            self.assertEqual(result.returncode, code, result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(result.stdout, '')

    def rotate(self):
        shutil.copyfile(self.fixtures / 'cloud-s0653.cer', self.fixtures / 'cacorp.cer')

    def rewrite_hashes(self):
        self.lock.write_text(''.join(
            hashlib.sha256((self.fixtures / name).read_bytes()).hexdigest() +
            '  ' + name + '\n' for name in FILES))

    def assert_bundle_readable(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        for field, count in (('ca_bundle_interna', 5), ('ca_bundle_externa', 7)):
            bundle = self.output / (field + '.crt')
            self.assertEqual(document[field], bundle.read_text())
            parsed = subprocess.run(['openssl', 'crl2pkcs7', '-nocrl', '-certfile', str(bundle)],
                                    capture_output=True)
            self.assertEqual(parsed.returncode, 0, parsed.stderr)
            certs = subprocess.run(['openssl', 'pkcs7', '-print_certs'], input=parsed.stdout,
                                   capture_output=True)
            self.assertEqual(certs.returncode, 0, certs.stderr)
            self.assertEqual(certs.stdout.count(b'-----BEGIN CERTIFICATE-----'), count)

    def test_baseline_and_pin_are_repeatable(self):
        before = (self.lock.read_bytes(), self.meta.read_bytes())
        self.assert_bundle_readable(self.run_script())
        self.assertEqual(self.run_script(pin=True).returncode, 0)
        self.assertEqual(before, (self.lock.read_bytes(), self.meta.read_bytes()))

    def test_relative_lockfile(self):
        self.assert_bundle_readable(self.run_script(relative=True))

    def test_missing_lockfile(self):
        self.lock.unlink()
        self.assert_blocked(self.run_script(), 3)

    def test_empty_lockfile(self):
        self.lock.write_text('')
        self.assert_blocked(self.run_script(), 3)

    def test_missing_entry(self):
        self.lock.write_text('\n'.join(self.lock.read_text().splitlines()[:-1]) + '\n')
        self.assert_blocked(self.run_script(), 3)

    def test_duplicate_entry(self):
        self.lock.write_text(self.lock.read_text() + self.lock.read_text().splitlines()[0] + '\n')
        self.assert_blocked(self.run_script(), 3)

    def test_rotation_then_explicit_pin(self):
        self.rotate()
        self.assert_blocked(self.run_script(), 1)
        self.assertEqual(self.run_script(pin=True).returncode, 0)
        self.assert_bundle_readable(self.run_script())

    def test_malformed_hash_including_final_line_without_newline(self):
        for filename, newline in (('cacorp.cer', True), ('mozilla.crt', False)):
            with self.subTest(filename=filename, newline=newline):
                self.rewrite_hashes()
                lines = ['INVALID  ' + filename if line.endswith('  ' + filename) else line
                         for line in self.lock.read_text().splitlines()]
                self.lock.write_text('\n'.join(lines) + ('\n' if newline else ''))
                self.assert_blocked(self.run_script(), 3)

    def test_truncated_tail(self):
        p = self.fixtures / 'cacorp.cer'
        p.write_bytes(p.read_bytes() + b'-----BEGIN CERTIFICATE-----\n')
        self.rewrite_hashes()
        self.assert_blocked(self.run_script(), 1)

    def test_truncated_tail_without_newline(self):
        p = self.fixtures / 'cacorp.cer'
        p.write_bytes(p.read_bytes() + b'-----BEGIN CERTIFICATE-----')
        self.rewrite_hashes()
        self.assert_blocked(self.run_script(), 1)

    def test_valid_pem_without_final_newline(self):
        p = self.fixtures / 'cacorp.cer'
        p.write_bytes(p.read_bytes().rstrip(b'\n'))
        self.rewrite_hashes()
        self.assert_bundle_readable(self.run_script())

    def test_tampered_metadata(self):
        self.meta.write_text('Unrelated authority\n')
        self.assert_blocked(self.run_script(), 1)

    def test_metadata_write_failure_preserves_lockfile(self):
        before = self.lock.read_bytes()
        self.rotate()
        self.env['CERT_TEST_FAIL_COPY'] = self.meta.name
        self.assert_blocked(self.run_script(pin=True), 1)
        self.assertEqual(self.lock.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
