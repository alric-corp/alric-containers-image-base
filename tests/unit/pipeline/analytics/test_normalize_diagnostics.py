"""Normalizer CLI diagnostics: stable codes, legacy text/exit codes, no tracebacks or secrets."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics import normalize
from scripts.pipeline.analytics.normalize import main, prepare, read_completed
from scripts.pipeline.analytics.spdx import canonical
from tests.unit.pipeline.analytics.fixture_support import mutate_spdx, synthetic

ROOT = Path(__file__).resolve().parents[4]
SECRET = 'SECRET-d2-normalizer-canary'


class NormalizeDiagnosticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='sbom-normalize-diagnostics-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.context = synthetic(self.root / 'input')
        self.input = self.root / 'input/context.json'
        self.output = self.root / 'output'
        self.report = self.root / 'reports/normalize.json'

    def run_cli(self, context=None, *extra, report=True):
        if context is not None:
            self.input.write_bytes(canonical(context) if isinstance(context, dict) else context)
        argv = ['--input', str(self.input), '--output', str(self.output)] + list(extra)
        if report:
            argv += ['--report', str(self.report)]
        with patch('sys.stdout', new_callable=io.StringIO) as out, patch('sys.stderr', new_callable=io.StringIO) as err:
            status = main(argv)
        diagnostic = json.loads(self.report.read_bytes()) if report and self.report.exists() else None
        return status, out.getvalue(), err.getvalue(), diagnostic

    def assert_failure(self, result, stage, code, category):
        status, out, err, diagnostic = result
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        self.assertTrue(err.startswith('SBOM analytics failed: '), err)
        self.assertEqual((diagnostic['status'], diagnostic['stage'], diagnostic['code'], diagnostic['category']),
                         ('ERROR', stage, code, category))
        self.assertEqual((diagnostic['diagnostic_version'], diagnostic['exit_code'], diagnostic['complete'],
                          diagnostic['publication_authority']), (1, 1, False, False))
        self.assertNotIn('Traceback', err + json.dumps(diagnostic))
        self.assertFalse((self.output / 'batches').exists() and any((self.output / 'batches').iterdir()))
        return diagnostic

    def test_success_keeps_stdout_contract_and_reports_batch(self):
        status, out, err, diagnostic = self.run_cli(self.context)
        self.assertEqual((status, err), (0, ''))
        result = json.loads(out)
        self.assertEqual(set(result), {'batch_id', 'path', 'status'})
        self.assertEqual((diagnostic['status'], diagnostic['code'], diagnostic['batch_id'], diagnostic['complete']),
                         ('SUCCESS', 'BATCH_CREATED', result['batch_id'], True))
        self.assertEqual(self.run_cli()[3]['code'], 'BATCH_ALREADY_PRESENT_IDENTICAL')
        self.assertEqual(read_completed(result['path'])['observations'][0]['framework'], 'python-3.14')

    def test_without_report_the_legacy_cli_is_unchanged(self):
        status, out, err, _ = self.run_cli(self.context, report=False)
        self.assertEqual((status, err), (0, ''))
        self.assertEqual(json.loads(out)['status'], 'CREATED')
        self.context['images'][0]['documents'].pop()
        status, out, err, _ = self.run_cli(self.context, report=False)
        self.assertEqual((status, out), (1, ''))
        self.assertEqual(err, 'SBOM analytics failed: python-3.14: three subject-specific SPDXs required\n')
        self.assertFalse(self.report.exists())

    def test_invalid_json_in_context_and_in_spdx_document(self):
        self.assert_failure(self.run_cli(b'{"schema_version": 1,'), 'PARSE_CONTEXT', 'INVALID_JSON', 'INPUT_JSON')
        self.assert_failure(self.run_cli(b'{"a": 1, "a": 2}'), 'PARSE_CONTEXT', 'INVALID_JSON', 'INPUT_JSON')
        Path(self.context['images'][0]['documents'][0]['path']).write_bytes(b'{not json')
        diagnostic = self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'INVALID_JSON', 'INPUT_JSON')
        self.assertTrue(diagnostic['message'].startswith('python-3.14/sbom-index.spdx.json: invalid JSON'))

    def test_incompatible_spdx_is_identified_with_its_document(self):
        mutate_spdx(self.context, lambda value: value.update(spdxVersion='SPDX-2.2'), document=1)
        diagnostic = self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'SPDX_INCOMPATIBLE', 'SPDX_CONTRACT')
        self.assertEqual(diagnostic['message'], 'python-3.14/sbom-x86_64.spdx.json: unsupported SPDX version (expected SPDX-2.3)')

    def test_missing_required_field_and_invalid_identity(self):
        del self.context['origin']
        diagnostic = self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'FIELDS_INVALID', 'CONTRACT')
        self.assertEqual(diagnostic['message'], 'analytics input: missing/unknown fields')
        context = synthetic(self.root / 'other')
        context['origin']['run_id'] = 0
        self.assert_failure(self.run_cli(context), 'VALIDATE', 'CONTEXT_INVALID', 'CONTRACT')

    def test_divergent_and_invalid_digests(self):
        document = self.context['images'][0]['documents'][1]
        document['sha256'] = '0' * 64
        self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'SPDX_HASH_MISMATCH', 'INTEGRITY')
        del document['sha256']
        self.context['images'][0]['platforms']['linux/amd64'] = 'sha256:' + '0' * 64
        self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'SUBJECT_MISMATCH', 'INTEGRITY')
        self.context['images'][0]['platforms']['linux/amd64'] = 'sha256:ABC'
        self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'INVALID_DIGEST', 'INTEGRITY')

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'root bypasses filesystem permissions')
    def test_filesystem_errors_report_errno_without_paths(self):
        self.input.write_bytes(canonical(self.context))
        self.input.chmod(0)
        self.addCleanup(self.input.chmod, 0o600)
        diagnostic = self.assert_failure(self.run_cli(), 'READ_CONTEXT', 'FILESYSTEM_ERROR', 'FILESYSTEM')
        self.assertEqual(diagnostic['context'], {'exception': 'PermissionError', 'errno': 'EACCES'})
        self.assertNotIn(str(self.root), json.dumps(diagnostic))
        self.input.chmod(0o600)
        locked = self.root / 'locked'
        locked.mkdir(mode=0o500)
        self.addCleanup(locked.chmod, 0o700)
        self.output = locked / 'output'
        self.assert_failure(self.run_cli(), 'EXPORT', 'FILESYSTEM_ERROR', 'FILESYSTEM')

    def test_malicious_paths_fail_closed_without_reading_secrets_into_output(self):
        outside = self.root / 'outside.json'
        outside.write_bytes(canonical({'token': SECRET, 'sboms': SECRET}))
        self.context['images'][0]['validation'] = dict(path='../outside.json', reference='traversal')
        diagnostic = self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'CONTEXT_INVALID', 'CONTRACT')
        self.assertEqual(diagnostic['message'], 'invalid validation SPDX inventory')
        del self.context['images'][0]['validation']
        text = self.root / 'environment'
        text.write_text('AWS_SECRET_ACCESS_KEY=' + SECRET + '\n')
        self.context['images'][0]['documents'][0]['path'] = str(text)
        status, out, err, diagnostic = self.run_cli(self.context)
        self.assert_failure((status, out, err, diagnostic), 'VALIDATE', 'INVALID_JSON', 'INPUT_JSON')
        self.assertNotIn(SECRET, err + json.dumps(diagnostic))
        for special in ('symlink', 'fifo', 'directory'):
            target = self.root / ('special-' + special)
            if special == 'symlink':
                target.symlink_to(self.context['images'][0]['documents'][1]['path'])
            elif special == 'fifo':
                os.mkfifo(target)
            else:
                target.mkdir()
            self.context['images'][0]['documents'][0]['path'] = str(target)
            with self.subTest(special=special):
                self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'NOT_A_REGULAR_FILE', 'UNSAFE_PATH')
        self.context['images'][0]['documents'][0]['path'] = 'nul\x00byte.json'
        diagnostic = self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'NOT_A_REGULAR_FILE', 'UNSAFE_PATH')
        self.assertEqual(diagnostic['message'], '<context-directory>/nul?byte.json: regular local file required')

    def test_unsafe_output_and_report_sinks_are_refused_before_any_work(self):
        real = self.root / 'real-output'
        real.mkdir()
        self.output.symlink_to(real, target_is_directory=True)
        self.assert_failure(self.run_cli(self.context), 'EXPORT', 'SYMLINK_REFUSED', 'UNSAFE_PATH')
        self.assertEqual(list(real.iterdir()), [])
        self.output = self.root / 'output-2'
        self.assert_failure(self.run_cli(self.context, '--output', 's3://bucket/prefix'), 'ARGUMENTS',
                            'OUTPUT_NOT_LOCAL', 'UNSAFE_PATH')
        victim = self.root / 'victim.json'
        victim.write_bytes(b'{"keep": true}')
        self.report.unlink()
        self.report.symlink_to(victim)
        for report in (self.report, self.input, self.output / 'report.json', 's3://bucket/report.json'):
            with self.subTest(report=report), patch('sys.stdout', new_callable=io.StringIO), \
                    patch('sys.stderr', new_callable=io.StringIO) as err:
                status = main(['--input', str(self.input), '--output', str(self.output), '--report', str(report)])
            self.assertEqual(status, 1)
            self.assertIn('report must', err.getvalue())
        self.assertEqual(victim.read_bytes(), b'{"keep": true}')
        self.assertEqual(self.input.read_bytes(), canonical(self.context))
        self.assertFalse(self.output.exists())

    def test_concurrent_writer_is_retryable_and_never_partial(self):
        self.input.write_bytes(canonical(self.context))
        batch_id = prepare(self.context).batch_id
        self.output.mkdir()
        lock = self.output / ('.' + batch_id + '.lock')
        lock.write_bytes(b'')
        diagnostic = self.assert_failure(self.run_cli(), 'EXPORT', 'OUTPUT_BUSY', 'CONCURRENCY')
        self.assertTrue(diagnostic['retryable'])
        lock.unlink()
        self.assertEqual(self.run_cli()[3]['code'], 'BATCH_CREATED')

    def test_parallel_processes_converge_on_one_verified_batch(self):
        self.input.write_bytes(canonical(self.context))
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        processes = [subprocess.Popen([sys.executable, '-B', '-m', 'scripts.pipeline.analytics.normalize',
                                       '--input', str(self.input), '--output', str(self.output),
                                       '--report', str(self.root / ('reports/%d.json' % i))],
                                      cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for i in range(4)]
        outcomes = [(p.communicate(timeout=120), p.returncode) for p in processes]
        codes = [json.loads((self.root / ('reports/%d.json' % i)).read_bytes())['code'] for i in range(4)]
        self.assertTrue(set(codes) <= {'BATCH_CREATED', 'BATCH_ALREADY_PRESENT_IDENTICAL', 'OUTPUT_BUSY'}, codes)
        self.assertEqual(codes.count('BATCH_CREATED'), 1)
        for ((out, err), status), code in zip(outcomes, codes):
            self.assertEqual(status, 1 if code == 'OUTPUT_BUSY' else 0, err)
            self.assertNotIn(b'Traceback', err)
        batches = list((self.output / 'batches').iterdir())
        self.assertEqual(len(batches), 1)
        read_completed(batches[0])
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['batches'])

    def test_missing_dependency_is_reported_as_such(self):
        with patch.dict(sys.modules, {'pyarrow': None, 'pyarrow.parquet': None}):
            diagnostic = self.assert_failure(self.run_cli(self.context), 'EXPORT', 'DEPENDENCY_UNAVAILABLE', 'DEPENDENCY')
        self.assertEqual(diagnostic['message'], 'required module unavailable: pyarrow')
        self.assertEqual([p.name for p in self.output.iterdir()], ['batches'])

    def test_unexpected_error_has_no_traceback_or_message_payload(self):
        with patch.object(normalize, 'prepare', side_effect=RuntimeError(SECRET)):
            status, out, err, diagnostic = self.run_cli(self.context)
        self.assert_failure((status, out, err, diagnostic), 'VALIDATE', 'NORMALIZER_INTERNAL_ERROR', 'INTERNAL')
        self.assertEqual(err, 'SBOM analytics failed: internal error (RuntimeError)\n')
        self.assertNotIn(SECRET, json.dumps(diagnostic))

    def test_messages_redact_local_roots_and_control_characters(self):
        missing = self.root / 'input' / 'missing.json'
        self.context['images'][0]['documents'][0]['path'] = 'missing.json'
        diagnostic = self.assert_failure(self.run_cli(self.context), 'VALIDATE', 'NOT_A_REGULAR_FILE', 'UNSAFE_PATH')
        self.assertEqual(diagnostic['message'], '<context-directory>/missing.json: regular local file required')
        self.assertFalse(missing.exists())
        self.assertNotIn(str(self.root.resolve()), json.dumps(diagnostic))
        self.assert_failure(self.run_cli(b'{"k\\u0007\\n' + b'x' * 400 + b'": 1, "k\\u0007\\n' + b'x' * 400 + b'": 2}'),
                            'PARSE_CONTEXT', 'INVALID_JSON', 'INPUT_JSON')
        message = json.loads(self.report.read_bytes())['message']
        self.assertLessEqual(len(message), 300)
        self.assertTrue(all(' ' <= c <= '~' for c in message))

    def test_argument_errors_keep_exit_status_and_report_when_requested(self):
        with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit) as raised:
            main(['--output', str(self.output), '--report', str(self.report)])
        self.assertEqual(raised.exception.code, 2)
        diagnostic = json.loads(self.report.read_bytes())
        self.assertEqual((diagnostic['stage'], diagnostic['code'], diagnostic['exit_code']), ('ARGUMENTS', 'ARGUMENTS_INVALID', 2))

    def test_report_write_failure_never_becomes_success(self):
        blocker = self.root / 'not-a-directory'
        blocker.write_bytes(b'')
        self.report = blocker / 'report.json'
        status, out, err, _ = self.run_cli(self.context, report=False)
        self.assertEqual(status, 0)
        with patch('sys.stdout', new_callable=io.StringIO), patch('sys.stderr', new_callable=io.StringIO) as err:
            status = main(['--input', str(self.input), '--output', str(self.output), '--report', str(self.report)])
        self.assertEqual(status, 1)
        self.assertIn('report not written', err.getvalue())

    def test_each_code_has_one_rule_and_every_stage_a_fallback(self):
        codes = [code for _, code, _ in normalize.FAILURES]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(set(normalize.STAGE_FAILURES), {'ARGUMENTS', 'READ_CONTEXT', 'PARSE_CONTEXT', 'VALIDATE', 'EXPORT'})
        self.assertTrue(set(normalize.EXPORT_CODES) <= set(codes))


if __name__ == '__main__':
    unittest.main()
