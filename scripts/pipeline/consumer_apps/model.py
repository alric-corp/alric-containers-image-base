"""Versioned consumer scenarios; these do not define release promotion units."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
CATALOG = (
    'dotnet10', 'dotnet10-dev', 'go1-25', 'go1-25-dev', 'go1-26', 'go1-26-dev',
    'java21', 'java21-dev', 'java25', 'java25-dev', 'nodejs22', 'nodejs22-dev',
    'nodejs24', 'nodejs24-dev', 'python3-13', 'python3-14',
)
ARCHITECTURES = ('amd64', 'arm64')
SCENARIOS = tuple(
    {'framework': framework, 'family': family, 'dev_framework': dev,
     'expected_version': version}
    for framework, family, dev, version in (
        ('dotnet10', 'dotnet', 'dotnet10-dev', '10'),
        ('go1-25', 'go', 'go1-25-dev', '1.25'),
        ('go1-26', 'go', 'go1-26-dev', '1.26'),
        ('java21', 'java', 'java21-dev', '21'),
        ('java25', 'java', 'java25-dev', '25'),
        ('nodejs22', 'node', 'nodejs22-dev', '22'),
        ('nodejs24', 'node', 'nodejs24-dev', '24'),
        ('python3-13', 'python', None, '3.13'),
        ('python3-14', 'python', None, '3.14'),
    )
)
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
REGISTRY = re.compile(r'[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?')


def scenario(framework):
    for item in SCENARIOS:
        if item['framework'] == framework:
            return dict(item)
    raise ValueError(f'unknown consumer application scenario: {framework}')


def validate_inventory(document):
    """Validate every identity again at the unprivileged execution boundary."""
    if type(document.get('schema_version')) is not int or document['schema_version'] != 1:
        raise ValueError('unsupported candidate inventory schema')
    run = document.get('source_run_id')
    if (type(run) is not int or run <= 0 or type(document.get('source_run_attempt')) is not int
            or document['source_run_attempt'] != 1):
        raise ValueError('inventory must identify one source run and attempt 1')
    if not re.fullmatch(r'[0-9a-f]{40}', document.get('source_sha', '')):
        raise ValueError('inventory source revision must be a full Git SHA')
    candidates = document.get('candidates', {})
    if set(candidates) != set(CATALOG):
        raise ValueError('inventory must cover exactly the 16 catalog artifacts')
    registries = set()
    for framework, item in candidates.items():
        digest = item.get('digest', '')
        repository = f'image-base-{framework}'
        ref = item.get('image_ref', '')
        registry, separator, path = ref.partition('/')
        if (not DIGEST.fullmatch(digest) or not REGISTRY.fullmatch(registry)
                or not separator or path != f'{repository}@{digest}'
                or item.get('framework') != framework or item.get('repository') != repository):
            raise ValueError(f'invalid immutable candidate identity: {framework}')
        tag = item.get('immutable_tag', '')
        if not re.fullmatch(rf'[0-9]{{6}}-[0-9]{{4}}-r{run}-a1', tag):
            raise ValueError(f'candidate tag does not bind source run/attempt: {framework}')
        platforms = item.get('platforms', {})
        if set(platforms) != set(ARCHITECTURES) or any(
                not isinstance(value, str) or not DIGEST.fullmatch(value) for value in platforms.values()):
            raise ValueError(f'candidate needs exact amd64 and arm64 manifests: {framework}')
        if len(set(platforms.values())) != 2:
            raise ValueError(f'candidate platform manifests are ambiguous: {framework}')
        if not item.get('imagePushedAt'):
            raise ValueError(f'candidate lacks ECR push timestamp: {framework}')
        registries.add(registry)
    if len(registries) != 1:
        raise ValueError('candidate inventory spans different ECR registries')
    return document
