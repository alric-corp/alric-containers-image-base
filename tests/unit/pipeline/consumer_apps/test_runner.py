import copy
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from scripts.pipeline.consumer_apps import model, runner, summary
from tests.unit.pipeline.consumer_apps.support import good_result, inventory


class ConsumerModelTests(unittest.TestCase):
    def test_scenarios_cover_exact_catalog_and_eighteen_executions(self):
        covered = [item[key] for item in model.SCENARIOS for key in ('framework', 'dev_framework') if item[key]]
        self.assertEqual(len(model.SCENARIOS), 9)
        self.assertEqual(len(covered), 16)
        self.assertEqual(sorted(covered), sorted(model.CATALOG))
        self.assertEqual(sorted(model.CATALOG), sorted(path.stem for path in (model.ROOT / 'frameworks').glob('*.yaml')))
        self.assertEqual(len(model.SCENARIOS) * len(model.ARCHITECTURES), 18)

    def test_compiled_node_and_python_relationships_are_explicit(self):
        for item in model.SCENARIOS:
            self.assertEqual(item['dev_framework'], None if item['family'] == 'python' else item['framework'] + '-dev')
        self.assertEqual(sum(item['dev_framework'] is not None for item in model.SCENARIOS), 7)

    def test_execution_boundary_rejects_mutable_or_other_run_identity(self):
        for field, value in [('image_ref', 'example.org/app:latest'), ('immutable_tag', '210926-0422-r999-a1'),
                             ('digest', 'sha256:' + 'f' * 64), ('repository', 'unrelated')]:
            with self.subTest(field=field):
                data = inventory(); data['candidates']['go1-26'][field] = value
                with self.assertRaises(ValueError):
                    model.validate_inventory(data)


class ExecutionEvidenceTests(unittest.TestCase):
    def test_all_eighteen_valid_results(self):
        for item in model.SCENARIOS:
            for arch in model.ARCHITECTURES:
                with self.subTest(framework=item['framework'], arch=arch):
                    runner.validate_result(good_result(item['framework'], arch), inventory())

    def test_success_cannot_hide_missing_http_or_wrong_arch_version_security(self):
        mutations = [
            lambda r: r.pop('health'),
            lambda r: r['ready'].update(http_status=503),
            lambda r: r['info']['body'].update(architecture='arm64'),
            lambda r: r['info']['body'].update(runtime_version='1.25.9'),
            lambda r: r['info']['body'].update(runtime='python'),
            lambda r: r['info']['body']['security'].update(uid=0),
            lambda r: r['info']['body']['security'].update(cap_eff='0001'),
            lambda r: r['info']['body']['security'].update(no_new_privileges=False),
            lambda r: r.update(container_started=False),
            lambda r: r.update(source_run_id=999),
            lambda r: r.update(source_sha='b' * 40),
            lambda r: r.update(dev_digest='sha256:' + 'b' * 64),
            lambda r: r.update(runtime_manifest_digest='sha256:' + 'b' * 64),
            lambda r: r.update(shutdown_exit_code=137),
            lambda r: r.update(shutdown_marker_observed=False),
            lambda r: r.update(oom_killed=True),
            lambda r: r.update(build_seconds=float('nan')),
            lambda r: r.update(platform='amd64'),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = good_result(); mutation(result)
                with self.assertRaises(ValueError):
                    runner.validate_result(result, inventory())

    def test_java_normal_sigterm_still_needs_hook_completion(self):
        result = good_result('java21'); result['shutdown_exit_code'] = 143
        runner.validate_result(result, inventory())
        result['shutdown_marker_observed'] = False
        with self.assertRaises(ValueError):
            runner.validate_result(result, inventory())

    def test_readiness_is_bounded_and_not_fixed_sleep(self):
        with patch.object(runner, 'fetch_json', side_effect=ConnectionRefusedError('not ready')), \
                patch.object(runner.time, 'monotonic', side_effect=[0, 0, 2]), \
                patch.object(runner.time, 'sleep') as sleep:
            with self.assertRaisesRegex(TimeoutError, 'readiness timeout'):
                runner.wait_for_health('http://127.0.0.1:1/health', timeout=1)
            sleep.assert_called_once_with(0.2)

    def test_build_failure_preserves_per_execution_failure_json(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner.Runner, 'command', side_effect=RuntimeError('pull failed')):
            result = runner.execute(inventory(), 'go1-26', 'arm64', Path(directory))
            saved = json.loads((Path(directory) / 'go1-26-arm64.json').read_text())
            self.assertEqual(result, saved)
            self.assertEqual(saved['status'], 'FAIL')
            self.assertFalse(saved['container_started'])
            self.assertIn('pull failed', saved['error'])

    def test_command_timeout_preserves_partial_build_output(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner.subprocess, 'run', side_effect=subprocess.TimeoutExpired(
                    ['docker', 'buildx'], 1, output=b'compiler reached source', stderr=b'last diagnostic')):
            harness = runner.Runner(Path(directory))
            with self.assertRaises(subprocess.TimeoutExpired):
                harness.command('docker', 'buildx', 'build', timeout=1)
            diagnostic = (Path(directory) / 'commands.log').read_text()
            self.assertIn('compiler reached source', diagnostic)
            self.assertIn('last diagnostic', diagnostic)

    def test_actual_run_builds_offline_and_starts_hardened_target_platform(self):
        source = inventory(); expected = good_result('nodejs22', 'arm64')
        commands = []
        running = {'Config': {'User': '10000'}, 'State': {'Running': True},
                   'HostConfig': {'ReadonlyRootfs': True, 'CapDrop': ['ALL'], 'CapAdd': None,
                    'Privileged': False, 'Binds': None, 'PidMode': '', 'NetworkMode': 'default',
                    'Tmpfs': {'/tmp': runner.TMPFS, '/app/work': runner.TMPFS},
                    'SecurityOpt': ['no-new-privileges']},
                   'NetworkSettings': {'Ports': {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '1234'}]}}}
        def command(_self, *args, **kwargs):
            commands.append(args)
            if args[1] == 'info':
                return json.dumps({'OSType': 'linux', 'Architecture': 'x86_64'})
            if args[1] == 'logs':
                return runner.SHUTDOWN_MARKER
            return ''
        inspections = 0
        def inspect(_self, kind, name):
            nonlocal inspections
            if kind == 'image':
                return {'Architecture': 'arm64', 'Os': 'linux', 'Config': {'User': '10000'},
                        'RootFS': {'Layers': ['base']}, 'Id': 'sha256:' + 'a' * 64}
            inspections += 1
            if inspections == 1:
                return copy.deepcopy(running)
            return {'State': {'Running': False, 'ExitCode': 0, 'OOMKilled': False}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner.Runner, 'command', command), patch.object(runner.Runner, 'inspect', inspect), \
                patch.object(runner, 'wait_for_health', return_value=(expected['health'], 0.1)), \
                patch.object(runner, 'fetch_json', side_effect=[expected['ready'], expected['info']]):
            result = runner.execute(source, 'nodejs22', 'arm64', Path(directory))
        self.assertEqual(result['status'], 'PASS', result.get('error'))
        self.assertEqual(result['execution_mode'], 'emulated')
        build = next(c for c in commands if c[1:3] == ('buildx', 'build'))
        self.assertEqual(build[build.index('--network') + 1], 'none')
        self.assertEqual(build[build.index('--platform') + 1], 'linux/arm64')
        self.assertIn('--load', build); self.assertNotIn('--push', build)
        self.assertIn('BUILD_IMAGE=' + source['candidates']['nodejs22-dev']['image_ref'], build)
        self.assertIn('RUNTIME_IMAGE=' + source['candidates']['nodejs22']['image_ref'], build)
        run = next(c for c in commands if c[1] == 'run')
        for option in ('--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges'):
            self.assertIn(option, run)
        self.assertNotIn('--user', run)
        self.assertEqual(run[run.index('--platform') + 1], 'linux/arm64')
        self.assertTrue(any(c[1] == 'stop' for c in commands))
        self.assertFalse(any(c[1] in ('push', 'kill') for c in commands))


class SummaryTests(unittest.TestCase):
    def write_results(self, directory):
        for item in model.SCENARIOS:
            for arch in model.ARCHITECTURES:
                name = item['framework'] + '-' + arch
                (directory / (name + '.json')).write_text(json.dumps(good_result(item['framework'], arch)))

    def test_complete_eighteen_http_executions_pass(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name); self.write_results(directory)
            result, markdown = summary.summarize(inventory(), directory)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['consumer_executions_passed'], 18)
        self.assertIn('| python3-14 | PASS | PASS | N/A |', markdown)

    def test_missing_failed_duplicate_or_unknown_evidence_cannot_pass(self):
        for failure in ('missing', 'failed', 'duplicate', 'unknown'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as name:
                directory = Path(name); self.write_results(directory)
                target = directory / 'java21-arm64.json'
                if failure == 'missing':
                    target.unlink()
                elif failure == 'failed':
                    result = good_result('java21', 'arm64'); result['health']['http_status'] = 500
                    target.write_text(json.dumps(result))
                elif failure == 'duplicate':
                    (directory / 'duplicate').mkdir()
                    (directory / 'duplicate' / target.name).write_bytes(target.read_bytes())
                else:
                    (directory / 'unknown-amd64.json').write_text('{}')
                result, _ = summary.summarize(inventory(), directory)
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(result['results']['nodejs22-amd64']['status'], 'PASS')

    def test_failed_download_cannot_report_pass_even_with_all_result_files(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name); self.write_results(directory)
            result, _ = summary.summarize(inventory(), directory, 'failure')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('integrity verification failed', result['errors'][0])

    def test_failed_execution_retains_its_actionable_diagnostic(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name); self.write_results(directory)
            result = good_result('java21', 'arm64')
            result.update(status='FAIL', error='application /health readiness timeout after 90s')
            (directory / 'java21-arm64.json').write_text(json.dumps(result))
            result, markdown = summary.summarize(inventory(), directory)
        self.assertIn('readiness timeout', result['results']['java21-arm64']['error'])
        self.assertIn('readiness timeout', markdown)


if __name__ == '__main__':
    unittest.main()
