"""Trust contract per package source.

Wolfi is the default source. Any other source is an explicit, reviewed
exception: a framework may only use it if the policy authorises that framework
by name. Two independent checks run before anything is built:

- composition: the repositories/keyring a framework resolves to through its
  apko `include` chain must match exactly one declared source, and that source
  must be the one authorised for it;
- effective keyring: apko unions keys it discovers over the network with the
  declared keyring and offers no knob to disable that, so every key it ended up
  trusting must be byte-identical to a pinned key of that source and, when
  discovered, must come from an allowed origin.

Both fail closed. There is no fallback between sources.
"""
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY = Path('policies/sources/package-sources.json')
MAX_KEY_BYTES = 16384
MAX_INCLUDE_DEPTH = 10


def load_policy(root=None):
    root = Path(root) if root is not None else ROOT
    policy = json.loads((root / POLICY).read_text())
    if policy.get('default') not in (policy.get('sources') or {}):
        raise ValueError('default source is not declared in sources')
    return policy


def source_for(policy, framework):
    return (policy.get('framework_sources') or {}).get(framework, {}).get(
        'source', policy['default'])


def resolve_config(path, root):
    """Resolve an apko config through its include chain.

    Mirrors apko: `include` is a single string and list fields are APPENDED by
    the includer, never overridden (verified against `apko show-config`).
    """
    root = Path(root).resolve()
    chain, current, depth = [], Path(path), 0
    while current is not None:
        if depth > MAX_INCLUDE_DEPTH:
            raise ValueError('include chain too deep (possible cycle)')
        resolved = (root / current).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f'include escapes the repository: {current}')
        if not resolved.is_file():
            raise ValueError(f'include target not found: {current}')
        document = yaml.safe_load(resolved.read_text()) or {}
        chain.append(document)
        included = document.get('include')
        if included is not None and not isinstance(included, str):
            raise ValueError('include must be a single string (apko does not accept a list)')
        current = Path(included) if included else None
        depth += 1
    repositories, keyring = [], []
    for document in reversed(chain):
        contents = document.get('contents') or {}
        repositories += list(contents.get('repositories') or [])
        keyring += list(contents.get('keyring') or [])
    return repositories, keyring


def match_source(policy, repositories, keyring):
    """Exact match against a declared source; no partial or prefix matching."""
    for name, source in policy['sources'].items():
        if list(source['repositories']) == list(repositories) \
                and list(source['keyring']) == list(keyring):
            return name
    return None


def key_errors(root, source_name, source):
    errors = []
    for relative, expected in (source.get('keys') or {}).items():
        path = root / relative
        try:
            if path.is_symlink():
                raise ValueError('key must be a regular repository file, not a symlink')
            data = path.read_bytes()
            if len(data) > MAX_KEY_BYTES:
                raise ValueError('key exceeds size limit')
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                raise ValueError(f'SHA-256 mismatch (expected {expected}, got {actual})')
        except (OSError, ValueError) as error:
            errors.append(f'{source_name}: {relative}: {error}')
    for relative in source['keyring']:
        if relative not in (source.get('keys') or {}):
            errors.append(f'{source_name}: {relative}: keyring entry has no pinned SHA-256')
    return errors


def framework_errors(root=None):
    """Validate every catalog framework against the source trust contract."""
    root = Path(root).resolve() if root is not None else ROOT
    errors = []
    try:
        policy = load_policy(root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        return [f'{POLICY}: invalid or missing source policy ({error})']
    declared = policy.get('framework_sources') or {}
    for unknown in sorted(set(declared) - {p.stem for p in (root / 'frameworks').glob('*.yaml')}):
        errors.append(f'{unknown}: framework_sources entry has no framework in the catalog')
    for path in sorted((root / 'frameworks').glob('*.yaml')):
        framework = path.stem
        expected = source_for(policy, framework)
        if expected not in policy['sources']:
            errors.append(f'{framework}: unknown source {expected!r} in policy')
            continue
        try:
            repositories, keyring = resolve_config(path.relative_to(root), root)
        except (OSError, ValueError, yaml.YAMLError) as error:
            errors.append(f'{framework}: cannot resolve composition ({error})')
            continue
        if not repositories or not keyring:
            errors.append(f'{framework}: no package source resolved (repositories/keyring empty)')
            continue
        matched = match_source(policy, repositories, keyring)
        if matched is None:
            errors.append(f'{framework}: repositories/keyring do not match any declared source '
                          f'(repositories={repositories}, keyring={keyring})')
            continue
        if matched != expected:
            errors.append(f'{framework}: resolves to source {matched!r} but the policy '
                          f'authorises {expected!r}; a non-default source must be explicit')
            continue
        errors += key_errors(root, matched, policy['sources'][matched])
    return errors


def require_sources(root=None):
    """Fail closed before Apko/Melange."""
    errors = framework_errors(root)
    if errors:
        raise ValueError('; '.join(errors))
    return True


def effective_keyring(lock):
    """Keys Apko actually trusted, as recorded in apko.lock.json."""
    document = json.loads(Path(lock).read_text()) if not isinstance(lock, dict) else lock
    return document.get('contents', {}).get('keyring', []) or []


def keyring_errors(lock, framework, root=None):
    """Every effective key must be a pinned key, from an allowed origin."""
    root = Path(root).resolve() if root is not None else ROOT
    problems = []
    try:
        policy = load_policy(root)
        name = source_for(policy, framework)
        source = policy['sources'][name]
        pinned = {digest: path for path, digest in (source.get('keys') or {}).items()}
        keys = effective_keyring(lock)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return [f'{framework}: cannot evaluate the effective keyring ({error})']
    if not keys:
        return [f'{framework}: effective keyring is empty']
    seen = set()
    for key in keys:
        content = key.get('content')
        if not isinstance(content, str) or not content.strip():
            problems.append(f'{framework}: keyring entry {key.get("name")!r} has no content')
            continue
        digest = hashlib.sha256(content.encode()).hexdigest()
        url = str(key.get('url', ''))
        remote = url.startswith('http')
        origin = 'discovered over the network' if remote else 'declared in the repository'
        # Content pinning answers "is this the right key"; the origin allowlist
        # answers "did discovery start pointing somewhere else", which is a
        # signal even when the bytes still match.
        allowed = tuple(source.get('discovery_origins') or ())
        if remote and not url.startswith(allowed):
            problems.append(f'{framework}: key {key.get("name")!r} was discovered at an '
                            f'origin not allowed for source {name!r}: {url}')
            continue
        if digest not in pinned:
            problems.append(f'{framework}: key {key.get("name")!r} ({origin}) is not pinned for '
                            f'source {name!r}: sha256 {digest}')
            continue
        seen.add(digest)
    for digest in sorted(set(pinned) - seen):
        problems.append(f'{framework}: pinned key {pinned[digest]!r} of source {name!r} '
                        'is absent from the effective keyring')
    return problems


def require_keyring(lock, framework, root=None):
    problems = keyring_errors(lock, framework, root)
    if problems:
        raise ValueError('; '.join(problems))
    return True


def inventory(root=None):
    """Which source each framework resolves to, for evidence and the run table."""
    root = Path(root).resolve() if root is not None else ROOT
    policy = load_policy(root)
    report = {}
    for path in sorted((root / 'frameworks').glob('*.yaml')):
        repositories, keyring = resolve_config(path.relative_to(root), root)
        report[path.stem] = {'source': match_source(policy, repositories, keyring),
                             'repositories': repositories, 'keyring': keyring}
    return report


if __name__ == '__main__':
    import sys
    issues = framework_errors()
    for issue in issues:
        print(f'::error::{issue}', file=sys.stderr)
    if issues:
        sys.exit(1)
    print(json.dumps(inventory(), indent=2))
