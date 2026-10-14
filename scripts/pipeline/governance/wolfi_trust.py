"""Offline integrity of the explicitly configured Wolfi public key.

The adjacent JSON is the single executable source of the expected SHA-256.
Within this module only monitoring reads remotely; neither path updates the
local key/pin. Apko's own key discovery is separate and remains enabled.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
KEY = Path('melange/keys/wolfi-signing.rsa.pub')
POLICY = KEY.with_name('wolfi-signing-key.json')
MAX_KEY_BYTES = 16384
# The pinned Apko also discovers keys from every http(s) repository, so the
# repository set is part of the reviewed trust surface, like the keyring.
REPOSITORIES = ['https://packages.wolfi.dev/os']
# Not part of the reviewed model: extra build/runtime origins, and a base
# image whose package index Apko installs without signature verification.
UNREVIEWED_FIELDS = ('build_repositories', 'runtime_repositories', 'baseimage')
# Build entrypoints must not bypass the reviewed configuration: no disabled
# signature checks, no untrusted APKs, no remote key/repository appended by CLI.
INSECURE_FALLBACK = re.compile(
    r'--(?:ignore-signatures|allow-untrusted)\b'
    r'|--(?:keyring|repository)-append(?:=|["\',\s]+)https?://'
    r'|\b(?:keyring|repository)\s*=\s*["\']https?://'
    r'|add_argument\(\s*["\']--(?:keyring|repository)["\'][^)]*default\s*=\s*["\']https?://')


def local_pin(root=None, run=None):
    """Inventory record, including explicit local failures; never uses network."""
    root = Path(root) if root is not None else ROOT
    run = run or subprocess.run
    record = {'kind': 'local-key', 'name': 'wolfi-signing-key', 'file': str(POLICY),
              'key_file': str(KEY), 'current': '', 'expected_sha256': None,
              'actual_sha256': None, 'pinned': False, 'managers': ['human-review'],
              'errors': []}
    try:
        policy = json.loads((root / POLICY).read_text())
        expected = policy.get('expected_sha256')
        if policy.get('name') != record['name'] or not isinstance(expected, str) \
                or not re.fullmatch(r'[0-9a-f]{64}', expected):
            raise ValueError('invalid name or expected_sha256')
        record.update(expected_sha256=expected, current='sha256:' + expected, pinned=True,
                      origin=policy['sources']['distribution'])
        if not isinstance(record['origin'], str) or not record['origin'].startswith('https://'):
            raise ValueError('monitor source must use HTTPS')
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        record['errors'].append(f'{POLICY}: invalid or missing policy ({error})')
    try:
        path = root / KEY
        if path.is_symlink():
            raise ValueError('key must be a regular repository file, not a symlink')
        data = path.read_bytes()
        record['actual_sha256'] = hashlib.sha256(data).hexdigest()
        if record['actual_sha256'] != record['expected_sha256']:
            record['errors'].append(f'{KEY}: SHA-256 mismatch')
        # Reject extra PEM blocks/private keys/trailing text before asking
        # OpenSSL to parse RSA SPKI. Do not implement cryptographic parsing.
        if len(data) > MAX_KEY_BYTES or not re.fullmatch(
                rb'-----BEGIN PUBLIC KEY-----\r?\n[A-Za-z0-9+/=\r\n]+-----END PUBLIC KEY-----\r?\n?', data):
            raise ValueError('expected exactly one RSA PUBLIC KEY in SPKI PEM format')
        result = run(['openssl', 'rsa', '-pubin', '-noout'], input=data,
                     capture_output=True, check=False, timeout=10)
        if result.returncode:
            raise ValueError('invalid RSA public key format')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        record['errors'].append(f'{KEY}: invalid or missing key ({error})')
    return record


def require_key(root=None):
    """Fail closed before Apko/Melange; no PyYAML or remote dependency."""
    record = local_pin(root)
    if record['errors']:
        raise ValueError('; '.join(record['errors']))
    return record


def config_errors(root=None):
    """Check the product's trust surface (keyring, origins, includes) with PyYAML."""
    import yaml
    root = Path(root) if root is not None else ROOT
    errors = []
    required = {root / 'distroless/image-base.yaml',
                root / 'melange/image-base-ca-certificates.yaml'}
    paths = set(required)

    def found(value, field):
        if isinstance(value, dict):
            for name, child in value.items():
                if name == field:
                    yield child
                yield from found(child, field)
        elif isinstance(value, list):
            for child in value:
                yield from found(child, field)

    for directory in ('distroless', 'frameworks', 'melange'):
        for extension in ('*.yaml', '*.yml'):
            paths.update((root / directory).rglob(extension))
    # Apko resolves include paths itself: only scanned shared configurations
    # keep the included keyring/repositories inside this check.
    includable = {path.relative_to(root).as_posix() for path in paths if path.parent == root / 'distroless'}
    for path in sorted(paths):
        relative = path.relative_to(root)
        expected = str(KEY.relative_to('melange')) if relative.parts[0] == 'melange' else str(KEY)
        try:
            document = yaml.safe_load(path.read_text())
            contents = (document.get('environment') or {}).get('contents') \
                if relative.parts[0] == 'melange' else document.get('contents')
            keyring = (contents or {}).get('keyring')
            if (path in required and keyring != [expected]) \
                    or any(value != [expected] for value in found(document, 'keyring')):
                errors.append(f'{relative}: keyring must be exactly the local key [{expected}]')
            if (path in required and (contents or {}).get('repositories') != REPOSITORIES) \
                    or any(value != REPOSITORIES for value in found(document, 'repositories')):
                errors.append(f'{relative}: repositories must be exactly {REPOSITORIES}')
            for field in UNREVIEWED_FIELDS:
                if any(True for _ in found(document, field)):
                    errors.append(f'{relative}: {field} is outside the reviewed trust surface')
            if 'include' in document and document['include'] not in includable:
                errors.append(f'{relative}: include must name a scanned distroless/ configuration')
        except (OSError, ValueError, AttributeError, TypeError, yaml.YAMLError) as error:
            errors.append(f'{relative}: cannot verify local trust surface ({error})')
    return errors + insecure_fallback_errors(root)


def insecure_fallback_errors(root=None):
    """Scan the build entrypoints (not tests or docs) for trust bypasses."""
    root = Path(root) if root is not None else ROOT
    paths = {root / 'Makefile', *(root / '.github/workflows').glob('*.yml')}
    for directory in ('scripts', 'distroless', 'frameworks', 'melange'):
        for pattern in ('*.py', '*.sh', '*.yaml', '*.yml'):
            paths.update((root / directory).rglob(pattern))
    paths.discard(root / 'scripts/pipeline/governance/wolfi_trust.py')  # Defines the patterns.
    errors = []
    for path in sorted(path for path in paths if path.is_file()):
        text = path.read_text(errors='replace')
        for match in INSECURE_FALLBACK.finditer(text):
            line = text.count('\n', 0, match.start()) + 1
            errors.append(f'{path.relative_to(root)}:{line}: signature/trust fallback is not allowed ({match[0].strip()})')
    return errors


def lock_observation(raw, root=None):
    """Detection only: keys and origins recorded by one resolved Apko lock.

    The pinned Apko records the configured keys plus those its own discovery
    request found; the resolver's discovery is a separate request, and
    --keyring-append keys are not recorded. PINNED_ONLY therefore shows that
    no extra key was offered to the lock's request, not that every resolved
    index could only verify with the local key. No caller gates on this.
    """
    root = Path(root) if root is not None else ROOT
    record = {'status': 'INVALID', 'keyring': [], 'repositories': [], 'problems': []}
    try:
        contents = json.loads(raw)['contents']
        record['keyring'] = [entry['url'] for entry in contents['keyring']]
        record['repositories'] = [entry['url'] for entry in contents['repositories']]
        local = (root / KEY).read_bytes()
        if [(entry['name'], entry['url'], entry['content'].encode()) for entry in contents['keyring']] \
                != [(str(KEY), str(KEY), local)]:
            record['problems'].append('keyring is not exactly the pinned local key')
        indexes = {f'{origin}/{arch}/APKINDEX.tar.gz' for origin in REPOSITORIES for arch in ('x86_64', 'aarch64')}
        if not set(record['repositories']) <= indexes or contents['build_repositories'] \
                or contents['runtime_repositories']:
            record['problems'].append('repository outside the reviewed origin')
        origins = tuple(origin + '/' for origin in REPOSITORIES) + ('melange-repo/packages/',)
        if any(not package['url'].startswith(origins) for package in contents['packages']):
            record['problems'].append('package from an unreviewed origin')
        # Apko installs locked packages by their Q1 control hash; without it nothing is pinned.
        if not contents['packages'] or any(not re.fullmatch(r'Q1[A-Za-z0-9+/]{27}=', str(package.get('checksum')))
                                           for package in contents['packages']):
            record['problems'].append('package without a pinned Q1 checksum')
        record['status'] = 'UNEXPECTED' if record['problems'] else 'PINNED_ONLY'
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        record['problems'].append(f'unreadable lock ({error})')
    return record


def upstream_status(entry, fetch=None):
    """Detection only: missing/unreachable upstream is an operational failure."""
    record = dict(entry, available=False, remote_status='local-invalid', remote_sha256=None)
    if entry['errors']:
        return record
    try:
        if fetch is None:
            with urlopen(entry['origin'], timeout=20) as response:
                data = response.read(MAX_KEY_BYTES + 1)
        else:
            data = fetch(entry['origin'])
        if len(data) > MAX_KEY_BYTES:
            raise ValueError('upstream key exceeds size limit')
        digest = hashlib.sha256(data).hexdigest()
        same = digest == entry['actual_sha256'] == entry['expected_sha256']
        record.update(remote_sha256=digest, remote_status='same' if same else 'divergent',
                      available=same)
    except (OSError, ValueError, TimeoutError) as error:
        record.update(remote_status='unavailable', remote_error=str(error))
    return record
