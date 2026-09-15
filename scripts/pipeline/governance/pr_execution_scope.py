"""Resolve the validation profile for a pull request.

The default is fail-safe: anything outside the explicitly enumerated
P0-04-only paths selects FULL. This resolver never changes the catalog.
"""
import argparse
import json
import sys


P0_04 = 'P0_04'
FULL = 'FULL'
P0_04_FRAMEWORKS = ['go1-26', 'go1-26-dev']

# Paths whose behavior is limited to the P0-04 Go candidate. Every other
# product/runtime/orchestration path is shared-impact and selects FULL.
P0_ONLY_FILES = frozenset({
    'frameworks/go1-26.yaml',
    'frameworks/go1-26-dev.yaml',
})
P0_ONLY_PREFIXES = ('tests/runtime/projects/go/',)
DOC_PREFIXES = ('docs/', 'specs/')


def _is_p0_only(path: str) -> bool:
    return path in P0_ONLY_FILES or path.startswith(P0_ONLY_PREFIXES)


def profile_for_paths(paths):
    """Return ``P0_04`` only when every changed path is safely P0-specific."""
    normalized = [str(path).replace('\\', '/') for path in paths if str(path)]
    if not normalized:
        return FULL
    for path in normalized:
        if _is_p0_only(path) or path.startswith(DOC_PREFIXES):
            continue
        return FULL
    return P0_04


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paths-file', type=argparse.FileType('r'),
                        default=sys.stdin)
    args = parser.parse_args()
    paths = [line.strip() for line in args.paths_file if line.strip()]
    profile = profile_for_paths(paths)
    print(f'profile={profile}')
    print(f'frameworks={json.dumps(P0_04_FRAMEWORKS if profile == P0_04 else None)}')


if __name__ == '__main__':
    main()
