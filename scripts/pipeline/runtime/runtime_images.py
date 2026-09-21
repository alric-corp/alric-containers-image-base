#!/usr/bin/env python3
"""Executa os contratos funcionais (M08/M10) nas duas plataformas de um
artifact OCI já validado, sem rebuild da imagem base.

Dois tipos de contrato, mesmo contrato de ambiente e de saída:

- interpretado (Node, Python): o probe roda com o interpretador da própria
  imagem candidata, montado somente para leitura;
- compilado (Go, Java, .NET): o projeto mínimo versionado em
  `tests/runtime/projects/` é construído por um Dockerfile multi-stage real
  usando a variante `-dev` do candidato como estágio de build e a variante de
  runtime como estágio final — o mesmo par que o README documenta.

Emulação e execução nativa são registradas separadamente em cada relatório.
"""
import argparse
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid

from scripts.pipeline.artifacts.oci_artifact import blob, load_index, verify
from scripts.pipeline.runtime.readiness import wait_until_ready
from scripts.pipeline.runtime import contract_evidence

ROOT = Path(__file__).resolve().parents[3]
SKOPEO = 'quay.io/skopeo/stable:v1.22.2-immutable@sha256:4a16d57b37617a04b3d643079a477a2848efe892dffcdf0ce56df4262b65f810'

# Contrato de ambiente compartilhado pelos quatro runtimes.
IMAGE_CA_BUNDLE = '/etc/ssl/certs/ca-certificates.crt'
READONLY_PATH = '/app/runtime-test-write'
# Raiz somente leitura com áreas graváveis explícitas: `/tmp` e uma área de
# trabalho da aplicação. Duas provas diferentes — a segunda mostra que um
# diretório sob `/app` pode ser concedido sem abrir a raiz.
WRITABLE_DIRS = ('/tmp', '/app/work')
TMPFS = 'rw,nosuid,nodev,noexec,size=16m,mode=1777'

# Projetos compilados: prefixo do framework -> diretório do projeto mínimo e
# comando que comprova o toolchain na variante -dev.
COMPILED = (
    (r'go1-\d+', 'go', 'go version'),
    (r'java\d+', 'java', 'javac -version'),
    (r'dotnet\d+', 'dotnet', 'dotnet --version'),
)


def command(*args, timeout=180):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): {result.stderr[-4000:]}')
    return result.stdout.strip()


def catalog(framework):
    if not (ROOT / 'frameworks' / f'{framework}.yaml').is_file():
        raise ValueError('framework must exist in the repository catalog')
    return framework


def runtime(framework):
    """Contrato interpretado: executável da imagem e probe correspondente."""
    catalog(framework)
    if re.fullmatch(r'nodejs\d+(?:-dev)?', framework):
        return '/usr/bin/node', 'probe.cjs'
    if re.fullmatch(r'python3-\d+', framework):
        return '/usr/bin/python3', 'probe.py'
    raise ValueError('interpreted contracts support Node and Python only')


def project(framework):
    """Contrato compilado: projeto mínimo, variante -dev pareada e toolchain."""
    catalog(framework)
    for pattern, directory, toolchain in COMPILED:
        if not re.fullmatch(pattern, framework):
            continue
        dev = f'{framework}-dev'
        if not (ROOT / 'frameworks' / f'{dev}.yaml').is_file():
            # Cobertura gradual explícita (M07 parcial): sem o par de build
            # não há como compilar o projeto mínimo neste framework.
            raise ValueError(f'{framework} has no {dev} build variant yet; '
                             'a compiled contract needs the build/runtime pair')
        return ROOT / 'tests' / 'runtime' / 'projects' / directory, dev, toolchain
    base = framework.removesuffix('-dev')
    if base != framework and any(re.fullmatch(pattern, base) for pattern, _, _ in COMPILED):
        raise ValueError(f'{framework} is the build stage of the {base} contract '
                         '(shell, toolchain and the multi-stage build are exercised there); '
                         'it has no contract of its own')
    raise ValueError('compiled contracts support Go, Java and .NET only')


def expected_version(framework):
    """Versão que o runtime da imagem deve reportar, derivada do catálogo."""
    catalog(framework)
    for pattern, template in ((r'nodejs(\d+)(?:-dev)?', '{0}'), (r'python3-(\d+)', '3.{0}'),
                              (r'go1-(\d+)', '1.{0}'), (r'java(\d+)', '{0}'),
                              (r'dotnet(\d+)', '{0}')):
        match = re.fullmatch(pattern, framework)
        if match:
            return template.format(*match.groups())
    raise ValueError(f'no version expectation defined for {framework}')


def supported(framework):
    """'interpreted' ou 'compiled'; erro explícito para o que não tem contrato."""
    try:
        runtime(framework)
        return 'interpreted'
    except ValueError:
        return 'compiled' if project(framework) else None


def contracts():
    """Frameworks do catálogo que têm contrato funcional executável hoje."""
    covered = []
    for path in sorted((ROOT / 'frameworks').glob('*.yaml')):
        try:
            supported(path.stem)
        except ValueError:
            continue
        covered.append(path.stem)
    return covered


def execution_mode(daemon_arch, target_arch):
    aliases = {'x86_64': 'amd64', 'aarch64': 'arm64'}
    daemon_arch = aliases.get(daemon_arch, daemon_arch)
    if daemon_arch not in ('amd64', 'arm64'):
        raise ValueError(f'unsupported Docker daemon architecture: {daemon_arch}')
    return 'native' if daemon_arch == target_arch else 'emulated'


def validate_result(output):
    result = json.loads(output)
    if result.get('uid') != 10000 or result.get('gid') != 10000:
        raise ValueError('runtime did not confirm uid/gid 10000')
    for key in ('readonly', 'tmpfs', 'writable_dirs', 'bundle_parse',
                'timezone', 'tls_trusted', 'tls_untrusted_rejected'):
        if result.get(key) is not True:
            raise ValueError(f'runtime did not confirm {key}')
    return result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'runtime-tls-ok\n')

    def log_message(self, *args):
        pass


@contextmanager
def tls_server(directory, name, identity=None):
    cert, key = directory / f'{name}.pem', directory / f'{name}.key'
    if identity:
        cert, key = map(Path, identity)
    else:
        command('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-keyout', str(key), '-out', str(cert), '-subj', '/CN=host.docker.internal',
            '-addext', 'subjectAltName=DNS:host.docker.internal',
            '-addext', 'basicConstraints=critical,CA:TRUE')
    server = ThreadingHTTPServer(('0.0.0.0', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # M08/M10/M14: bounded readiness check from the harness (this
        # process), not the container -- replaces the implicit assumption
        # that a bound socket is already reachable across the Docker
        # bridge by the time the container starts. A fast server pays no
        # wait; one that never comes up fails within the limit instead of
        # the container hanging on connection refused for its own timeout.
        wait_until_ready(
            lambda: socket.create_connection(('127.0.0.1', server.server_port), timeout=1).close(),
            interval=0.05, timeout=5.0, attempts=100)
        yield f'https://host.docker.internal:{server.server_port}/', cert
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def expected_config(layout, arch):
    _, index = load_index(layout)
    entry = next(item for item in index['manifests']
                 if item['platform']['architecture'] == arch)
    manifest = json.loads(blob(layout, entry).read_text())
    return manifest['config']['digest']


def archive_config(archive):
    with tarfile.open(archive) as source:
        manifests = json.load(source.extractfile('manifest.json'))
        if len(manifests) != 1:
            raise ValueError('Docker archive must contain exactly one image')
        config = source.extractfile(manifests[0]['Config']).read()
    return 'sha256:' + hashlib.sha256(config).hexdigest()


def remove(*args):
    # Só recursos criados por esta invocação; nunca prune de estado compartilhado.
    subprocess.run(args, capture_output=True, timeout=60)


@contextmanager
def loaded_platform(layout, arch, directory):
    """Importa uma plataforma do candidato e prova que é ela que roda."""
    tag = f'localhost/runtime-candidate:{uuid.uuid4().hex}'
    archive = directory / f'{uuid.uuid4().hex}.tar'
    exported = directory / f'{uuid.uuid4().hex}-loaded.tar'
    try:
        command('docker', 'run', '--rm', '-v', f'{layout}:/candidate:ro',
                '-v', f'{directory}:/output', SKOPEO, '--override-arch', arch,
                '--override-os', 'linux', 'copy', 'oci:/candidate:image',
                f'docker-archive:/output/{archive.name}:{tag}')
        command('docker', 'load', '--input', str(archive))
        inspected = json.loads(command('docker', 'image', 'inspect', tag))[0]
        # Docker's containerd store may expose a manifest digest as Id. Re-export
        # the loaded image and hash its actual config instead of assuming Id's type.
        command('docker', 'image', 'save', '--output', str(exported), inspected['Id'])
        config_digest = archive_config(exported)
        if config_digest != expected_config(layout, arch):
            raise ValueError('loaded image config differs from the verified OCI candidate')
        if inspected['Architecture'] != arch or inspected['Os'] != 'linux':
            raise ValueError('loaded image platform differs from the requested platform')
        yield tag, inspected['Id'], config_digest
    finally:
        remove('docker', 'image', 'rm', '-f', tag)
        archive.unlink(missing_ok=True)
        exported.unlink(missing_ok=True)


def contract_environment(framework, urls, ca):
    trusted_url, untrusted_url = urls
    # ca=None exercises the trust installed by Melange + Apko, with no mount,
    # SSL_CERT_FILE override, Node override or custom Java/.NET trust store.
    injected = [] if ca is None else [
        '-v', f'{ca}:/test-ca.pem:ro', '-e', 'SSL_CERT_FILE=/test-ca.pem',
        '-e', 'NODE_EXTRA_CA_CERTS=/test-ca.pem', '-e', 'TLS_CA_FILE=/test-ca.pem']
    return injected + ['-e', 'PYTHONDONTWRITEBYTECODE=1',
            '-e', f'IMAGE_CA_BUNDLE={IMAGE_CA_BUNDLE}',
            '-e', f'READONLY_PATH={READONLY_PATH}',
            '-e', f'WRITABLE_DIRS={",".join(WRITABLE_DIRS)}',
            '-e', f'EXPECTED_RUNTIME_VERSION={expected_version(framework)}',
            '-e', f'TLS_TRUSTED_URL={trusted_url}',
            '-e', f'TLS_UNTRUSTED_URL={untrusted_url}']


def contract_run(name, arch, framework, urls, ca):
    """Execução non-root, sem capabilities, raiz somente leitura e tmpfs."""
    args = ['docker', 'run', '--rm', '--name', name, '--platform', f'linux/{arch}',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--add-host', 'host.docker.internal:host-gateway']
    for directory in WRITABLE_DIRS:
        args += ['--tmpfs', f'{directory}:{TMPFS}']
    return args + contract_environment(framework, urls, ca)


def dev_shell(image, arch, toolchain):
    """Shell funcional como uid/gid 10000 na variante -dev, com o toolchain."""
    name = f'runtime-dev-shell-{uuid.uuid4().hex}'
    script = 'test "$(id -u)" = 10000; test "$(id -g)" = 10000'
    if toolchain:
        script += f'; {toolchain}'
    try:
        return command('docker', 'run', '--rm', '--name', name, '--platform', f'linux/{arch}',
                       '--network', 'none', '--read-only', '--tmpfs', f'/tmp:{TMPFS}',
                       '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                       '-e', 'HOME=/tmp', '-e', 'DOTNET_CLI_HOME=/tmp',
                       '-e', 'DOTNET_CLI_TELEMETRY_OPTOUT=1', '-e', 'DOTNET_NOLOGO=1',
                       '--entrypoint', '/bin/sh', image, '-ec', script, timeout=180)
    finally:
        remove('docker', 'rm', '-f', name)


def run_interpreted(framework, arch, image, urls, ca):
    executable, probe = runtime(framework)
    name = f'runtime-contract-{uuid.uuid4().hex}'
    try:
        args = contract_run(name, arch, framework, urls, ca)
        args += ['-v', f'{ROOT / "tests/runtime"}:/contract:ro']
        output = command(*args, '--entrypoint', executable, image, f'/contract/{probe}', timeout=120)
    finally:
        remove('docker', 'rm', '-f', name)
    result = validate_result(output)
    if framework.endswith('-dev'):
        # Sem toolchain extra: nas variantes -dev interpretadas o próprio
        # interpretador já foi exercido acima.
        dev_shell(image, arch, None)
        result['dev_shell'] = True
    return result


def run_compiled(framework, arch, runtime_image, dev_image, urls, ca, build_timeout):
    directory, _, toolchain = project(framework)
    # A variante -dev precisa de shell e toolchain: é ela que executa o
    # estágio de build shell-form do Dockerfile logo abaixo.
    dev_shell(dev_image, arch, toolchain)
    tag = f'localhost/runtime-application:{uuid.uuid4().hex}'
    name = f'runtime-contract-{uuid.uuid4().hex}'
    started = time.monotonic()
    try:
        # Sem rede no build: os projetos mínimos usam só a biblioteca padrão,
        # então um download aqui seria conteúdo não validado entrando na imagem.
        command('docker', 'build', '--platform', f'linux/{arch}', '--network', 'none',
                '--build-arg', f'BUILD_IMAGE={dev_image}',
                '--build-arg', f'RUNTIME_IMAGE={runtime_image}',
                '--tag', tag, '--file', str(directory / 'Dockerfile'), str(directory),
                timeout=build_timeout)
        build_seconds = round(time.monotonic() - started, 1)
        application = json.loads(command('docker', 'image', 'inspect', tag))[0]['Id']
        # Sem --entrypoint e sem --user: a imagem final precisa trazer a
        # identidade non-root e o entrypoint do próprio Dockerfile.
        output = command(*contract_run(name, arch, framework, urls, ca), tag, timeout=180)
    finally:
        remove('docker', 'rm', '-f', name)
        remove('docker', 'image', 'rm', '-f', tag)
    return dict(validate_result(output), dev_shell=True, build_seconds=build_seconds,
                application_image=application)


def run_platform(layouts, framework, arch, directory, urls, ca, build_timeout):
    runtime_layout, dev_layout = layouts
    with loaded_platform(runtime_layout, arch, directory) as (tag, image, config_digest):
        if dev_layout is None:
            checks = run_interpreted(framework, arch, image, urls, ca)
            return dict(checks, config_digest=config_digest, docker_image_id=image)
        with loaded_platform(dev_layout, arch, directory) as (dev_tag, dev_image, dev_config):
            checks = run_compiled(framework, arch, tag, dev_tag, urls, ca, build_timeout)
        return dict(checks, config_digest=config_digest, docker_image_id=image,
                    dev_config_digest=dev_config, dev_docker_image_id=dev_image)


def verified_layout(layout):
    """Verifica os blobs e confronta com a evidência de validação do artifact."""
    layout = Path(layout).resolve()
    verified = verify(layout)
    if verified != json.loads((layout / 'validated-index.json').read_text()):
        raise ValueError(f'OCI candidate {layout.name} differs from validated-index.json')
    return layout, verified


def run(layout, framework, reports, dev_layout=None, build_timeout=600, baked_ca=None):
    kind = supported(framework)
    if kind == 'compiled':
        _, dev_framework, _ = project(framework)
        if dev_layout is None or not Path(dev_layout).is_dir():
            raise ValueError(f'{framework} needs the validated OCI of {dev_framework} '
                             '(--dev-layout) as the build stage of its contract')
    else:
        dev_layout = None
    reports = Path(reports)
    reports.mkdir(parents=True, exist_ok=True)
    failed = False
    # Overwrite both reports even when OCI verification or setup fails.
    evidence = {arch: {'schema_version': 1, 'framework': framework, 'contract': kind,
                       'platform': f'linux/{arch}', 'repository': os.environ.get('GITHUB_REPOSITORY'),
                       'run_id': os.environ.get('GITHUB_RUN_ID'),
                       'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                       'revision': os.environ.get('GITHUB_SHA'),
                       'status': 'failed', 'started_at': datetime.now(timezone.utc).isoformat()}
                for arch in ('amd64', 'arm64')}
    try:
        layout, verified = verified_layout(layout)
        dev_verified = None
        if kind == 'compiled':
            dev_layout, dev_verified = verified_layout(dev_layout)
        else:
            dev_layout = None
        # Record the verified identities even if subsequent runtime setup fails.
        for arch, report in evidence.items():
            report.update(index_digest=verified['digest'],
                          manifest_digest=verified['platforms'][f'linux/{arch}'])
            if dev_verified is not None:
                report.update(dev_framework=f'{framework}-dev',
                              dev_index_digest=dev_verified['digest'],
                              dev_manifest_digest=dev_verified['platforms'][f'linux/{arch}'])
        daemon_arch = command('docker', 'info', '--format', '{{.Architecture}}')
        with tempfile.TemporaryDirectory(prefix='runtime-contract-') as temporary:
            directory = Path(temporary)
            trusted = (tls_server(directory, 'trusted', (str(baked_ca) + '.pem', str(baked_ca) + '.key'))
                       if baked_ca else tls_server(directory, 'trusted'))
            with trusted as (trusted_url, ca), \
                    tls_server(directory, 'untrusted') as (untrusted_url, _):
                for arch, report in evidence.items():
                    try:
                        report.update(daemon_architecture=daemon_arch,
                                      execution=execution_mode(daemon_arch, arch))
                        report['checks'] = run_platform(
                            (layout, dev_layout), framework, arch, directory,
                            (trusted_url, untrusted_url), None if baked_ca else ca, build_timeout)
                        report['trust_mode'] = 'image' if baked_ca else 'injected-runtime-ca'
                        report['status'] = 'passed'
                    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
                        report['error'] = str(error)
                        failed = True
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        failed = True
        for report in evidence.values():
            report['error'] = str(error)
    finally:
        for arch, report in evidence.items():
            (reports / f'runtime-{framework}-{arch}.json').write_text(
                json.dumps(report, indent=2) + '\n')
    return int(failed)


def plan(requested):
    """Quais frameworks do lote podem ter o contrato executado neste run.

    Um contrato compilado precisa do par `-dev` **do mesmo run**: o estágio de
    build é o artifact candidato, não uma imagem de registry. Se o lote não
    inclui o par (um `workflow_dispatch` só com `go1-26`, por exemplo), o
    contrato não roda — e o motivo fica registrado, nunca some da tabela.
    """
    planned, skipped = [], {}
    for framework in requested:
        try:
            kind = supported(framework)
        except ValueError as error:
            skipped[framework] = f'sem contrato funcional: {error}'
            continue
        if kind == 'compiled':
            dev = project(framework)[1]
            if dev not in requested:
                skipped[framework] = (f'contrato compilado exige {dev} no mesmo lote: '
                                      'o estágio de build é o artifact candidato')
                continue
        planned.append(framework)
    return planned, skipped


def publication_contract(framework, requested):
    """Resolve a publication target to its required executable contract.

    Functional planning may skip a compiled build companion, but publication
    of either member requires the same complete runtime/build pair. Keep that
    authorization decision separate from the generic plan's gradual coverage.
    """
    if (not isinstance(requested, list) or not requested
            or any(not isinstance(item, str) for item in requested)):
        raise ValueError('publication requires a non-empty requested framework list')
    if len(requested) != len(set(requested)):
        raise ValueError('publication requested frameworks must be unique')
    catalog_names = {path.stem for path in (ROOT / 'frameworks').glob('*.yaml')}
    for item in requested:
        if item not in catalog_names:
            raise ValueError('publication framework must exist in the repository catalog')
    if not isinstance(framework, str) or framework not in requested:
        raise ValueError('publication framework must belong to the requested batch')

    base = framework.removesuffix('-dev')
    compiled = any(re.fullmatch(pattern, base) for pattern, _, _ in COMPILED)
    if compiled:
        # project() also requires both catalog definitions; an absent catalog
        # companion must not turn a compiled artifact into optional coverage.
        _, dev, _ = project(base)
        if base not in requested or dev not in requested:
            raise ValueError(f'publication of {framework} requires {base} and {dev} '
                             'in the same requested batch')
        role = 'dev' if framework == dev else 'runtime'
        return {'required': True, 'publication_framework': framework,
                'contract_framework': base, 'runtime_framework': base,
                'dev_framework': dev, 'target_role': role,
                'counterpart_framework': base if role == 'dev' else dev}

    # A direct executable contract authorizes interpreted candidates. Unknown
    # coverage remains a planning concern and cannot authorize publication.
    supported(framework)
    return {'required': True, 'publication_framework': framework,
            'contract_framework': framework, 'runtime_framework': framework,
            'dev_framework': '', 'target_role': 'runtime',
            'counterpart_framework': ''}


def gate(reports, framework, layout=None, artifact_metadata=None, job_metadata=None,
         run_id=None, attempt=None, repository=None, revision=None, dev_layout=None,
         download_result='success'):
    """Fail closed unless same-run reports approve the actual OCI being published."""
    result = {'framework': framework, 'passed': False, 'run_id': run_id,
              'run_attempt': attempt, 'selected_attempt': None}
    try:
        if download_result != 'success':
            raise ValueError('functional artifact download failed or did not run')
        if layout is None or artifact_metadata is None or job_metadata is None:
            raise ValueError('gate requires validated OCI and complete run metadata')
        _, expected = verified_layout(layout)
        dev_expected = None
        if supported(framework) == 'compiled':
            if dev_layout is None:
                raise ValueError('compiled gate requires the current validated build variant')
            _, dev_expected = verified_layout(dev_layout)
        artifact_document, _ = contract_evidence.read_json(artifact_metadata)
        job_document, _ = contract_evidence.read_json(job_metadata)
        result = contract_evidence.select(reports, framework, expected, run_id, attempt,
                                          repository, revision, artifact_document,
                                          job_document, dev_expected)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        result['error'] = str(error)
    return result


def publication_gate(reports, framework, requested, layout=None, counterpart_layout=None,
                     artifact_metadata=None, job_metadata=None, run_id=None, attempt=None,
                     repository=None, revision=None, download_result='success'):
    """Authorize the current target using canonical runtime/dev pair evidence."""
    result = {'publication_framework': framework, 'passed': False, 'run_id': run_id,
              'run_attempt': attempt, 'selected_attempt': None}
    try:
        resolution = publication_contract(framework, requested)
    except (OSError, ValueError, TypeError) as error:
        result['error'] = str(error)
        return result
    result.update(resolution)
    if resolution['dev_framework']:
        if layout is None or counterpart_layout is None:
            result['error'] = 'compiled publication requires both current validated OCI layouts'
            return result
        runtime_layout, dev_layout = ((counterpart_layout, layout)
                                     if resolution['target_role'] == 'dev'
                                     else (layout, counterpart_layout))
    else:
        runtime_layout, dev_layout = layout, None
    result.update(gate(reports, resolution['contract_framework'], runtime_layout,
                       artifact_metadata, job_metadata, run_id, attempt, repository,
                       revision, dev_layout, download_result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layout', nargs='?',
                        help='runtime OCI layout, or current publication target with --publication-gate')
    parser.add_argument('framework', nargs='?')
    parser.add_argument('--dev-layout', help='layout OCI da variante -dev (contratos compilados)')
    parser.add_argument('--counterpart-layout',
                        help='current validated paired OCI layout for publication authorization')
    parser.add_argument('--reports', default='reports')
    parser.add_argument('--baked-ca', help='isolated fixture TLS identity prefix (.pem/.key)')
    # 600s por plataforma: o build multi-stage mais lento observado foi 19,3s
    # (amd64 emulado por Rosetta). Margem grande para o QEMU do runner, mas
    # ainda dentro do timeout do job — o erro do script é mais legível que um
    # job morto por limite de duração.
    parser.add_argument('--build-timeout', type=int, default=600)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--list-contracts', action='store_true',
                      help='lista os frameworks com contrato funcional e sai')
    mode.add_argument('--gate', metavar='FRAMEWORK',
                      help='avalia os relatórios de --reports e falha se o contrato não passou')
    mode.add_argument('--publication-plan', metavar='FRAMEWORK',
                      help='resolve the publication target to its required functional contract')
    mode.add_argument('--publication-gate', metavar='FRAMEWORK',
                      help='authorize publication of the current target OCI and its exact pair')
    mode.add_argument('--plan', metavar='JSON',
                      help='imprime o plano de contratos para um lote de frameworks')
    parser.add_argument('--requested', metavar='JSON', default=None,
                        help='lote de frameworks do run; obrigatório para autorização de publicação')
    parser.add_argument('--artifact-metadata', help='complete run artifact API pages')
    parser.add_argument('--job-metadata', help='complete run job API pages (filter=all)')
    parser.add_argument('--run-id', default=os.environ.get('GITHUB_RUN_ID'))
    parser.add_argument('--run-attempt', default=os.environ.get('GITHUB_RUN_ATTEMPT'))
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--revision', default=os.environ.get('GITHUB_SHA'))
    parser.add_argument('--download-result', default='success')
    parser.add_argument('--gate-output', help='store the publication gate decision as JSON')
    args = parser.parse_args()
    if args.list_contracts:
        print(json.dumps(contracts()))
        return 0
    if args.plan:
        planned, skipped = plan(json.loads(args.plan))
        print(json.dumps({'planned': planned, 'skipped': skipped}, indent=2))
        return 0
    if args.publication_plan or args.publication_gate:
        if args.requested is None:
            parser.error('--requested is required for publication authorization')
        framework = args.publication_plan or args.publication_gate
        try:
            requested = json.loads(args.requested)
            if args.publication_plan:
                result = publication_contract(framework, requested)
            else:
                result = publication_gate(
                    args.reports, framework, requested, args.layout, args.counterpart_layout,
                    args.artifact_metadata, args.job_metadata, args.run_id, args.run_attempt,
                    args.repository, args.revision, args.download_result)
        except (OSError, ValueError, TypeError) as error:
            result = {'publication_framework': framework, 'passed': False, 'error': str(error)}
        if args.gate_output:
            Path(args.gate_output).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        if args.publication_gate:
            return int(result.get('passed') is not True)
        return int(result.get('required') is not True)
    if args.gate:
        requested = json.loads(args.requested) if args.requested else [args.gate]
        planned, skipped = plan(requested)
        if args.gate in skipped:
            # Cobertura gradual explícita: o motivo aparece no log e na tabela
            # do run. Não é aprovação silenciosa por ausência de evidência.
            print(f'{args.gate}: contrato funcional não executado — {skipped[args.gate]}')
            if args.gate_output:
                Path(args.gate_output).write_text(json.dumps(
                    {'framework': args.gate, 'passed': None, 'status': 'not_required',
                     'reason': skipped[args.gate]}, indent=2) + '\n')
            return 0
        if args.gate not in planned:
            print(f'{args.gate}: fora do lote informado em --requested')
            return 1
        result = gate(args.reports, args.gate, args.layout, args.artifact_metadata,
                      args.job_metadata, args.run_id, args.run_attempt, args.repository,
                      args.revision, args.dev_layout, args.download_result)
        if args.gate_output:
            Path(args.gate_output).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return int(not result['passed'])
    if not args.layout or not args.framework:
        parser.error('layout e framework são obrigatórios')
    dev_layout = args.dev_layout if args.dev_layout and Path(args.dev_layout).is_dir() else None
    return run(args.layout, args.framework, args.reports, dev_layout, args.build_timeout, args.baked_ca)


if __name__ == '__main__':
    raise SystemExit(main())
