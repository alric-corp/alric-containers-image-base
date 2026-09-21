"""Build and execute a downstream HTTP application, using remote ECR digests."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import uuid

from scripts.pipeline.consumer_apps.model import (
    ARCHITECTURES, ROOT, SCENARIOS, scenario, validate_inventory,
)
from scripts.pipeline.runtime.runtime_images import execution_mode

TMPFS = 'rw,nosuid,nodev,noexec,size=64m,mode=1777'
SHUTDOWN_MARKER = 'consumer shutdown complete'


def fetch_json(url):
    # Local readiness traffic never goes through a configured HTTP proxy.
    with build_opener(ProxyHandler({})).open(url, timeout=2) as response:
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            raise ValueError('application response must be HTTP 200 and bounded JSON')
        document = json.loads(body)
        if not isinstance(document, dict):
            raise ValueError('application response must be a JSON object')
        return {'http_status': response.status, 'body': document}


def wait_for_health(url, timeout=90):
    started = time.monotonic()
    last_error = None
    while time.monotonic() - started < timeout:
        try:
            response = fetch_json(url)
            if response['body'].get('status') != 'ok':
                raise ValueError('health response is not healthy')
            return response, time.monotonic() - started
        except HTTPError as error:
            if error.code != 503:
                raise
            last_error = error
        except (URLError, ConnectionError, TimeoutError) as error:
            last_error = error
        time.sleep(0.2)
    raise TimeoutError(f'application /health readiness timeout after {timeout}s: {last_error}')


def validate_http(result, expected, architecture):
    for endpoint in ('health', 'ready', 'info'):
        response = result.get(endpoint, {})
        if response.get('http_status') != 200 or response.get('body', {}).get('status') != 'ok':
            raise ValueError(f'/{endpoint} must return HTTP 200 and healthy status')
    info = result['info']['body']
    if info.get('runtime') != expected['family'] or info.get('architecture') != architecture:
        raise ValueError('/info runtime family or actual architecture differs from the scenario')
    version = info.get('runtime_version', '')
    if not isinstance(version, str) or not re.match(
            r'^(?:go|v)?' + re.escape(expected['expected_version']) + r'(?:[.+-]|$)', version):
        raise ValueError('/info runtime version differs from the catalog')
    security = info.get('security', {})
    if any(type(security.get(key)) is not int or security[key] != 10000 for key in ('uid', 'gid')):
        raise ValueError('application process must report uid/gid 10000/10000')
    for field in ('read_only_root', 'writable_tmp', 'writable_app_work', 'no_new_privileges'):
        if security.get(field) is not True:
            raise ValueError(f'application did not prove {field}')
    if not isinstance(security.get('cap_eff'), str) or not re.fullmatch(r'0+', security['cap_eff']):
        raise ValueError('application has unexpected effective capabilities')
    return security


def validate_container(document):
    host = document['HostConfig']
    if (host.get('ReadonlyRootfs') is not True or host.get('CapDrop') != ['ALL']
            or host.get('CapAdd') or host.get('Privileged') or host.get('Binds')
            or host.get('PidMode') or host.get('NetworkMode') == 'host'
            or set(host.get('Tmpfs', {})) != {'/tmp', '/app/work'}):
        raise ValueError('Docker runtime hardening differs from the consumer contract')
    if not any(value in ('no-new-privileges', 'no-new-privileges=true')
               for value in host.get('SecurityOpt', [])):
        raise ValueError('Docker no-new-privileges must be enabled')
    if document['Config'].get('User') not in ('10000', '10000:10000'):
        raise ValueError('container must preserve the base image non-root user')
    if not document['State'].get('Running'):
        raise ValueError('application container exited before HTTP verification')


def validate_result(result, inventory):
    """A PASS requires actual HTTP, process, platform and shutdown evidence."""
    validate_inventory(inventory)
    expected = scenario(result.get('framework'))
    architecture = result.get('platform', '').removeprefix('linux/')
    if (architecture not in ARCHITECTURES or result.get('platform') != f'linux/{architecture}'
            or type(result.get('schema_version')) is not int or result['schema_version'] != 1
            or result.get('status') != 'PASS' or result.get('error')):
        raise ValueError('application execution has not passed')
    for key in ('source_run_id', 'source_run_attempt', 'source_sha'):
        if result.get(key) != inventory[key]:
            raise ValueError('application evidence belongs to another source run')
    for role, framework in (('runtime', expected['framework']), ('dev', expected['dev_framework'])):
        if framework:
            candidate = inventory['candidates'][framework]
            if (result.get(f'{role}_image_ref') != candidate['image_ref']
                    or result.get(f'{role}_digest') != candidate['digest']
                    or result.get(f'{role}_manifest_digest') != candidate['platforms'][architecture]):
                raise ValueError(f'{role} image evidence is not the resolved candidate')
        elif result.get('dev_image_ref') is not None or result.get('dev_digest') is not None:
            raise ValueError('Python has no dev companion')
    for key in ('build_seconds', 'startup_seconds'):
        if (type(result.get(key)) not in (float, int) or not math.isfinite(result[key])
                or result[key] < 0):
            raise ValueError(f'missing execution timing: {key}')
    if result.get('execution_mode') not in ('native', 'emulated'):
        raise ValueError('missing actual Docker daemon/target execution mode')
    for field in ('container_started', 'build_passed', 'runtime_base_verified', 'container_hardening_verified',
                  'read_only_root', 'writable_tmp', 'writable_app_work', 'no_new_privileges',
                  'graceful_shutdown'):
        if result.get(field) is not True:
            raise ValueError(f'missing successful execution proof: {field}')
    security = validate_http(result, expected, architecture)
    for field in ('uid', 'gid', 'read_only_root', 'writable_tmp', 'writable_app_work',
                  'no_new_privileges', 'cap_eff'):
        if result.get(field) != security[field]:
            raise ValueError(f'inconsistent process evidence: {field}')
    allowed_exit = (0, 143) if expected['family'] == 'java' else (0,)
    if (result.get('shutdown_exit_code') not in allowed_exit
            or result.get('shutdown_marker_observed') is not True
            or result.get('oom_killed') is not False):
        raise ValueError('graceful shutdown evidence is incomplete')
    return result


class Runner:
    def __init__(self, directory):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def command(self, *args, timeout=180):
        try:
            completed = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            with (self.directory / 'commands.log').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(list(args)) + f'\nTIMEOUT after {timeout}s\n')
                for output in (error.stdout, error.stderr):
                    if output:
                        stream.write(output.decode(errors='replace') if isinstance(output, bytes) else output)
            raise
        with (self.directory / 'commands.log').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(list(args)) + '\n' + completed.stdout + completed.stderr + '\n')
        if completed.returncode:
            raise RuntimeError(f'{args[0]} {args[1]} failed ({completed.returncode}): {completed.stderr[-2000:]}')
        return completed.stdout.strip()

    def inspect(self, kind, name, platform=None):
        if kind == 'image' and platform not in ('linux/amd64', 'linux/arm64'):
            raise ValueError('image inspection requires the exact target platform')
        documents = json.loads(self.command('docker', kind, 'inspect', name))
        if len(documents) != 1:
            raise ValueError('Docker inspection is ambiguous')
        if kind == 'image' and documents[0]['Os'] + '/' + documents[0]['Architecture'] != platform:
            raise ValueError('inspected image platform differs from the execution platform')
        return documents[0]


def execute(inventory, framework, architecture, reports):
    expected = scenario(framework)
    if architecture not in ARCHITECTURES:
        raise ValueError('unsupported application platform')
    reports = Path(reports)
    harness = Runner(reports / f'{framework}-{architecture}-logs')
    result = {key: inventory.get(key) for key in ('source_run_id', 'source_run_attempt', 'source_sha')}
    result.update(schema_version=1, framework=framework, platform=f'linux/{architecture}',
                  execution_mode=None, build_seconds=None, startup_seconds=None,
                  container_started=False, build_passed=False, health=None, ready=None, info=None,
                  uid=None, gid=None, read_only_root=False, writable_tmp=False, writable_app_work=False,
                  no_new_privileges=False, cap_eff=None, graceful_shutdown=False, status='FAIL')
    token = uuid.uuid4().hex
    image = f'localhost/consumer-app:{token}'
    container = f'consumer-app-{token}'
    started = False
    stopped = False
    try:
        validate_inventory(inventory)
        candidates = inventory['candidates']
        runtime = candidates[framework]
        dev = candidates[expected['dev_framework']] if expected['dev_framework'] else None
        for role, candidate in (('runtime', runtime), ('dev', dev)):
            result[f'{role}_image_ref'] = candidate['image_ref'] if candidate else None
            result[f'{role}_digest'] = candidate['digest'] if candidate else None
            result[f'{role}_manifest_digest'] = candidate['platforms'][architecture] if candidate else None
        daemon = json.loads(harness.command('docker', 'info', '--format', '{{json .}}'))
        if daemon.get('OSType') != 'linux':
            raise ValueError('application certification needs a Linux Docker daemon')
        result['execution_mode'] = execution_mode(daemon['Architecture'], architecture)
        for candidate in (runtime, dev):
            if candidate:
                # Inspect the exact single-platform child from the verified
                # index. Inspecting a cached multiarch index can silently choose
                # the daemon's native platform, and --platform on image inspect
                # requires API 1.49 (newer than the current hosted Docker 28.0).
                # Dockerfile FROM still uses the source-run index by digest.
                manifest_ref = candidate['image_ref'].split('@')[0] + '@' + candidate['platforms'][architecture]
                harness.command('docker', 'pull', '--platform', result['platform'], manifest_ref, timeout=600)
                base = harness.inspect('image', manifest_ref, result['platform'])
                if base['Architecture'] != architecture or base['Os'] != 'linux':
                    raise ValueError('pulled candidate platform does not match execution platform')
                if candidate is runtime:
                    runtime_base = base
        project = ROOT / 'tests/consumer-apps' / expected['family']
        build = ['docker', 'buildx', 'build', '--load', '--pull', '--no-cache', '--network', 'none',
                 '--platform', result['platform'], '--provenance=false', '--sbom=false',
                 '--metadata-file', str(harness.directory / 'build-metadata.json'),
                 '--tag', image, '--build-arg', f'RUNTIME_IMAGE={runtime["image_ref"]}']
        if dev:
            build.extend(['--build-arg', f'BUILD_IMAGE={dev["image_ref"]}'])
        build.extend(['--file', str(project / 'Dockerfile'), str(project)])
        began = time.monotonic()
        harness.command(*build, timeout=1200)
        result['build_seconds'] = round(time.monotonic() - began, 3)
        result['build_passed'] = True
        derived = harness.inspect('image', image, result['platform'])
        base_layers = runtime_base['RootFS']['Layers']
        if (not base_layers or derived['RootFS']['Layers'][:len(base_layers)] != base_layers
                or derived['Config']['User'] != runtime_base['Config']['User']
                or derived['Architecture'] != architecture or derived['Os'] != 'linux'):
            raise ValueError('final application image does not preserve the runtime candidate/platform/user')
        result['runtime_base_verified'] = True
        result['derived_image_id'] = derived['Id']
        began = time.monotonic()
        # Mark before the call: a daemon may create the container even if the
        # client loses its response. Cleanup targets only our unique name.
        started = True
        harness.command('docker', 'run', '--detach', '--name', container, '--platform', result['platform'],
                        '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                        '--stop-signal', 'SIGTERM', '--tmpfs', '/tmp:' + TMPFS,
                        '--tmpfs', '/app/work:' + TMPFS, '--publish', '127.0.0.1::8080', image)
        running = harness.inspect('container', container)
        validate_container(running)
        result['container_started'] = True
        result['container_hardening_verified'] = True
        ports = running['NetworkSettings']['Ports'].get('8080/tcp', [])
        if len(ports) != 1 or ports[0]['HostIp'] != '127.0.0.1' or not ports[0]['HostPort'].isdigit():
            raise ValueError('HTTP port must be bound only to the runner loopback')
        address = 'http://127.0.0.1:' + ports[0]['HostPort']
        result['health'], _ = wait_for_health(address + '/health')
        result['startup_seconds'] = round(time.monotonic() - began, 3)
        result['ready'] = fetch_json(address + '/ready')
        result['info'] = fetch_json(address + '/info')
        security = validate_http(result, expected, architecture)
        result.update({key: security[key] for key in ('uid', 'gid', 'read_only_root', 'writable_tmp',
                      'writable_app_work', 'no_new_privileges', 'cap_eff')})
        # docker stop can escalate to SIGKILL; exit 137 is a FAIL, never a
        # successful graceful shutdown. Java's normal SIGTERM exit is 143.
        harness.command('docker', 'stop', '--timeout', '15', container, timeout=30)
        final = harness.inspect('container', container)
        logs = harness.command('docker', 'logs', container)
        stopped = not final['State']['Running']
        result['shutdown_exit_code'] = final['State']['ExitCode']
        result['oom_killed'] = final['State']['OOMKilled']
        result['shutdown_marker_observed'] = SHUTDOWN_MARKER in logs
        result['graceful_shutdown'] = (stopped and not result['oom_killed']
            and result['shutdown_marker_observed']
            and result['shutdown_exit_code'] in ((0, 143) if expected['family'] == 'java' else (0,)))
        result['status'] = 'PASS'
        validate_result(result, inventory)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result['status'] = 'FAIL'
        result['error'] = str(error)
    finally:
        if started:
            for args in [('docker', 'logs', container),
                         ('docker', 'container', 'inspect', container)]:
                try:
                    harness.command(*args)
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    pass
            if not stopped:
                try:
                    harness.command('docker', 'stop', '--timeout', '15', container, timeout=30)
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    pass
            try:
                harness.command('docker', 'container', 'rm', container)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                pass
        try:
            harness.command('docker', 'image', 'rm', image)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            pass
        (reports / f'{framework}-{architecture}.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--framework', choices=[item['framework'] for item in SCENARIOS], required=True)
    parser.add_argument('--architecture', choices=ARCHITECTURES, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    result = execute(json.loads(args.inventory.read_text()), args.framework, args.architecture, args.reports)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
