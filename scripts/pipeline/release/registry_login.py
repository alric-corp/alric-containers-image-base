"""Use region-specific ECR tokens; never print tokens or pass them as argv."""
import subprocess

from scripts.pipeline.release.release_manifest import configuration, registry
from scripts.pipeline.release.release_store import command


def main():
    for environment in ('DEV', 'HOM'):
        token = command('aws', 'ecr', 'get-login-password', '--region', configuration()[environment]['region'])
        subprocess.run(['docker', 'login', '--username', 'AWS', '--password-stdin', registry(environment)],
                       input=token, check=True, capture_output=True, timeout=60)


if __name__ == '__main__':
    main()
