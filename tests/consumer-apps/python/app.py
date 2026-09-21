"""A downstream Python HTTP service with no third-party dependencies."""
import errno
import json
import os
import platform
import signal
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


def writable(directory):
    try:
        with tempfile.TemporaryFile(dir=directory) as stream:
            stream.write(b'consumer-app')
            stream.seek(0)
            return stream.read() == b'consumer-app'
    except OSError:
        return False


def security():
    fields = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    probe = Path('/app/certification-root-probe')
    readonly = False
    error = 'write unexpectedly succeeded'
    try:
        probe.write_text('must fail on read-only root')
        probe.unlink()
    except OSError as exc:
        readonly = exc.errno == errno.EROFS
        error = str(exc)
    return {
        'uid': os.getuid(), 'gid': os.getgid(),
        'read_only_root': readonly, 'root_write_error': error,
        'writable_tmp': writable('/tmp'), 'writable_app_work': writable('/app/work'),
        'cap_eff': fields['CapEff'].strip(),
        'no_new_privileges': fields['NoNewPrivs'].strip() == '1',
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 -- standard-library request handler interface
        status = 200
        body = {'status': 'ok'}
        try:
            path = urlsplit(self.path).path
            if path == '/info':
                machine = platform.machine().lower()
                body = {
                    'status': 'ok', 'runtime': 'python',
                    'runtime_version': platform.python_version(),
                    'architecture': {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(machine, machine),
                    'security': security(),
                }
            elif path not in ('/health', '/ready'):
                status, body = 404, {'status': 'not_found'}
        except (OSError, ValueError, KeyError) as exc:
            status, body = 500, {'status': 'error', 'error': str(exc)}
        data = json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    server = ThreadingHTTPServer(('0.0.0.0', 8080), Handler)
    stopping = threading.Event()

    def shutdown(_signal, _frame):
        if not stopping.is_set():
            stopping.set()
            # shutdown() must run outside serve_forever's thread.
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
    print('consumer shutdown complete', flush=True)


if __name__ == '__main__':
    main()
