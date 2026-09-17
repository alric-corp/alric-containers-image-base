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
    """Keyring rules of the product.

    The Melange build environment is Wolfi and stays pinned to exactly the local
    Wolfi key. Image composition (distroless/, frameworks/) is no longer required
    to be Wolfi: each framework must satisfy the trust contract of the source its
    include chain resolves to, which source_trust validates and fails closed on.
    """
    import yaml
    from scripts.pipeline.governance import source_trust
    root = Path(root) if root is not None else ROOT
    errors = []
    required = {root / 'melange/image-base-ca-certificates.yaml'}
    paths = set(required)

    def keyrings(value):
        if isinstance(value, dict):
            for name, child in value.items():
                if name == 'keyring':
                    yield child
                yield from keyrings(child)
        elif isinstance(value, list):
            for child in value:
                yield from keyrings(child)

    for extension in ('*.yaml', '*.yml'):
        paths.update((root / 'melange').rglob(extension))
    expected = str(KEY.relative_to('melange'))
    for path in sorted(paths):
        relative = path.relative_to(root)
        try:
            document = yaml.safe_load(path.read_text())
            contents = (document.get('environment') or {}).get('contents')
            keyring = (contents or {}).get('keyring')
            if (path in required and keyring != [expected]) \
                    or any(value != [expected] for value in keyrings(document)):
                errors.append(f'{relative}: keyring must be exactly the local key [{expected}]')
        except (OSError, ValueError, AttributeError, yaml.YAMLError) as error:
            errors.append(f'{relative}: cannot verify local keyring ({error})')
    return errors + source_trust.framework_errors(root)


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
