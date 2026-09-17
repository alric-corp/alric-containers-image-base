import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.runtime import runtime_images as runtime


class RuntimeContractTests(unittest.TestCase):
    def test_unsupported_framework_fails_explicitly(self):
        for framework in ('unsupported-runtime', 'nodejs999', '../nodejs24', 'nodejs24;id'):
            with self.subTest(framework=framework), self.assertRaises(ValueError):
                runtime.runtime(framework)

    def test_native_and_emulated_are_distinct(self):
        self.assertEqual(runtime.execution_mode('aarch64', 'arm64'), 'native')
        self.assertEqual(runtime.execution_mode('aarch64', 'amd64'), 'emulated')
        self.assertEqual(runtime.execution_mode('x86_64', 'amd64'), 'native')
        with self.assertRaises(ValueError):
            runtime.execution_mode('unknown', 'amd64')

    def test_missing_checks_and_root_are_rejected(self):
        result = dict(uid=10000, gid=10000, readonly=True, tmpfs=True, writable_dirs=True,
                      timezone=True, bundle_parse=True, tls_trusted=True, tls_untrusted_rejected=True)
        self.assertEqual(runtime.validate_result(json.dumps(result)), result)
        for key in result:
            changed = dict(result)
            changed[key] = 0 if key in ('uid', 'gid') else False
            with self.subTest(key=key), self.assertRaises(ValueError):
                runtime.validate_result(json.dumps(changed))

    def test_invalid_oci_overwrites_stale_success_for_both_architectures(self):
        with tempfile.TemporaryDirectory() as temporary:
            reports = Path(temporary)
            for arch in ('amd64', 'arm64'):
                (reports / f'runtime-nodejs24-{arch}.json').write_text('{"status":"passed"}')
            with patch.object(runtime, 'verify', side_effect=ValueError('tampered blob')), \
                    patch.object(runtime, 'command') as command:
                self.assertEqual(runtime.run('/missing', 'nodejs24', reports), 1)
            command.assert_not_called()
            for path in reports.glob('*.json'):
                result = json.loads(path.read_text())
                self.assertEqual(result['status'], 'failed')
                self.assertIn('tampered blob', result['error'])

    def test_one_platform_failure_does_not_skip_other_platform(self):
        from contextlib import nullcontext
        verified = {'digest': 'index', 'platforms': {'linux/amd64': 'amd', 'linux/arm64': 'arm'}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'validated-index.json').write_text(json.dumps(verified))
            with patch.object(runtime, 'verify', return_value=verified), \
                    patch.object(runtime, 'command', return_value='aarch64'), \
                    patch.object(runtime, 'tls_server', side_effect=lambda *_: nullcontext(('url', 'ca'))), \
                    patch.object(runtime, 'run_platform', side_effect=[RuntimeError('bad TLS'), {'ok': True}]) as run:
                self.assertEqual(runtime.run(directory, 'nodejs24', directory), 1)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(json.loads((directory / 'runtime-nodejs24-amd64.json').read_text())['status'], 'failed')
            self.assertEqual(json.loads((directory / 'runtime-nodejs24-arm64.json').read_text())['status'], 'passed')

    def test_compiled_contract_requires_the_dev_pair(self):
        for framework in ('go1-25', 'go1-26', 'java21', 'java25', 'dotnet10'):
            with self.subTest(framework=framework):
                directory, dev, toolchain = runtime.project(framework)
                self.assertEqual(dev, f'{framework}-dev')
                self.assertTrue((directory / 'Dockerfile').is_file())
                self.assertTrue(toolchain)

    def test_contract_kind_and_expected_version_follow_the_catalog(self):
        self.assertEqual(runtime.supported('nodejs24'), 'interpreted')
        self.assertEqual(runtime.supported('go1-26'), 'compiled')
        self.assertEqual(runtime.expected_version('nodejs24-dev'), '24')
        self.assertEqual(runtime.expected_version('python3-14'), '3.14')
        self.assertEqual(runtime.expected_version('go1-26'), '1.26')
        self.assertEqual(runtime.expected_version('java21'), '21')
        self.assertEqual(runtime.expected_version('dotnet10'), '10')
        # Um framework fora do catálogo não vira contrato por parecer com um.
        with self.assertRaises(ValueError):
            runtime.expected_version('go1-99')
        for framework in ('go1-25', 'go1-26', 'java21', 'java25', 'dotnet10', 'nodejs22',
                          'python3-13'):
            self.assertIn(framework, runtime.contracts())
        for framework in ('unsupported-runtime', 'go1-25-dev', 'java25-dev'):
            self.assertNotIn(framework, runtime.contracts())

    def test_compiled_contract_without_dev_layout_is_rejected_before_docker(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(runtime, 'command') as command:
            with self.assertRaises(ValueError):
                runtime.run(temporary, 'go1-26', temporary)
            command.assert_not_called()

    def test_missing_runtime_report_never_authorises_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            reports = Path(temporary)
            self.assertFalse(runtime.gate(reports, 'nodejs24')['passed'])
            for arch in ('amd64', 'arm64'):
                (reports / f'runtime-nodejs24-{arch}.json').write_text(
                    json.dumps({'status': 'passed', 'execution': 'native'}))
            # Status-only JSON cannot authorize publication without actual
            # OCI identity and same-run provenance (P1-02).
            self.assertFalse(runtime.gate(reports, 'nodejs24')['passed'])
            (reports / 'runtime-nodejs24-arm64.json').write_text(
                json.dumps({'status': 'failed', 'error': 'bad TLS'}))
            result = runtime.gate(reports, 'nodejs24')
            self.assertFalse(result['passed'])
            self.assertIn('validated OCI', result['error'])

    def test_compiled_run_builds_the_multi_stage_image_for_both_platforms(self):
        from contextlib import nullcontext
        verified = {'digest': 'index', 'platforms': {'linux/amd64': 'amd', 'linux/arm64': 'arm'}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            dev = directory / 'dev'
            dev.mkdir()
            for target in (directory, dev):
                (target / 'validated-index.json').write_text(json.dumps(verified))
            with patch.object(runtime, 'verify', return_value=verified), \
                    patch.object(runtime, 'command', return_value='aarch64'), \
                    patch.dict('os.environ', {'GITHUB_RUN_ID': '41', 'GITHUB_RUN_ATTEMPT': '2',
                                             'GITHUB_REPOSITORY': 'alric-corp/image-base',
                                             'GITHUB_SHA': 'a' * 40}), \
                    patch.object(runtime, 'tls_server', side_effect=lambda *_: nullcontext(('url', 'ca'))), \
                    patch.object(runtime, 'run_platform', return_value={'ok': True}) as platform:
                self.assertEqual(runtime.run(directory, 'go1-26', directory, dev), 0)
            self.assertEqual(platform.call_count, 2)
            for call in platform.call_args_list:
                self.assertEqual(call.args[0], (directory.resolve(), dev.resolve()))
            report = json.loads((directory / 'runtime-go1-26-amd64.json').read_text())
            self.assertEqual(report['contract'], 'compiled')
            self.assertEqual(report['dev_framework'], 'go1-26-dev')
            self.assertEqual(report['dev_index_digest'], 'index')
            self.assertEqual(report['run_id'], '41')
            self.assertEqual(report['run_attempt'], '2')
            self.assertEqual(report['repository'], 'alric-corp/image-base')
            self.assertEqual(report['revision'], 'a' * 40)
            self.assertEqual(report['execution'], 'emulated')
            self.assertEqual(
                json.loads((directory / 'runtime-go1-26-arm64.json').read_text())['execution'],
                'native')

    def test_contract_run_is_non_root_read_only_with_explicit_writable_dirs(self):
        args = runtime.contract_run('name', 'arm64', 'nodejs24', ('https://t/', 'https://u/'), '/ca.pem')
        self.assertIn('--read-only', args)
        self.assertNotIn('--user', args)
        self.assertNotIn('--privileged', args)
        self.assertIn('--cap-drop', args)
        for directory in runtime.WRITABLE_DIRS:
            self.assertIn(f'{directory}:{runtime.TMPFS}', args)
        self.assertIn('WRITABLE_DIRS=/tmp,/app/work', args)
        self.assertIn('EXPECTED_RUNTIME_VERSION=24', args)
        self.assertIn('READONLY_PATH=/app/runtime-test-write', args)
        # A chave privada da CA de teste nunca entra no candidato: só o PEM
        # público, e somente leitura.
        self.assertIn('/ca.pem:/test-ca.pem:ro', args)

    def test_config_digest_comes_from_archive_bytes(self):
        import hashlib
        config = b'{"architecture":"arm64","rootfs":{"diff_ids":["sha256:test"]}}'
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'docker.tar'
            with tarfile.open(archive, 'w') as output:
                for name, content in [('manifest.json', b'[{"Config":"config.json"}]'),
                                      ('config.json', config)]:
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    output.addfile(info, io.BytesIO(content))
            self.assertEqual(runtime.archive_config(archive), 'sha256:' + hashlib.sha256(config).hexdigest())


if __name__ == '__main__':
    unittest.main()
