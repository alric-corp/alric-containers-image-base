#!/usr/bin/env python3
"""Exercise a CA baked by Melange/Apko through each runtime's default trust.

The temporary image has a TEST CA with an ephemeral private key. It never uses
the validated-oci artifact namespace and cannot be submitted for publication.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.certificates.prepare_anchors import stage, verify
from scripts.pipeline.governance.wolfi_trust import require_key
from scripts.pipeline.runtime.runtime_images import supported, run, command


def check(framework, reports):
    require_key(ROOT)
    compiled = supported(framework) == 'compiled'
    reports = Path(reports).resolve()
    date = command('git', 'show', '-s', '--format=%cI', 'HEAD')
    with tempfile.TemporaryDirectory(prefix='.composition-fixture-', dir=ROOT) as temporary:
        workspace = Path(temporary)
        for directory in ('frameworks', 'distroless'):
            shutil.copytree(ROOT / directory, workspace / directory)
        # A composição resolve a fonte de pacotes pela policy versionada, e o
        # build a exige antes de resolver — a fixture precisa carregá-la junto.
        shutil.copytree(ROOT / 'policies/sources', workspace / 'policies/sources')
        melange = workspace / 'melange'
        melange.mkdir()
        # Melange needs root inside its build sandbox. Own the output directories
        # on the host so cleanup can unlink the root-created APK/index files.
        for arch in ('x86_64', 'aarch64'):
            (melange / 'packages' / arch).mkdir(parents=True)
        shutil.copy(ROOT / 'melange/image-base-ca-certificates.yaml', melange)
        shutil.copytree(ROOT / 'melange/keys', melange / 'keys')
        require_key(workspace)
        identity = workspace / 'trusted'
        command('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-keyout', str(identity) + '.key', '-out', str(identity) + '.pem',
                '-subj', '/CN=host.docker.internal/OU=runtime-test',
                '-addext', 'subjectAltName=DNS:host.docker.internal',
                '-addext', 'basicConstraints=critical,CA:TRUE')
        stage(str(identity) + '.pem', melange / 'certificates', allow_test=True)
        verify(melange / 'certificates', allow_test=True)
        # Normal release preparation must reject this very same trust input.
        try:
            verify(melange / 'certificates')
        except ValueError:
            pass
        else:
            raise ValueError('fixture trust unexpectedly accepted for release')
        docker = ['docker', 'run', '--rm', '--privileged', '-v', f'{melange}:/work',
                  '-w', '/work', os.environ['MELANGE_IMAGE']]
        subprocess.run(docker + ['keygen', 'melange.rsa'], check=True)
        for arch in ('x86_64', 'aarch64'):
            subprocess.run(docker + ['build', 'image-base-ca-certificates.yaml', '--arch', arch,
                                    '--signing-key', 'melange.rsa', '--build-date', date], check=True)
        environment = dict(os.environ, PYTHONPATH=str(ROOT))
        for candidate in ([framework, framework + '-dev'] if compiled else [framework]):
            subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.artifacts.build_image',
                            candidate, candidate + '.oci', '--engine', 'docker',
                            '--repository', 'melange/packages', '--keyring', 'melange/melange.rsa.pub'],
                           cwd=workspace, env=environment, check=True)
            subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.artifacts.oci_artifact',
                            'prepare', candidate + '.oci'], cwd=workspace, env=environment, check=True)
        return run(workspace / (framework + '.oci'), framework, reports,
                   workspace / (framework + '-dev.oci') if compiled else None, baked_ca=identity)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('framework')
    parser.add_argument('--reports', default='reports/certificate-contract')
    args = parser.parse_args()
    raise SystemExit(check(**vars(args)))
