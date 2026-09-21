"""Real loopback HTTP/shutdown checks; container hardening remains a hosted test.

These offline tests exercise the actual Python application request handler.
Only the Linux/container-specific security probe is mocked for host portability;
its placeholder values are not evidence of a hardened consumer execution.
"""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'tests/consumer-apps/python/app.py'


def load_application():
    spec = importlib.util.spec_from_file_location('consumer_http_integration_fixture', APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(port, path):
    connection = HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, response.getheader('Content-Type'), json.loads(response.read())
    finally:
        connection.close()


class ConsumerHttpApplicationTests(unittest.TestCase):
    def setUp(self):
        self.app = load_application()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.app.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive(), 'HTTP test server did not terminate')

    def test_health_serves_real_http_200_and_healthy_json(self):
        status, content_type, body = request(self.port, '/health')
        self.assertEqual(status, 200)
        self.assertEqual(content_type, 'application/json')
        self.assertEqual(body['status'], 'ok')

    def test_ready_serves_real_http_200_and_healthy_json(self):
        status, content_type, body = request(self.port, '/ready')
        self.assertEqual(status, 200)
        self.assertEqual(content_type, 'application/json')
        self.assertEqual(body['status'], 'ok')

    def test_info_reports_actual_runtime_and_architecture_over_http(self):
        # The HTTP contract is under test here, not this developer host's UID,
        # /proc or mount configuration. Explicitly label the mocked probe.
        mocked_probe = {'offline_wire_test_only': True}
        with patch.object(self.app, 'security', return_value=mocked_probe) as probe:
            status, content_type, body = request(self.port, '/info')
        machine = platform.machine().lower()
        expected_arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(machine, machine)
        self.assertEqual(status, 200)
        self.assertEqual(content_type, 'application/json')
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['runtime'], 'python')
        self.assertEqual(body['runtime_version'], platform.python_version())
        self.assertEqual(body['architecture'], expected_arch)
        self.assertEqual(body['security'], mocked_probe)
        probe.assert_called_once_with()

    def test_security_probe_failure_is_an_http_failure_not_healthy_info(self):
        with patch.object(self.app, 'security', side_effect=OSError('probe unavailable')):
            status, _, body = request(self.port, '/info')
        self.assertEqual(status, 500)
        self.assertEqual(body['status'], 'error')
        self.assertIn('probe unavailable', body['error'])

    def test_unknown_route_is_not_a_successful_health_response(self):
        status, _, body = request(self.port, '/unknown')
        self.assertEqual(status, 404)
        self.assertEqual(body['status'], 'not_found')


@unittest.skipUnless(os.name == 'posix', 'the production execution target is Linux/POSIX')
class ConsumerShutdownTests(unittest.TestCase):
    def test_python_application_handles_sigterm_and_exits_without_kill(self):
        # Run the real main()/signal handlers. Substitute only the listen
        # address to allocate a free loopback port instead of requiring 8080.
        child = '''
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('consumer_shutdown_fixture', sys.argv[1])
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
original_server = app.ThreadingHTTPServer
def ephemeral_server(_address, handler):
    server = original_server(('127.0.0.1', 0), handler)
    Path(sys.argv[2]).write_text(str(server.server_address[1]))
    return server
app.ThreadingHTTPServer = ephemeral_server
app.main()
'''
        with tempfile.TemporaryDirectory() as temporary:
            port_file = Path(temporary) / 'port.txt'
            process = subprocess.Popen([sys.executable, '-B', '-c', child, str(APP), str(port_file)],
                                       text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                ready = False
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        stdout, stderr = process.communicate(timeout=1)
                        self.fail(f'application exited before readiness: {stdout} {stderr}')
                    if port_file.exists():
                        try:
                            port = int(port_file.read_text())
                            status, _, body = request(port, '/health')
                            ready = status == 200 and body.get('status') == 'ok'
                        except (OSError, ValueError):
                            pass
                    if ready:
                        break
                    time.sleep(0.05)
                self.assertTrue(ready, 'application did not serve health within five seconds')
                process.terminate()  # POSIX SIGTERM; this is the application under test.
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertIn('consumer shutdown complete', stdout)
            finally:
                if process.poll() is None:
                    # Only failed tests reach this cleanup; it never counts as
                    # a graceful shutdown and prevents leaking a test process.
                    process.kill()
                    process.communicate(timeout=2)


if __name__ == '__main__':
    unittest.main()
