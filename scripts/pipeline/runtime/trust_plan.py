"""Plan default-trust fixtures without building outside the requested batch.

Compiled contracts exercise a runtime and its dev image together. Both must
be explicitly requested before they collapse to one runtime fixture. Node
dev images are independent interpreted fixtures, just like Node runtimes.
"""
import json
import os
import re
import sys

from scripts.pipeline.runtime import runtime_images


def plan(requested):
    """Return sorted unique fixture names for a nonempty JSON catalog batch."""
    if not isinstance(requested, str):
        raise ValueError('requested frameworks must be a JSON string')
    names = json.loads(requested)
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) for name in names)):
        raise ValueError('requested frameworks must be a nonempty array of names')
    # Duplicates do not add fixtures. Exact catalog membership is the input
    # whitelist; supported() below also requires an executable runtime contract.
    names = sorted(set(names))
    catalog = {path.stem for path in (runtime_images.ROOT / 'frameworks').glob('*.yaml')
               if path.is_file()}
    if not set(names) <= catalog:
        raise ValueError('requested frameworks must be names from the catalog')
    selected = set(names)
    fixtures = set()
    expanded = set()
    for name in names:
        fixture = name
        if name.endswith('-dev'):
            base = name.removesuffix('-dev')
            if any(re.fullmatch(pattern, base)
                   for pattern, _, _ in runtime_images.COMPILED):
                if base not in selected:
                    raise ValueError('compiled dev trust requires its runtime in the batch')
                fixture = base
        # Unlike the artifact runtime planner, unsupported or incomplete
        # selections are errors: an empty or skipped trust gate cannot pass.
        kind = runtime_images.supported(fixture)
        if kind == 'compiled':
            dev = runtime_images.project(fixture)[1]
            if dev not in selected:
                raise ValueError('compiled runtime trust requires its dev image in the batch')
            # Match certificate_contract.check's actual build expansion,
            # independently of the project metadata used to validate a pair.
            expanded.add(fixture + '-dev')
        elif kind != 'interpreted':
            raise ValueError('requested framework has no default-trust contract')
        fixtures.add(fixture)
        expanded.add(fixture)
    if not fixtures:
        raise ValueError('default-trust plan cannot be empty')
    if expanded != selected:
        raise ValueError('trust fixture builds must cover exactly the requested batch')
    return sorted(fixtures)


def main():
    try:
        fixtures = plan(os.environ['FRAMEWORKS'])
    except (KeyError, OSError, TypeError, ValueError):
        # Do not echo untrusted input or emit a usable matrix on failure.
        print('Invalid trust plan: request catalog names with complete compiled '
              'runtime/dev pairs and supported trust contracts.', file=sys.stderr)
        return 1
    print(json.dumps(fixtures, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
