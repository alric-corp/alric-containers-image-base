"""SBOM completeness against the resolved package lock.

Apko builds the image SPDX by aggregating the per-package SBOM documents that
Melange embeds at /var/lib/db/sbom/ inside each .apk. Packages built by another
distribution's tooling (Alpine's abuild) carry no such document, so Apko has
nothing to aggregate and they are silently absent from the SPDX.

This module does not create a second SBOM pipeline: it completes the document
Apko produced, using the same build's apko.lock.json as the authoritative
inventory, and then asserts that every locked package is represented. The purl
namespace comes from the versioned source policy, never guessed.

The resulting document is therefore APKO + LOCK COMPLETION, not pure Apko
output, and must not be described as the latter.
"""
import argparse
import json
from pathlib import Path

from scripts.pipeline.governance import source_trust

ARCHS = {'x86_64': 'sbom-x86_64.spdx.json', 'aarch64': 'sbom-aarch64.spdx.json'}
PURL_PREFIX = 'pkg:apk/'


def locked_packages(layout, arch):
    lock = json.loads((Path(layout) / 'apko.lock.json').read_text())
    return [p for p in lock['contents']['packages'] if p.get('architecture') == arch]


def represented(document):
    """apk packages already present in the SPDX, by (name, version)."""
    found = set()
    for package in document.get('packages', []):
        for reference in package.get('externalRefs', []):
            if reference.get('referenceType') == 'purl' \
                    and str(reference.get('referenceLocator', '')).startswith(PURL_PREFIX):
                found.add((package.get('name'), package.get('versionInfo')))
    return found


def distribution_of(framework, root):
    """Namespace for the purl, taken from the source the policy authorises."""
    policy = source_trust.load_policy(root)
    name = source_trust.source_for(policy, framework)
    return policy['sources'][name]['distribution']


def spdx_entry(package, arch, distribution):
    name, version = package['name'], package['version']
    url = package.get('url', '')
    # A locally built Melange package keeps the origin Apko already recorded.
    origin = url if url.startswith('http') else 'NOASSERTION'
    return {
        'SPDXID': f'SPDXRef-Package-apk-{name}-{version}',
        'name': name,
        'versionInfo': version,
        'filesAnalyzed': False,
        'licenseConcluded': 'NOASSERTION',
        'licenseDeclared': 'LicenseRef-NOASSERTION',
        'downloadLocation': origin,
        'originator': f'Organization: {distribution}',
        'supplier': f'Organization: {distribution}',
        'copyrightText': 'NOASSERTION',
        'primaryPackagePurpose': 'APPLICATION',
        'externalRefs': [{
            'referenceCategory': 'PACKAGE-MANAGER',
            'referenceType': 'purl',
            'referenceLocator': f'{PURL_PREFIX}{distribution}/{name}@{version}?arch={arch}',
        }],
    }


def complete(layout, framework, root=None):
    """Add the locked packages Apko could not describe. Returns what was added."""
    layout = Path(layout)
    root = Path(root) if root is not None else source_trust.ROOT
    distribution = distribution_of(framework, root)
    added = {}
    for arch, filename in ARCHS.items():
        path = layout / 'sbom' / filename
        document = json.loads(path.read_text())
        known = represented(document)
        image = next((r['spdxElementId'] for r in document.get('relationships', [])
                      if r.get('relationshipType') == 'CONTAINS'), None)
        missing = [p for p in locked_packages(layout, arch)
                   if (p['name'], p['version']) not in known]
        for package in missing:
            entry = spdx_entry(package, arch, distribution)
            document['packages'].append(entry)
            if image:
                document.setdefault('relationships', []).append({
                    'spdxElementId': image,
                    'relationshipType': 'CONTAINS',
                    'relatedSpdxElement': entry['SPDXID'],
                })
        path.write_text(json.dumps(document, indent=2) + '\n')
        added[arch] = [p['name'] for p in missing]
    return added


def errors(layout, root=None):
    """Every locked package for an architecture must appear in that SPDX."""
    layout = Path(layout)
    problems = []
    for arch, filename in ARCHS.items():
        path = layout / 'sbom' / filename
        try:
            document = json.loads(path.read_text())
            locked = locked_packages(layout, arch)
        except (OSError, ValueError, KeyError) as error:
            problems.append(f'{arch}: cannot read SBOM or lock ({error})')
            continue
        if not locked:
            problems.append(f'{arch}: lock has no packages for this architecture')
            continue
        known = represented(document)
        for package in locked:
            if (package['name'], package['version']) not in known:
                problems.append(f'{arch}: {package["name"]}@{package["version"]} is in '
                                'apko.lock.json but not represented in the SBOM')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('complete', 'verify'))
    parser.add_argument('layout')
    parser.add_argument('--framework')
    args = parser.parse_args()
    if args.mode == 'complete':
        if not args.framework:
            parser.error('--framework is required to resolve the source namespace')
        for arch, names in complete(args.layout, args.framework).items():
            print(f'{arch}: added {len(names)} package(s) absent from the Apko SPDX')
    problems = errors(args.layout)
    for problem in problems:
        print(f'::error::{problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
