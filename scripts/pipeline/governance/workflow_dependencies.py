"""Verify this repository's own contract with the reviewed shared library.

The versioned policy approves the origin; literal `uses:` pin the commit.
This only inspects files that live in this repository: the approved origin,
the local callers' pinned SHA (immutable, no moving refs, one release shared
across callers), their expected input bindings, this repository's own action
pins and Dependabot grouping. Input bindings protect the product's locked
build and forwarding choices; they do not mirror the executor's internal API.
It never opens or downloads anything from the shared repository itself --
that library's own implementation, inputs/outputs, hardening, actionlint and
retention are verified by its own CI (alric-containers-reusable-workflows).
"""
import argparse
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY = Path('policies/governance/reusable-workflows.json')
REPOSITORY_NAME = re.compile(
    r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/'
    r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
# Locations, not origin-filtered search results, define the required inventory.
CALLERS = {
    ('validate-base-images.yml', 'validate'): '.github/workflows/validate-apko-images.yml',
    ('test-runtime-images.yml', 'runtime'): '.github/workflows/test-runtime-images.yml',
}
CALLER_INPUTS = {
    ('validate-base-images.yml', 'validate'): {
        'frameworks': '${{ inputs.frameworks }}',
        'melange-config': 'image-base-ca-certificates.yaml',
        'locked-build': True,
    },
    ('test-runtime-images.yml', 'runtime'): {
        'framework': '${{ inputs.framework }}',
        'artifact-run-id': '${{ inputs.artifact-run-id }}',
    },
}
LOCAL_ACTIONS = {'promote-stable.yml': 'promote', 'recover-stable.yml': 'recover'}
TRIVY = 'actions/setup-trivy'


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate configuration key: {key}')
        result[key] = value
    return result


def approved_repository(root=ROOT):
    path = root / POLICY
    doc = json.loads(path.read_text(), object_pairs_hook=unique_pairs)
    if (not isinstance(doc, dict) or set(doc) != {'schema_version', 'repository'}
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1):
        raise ValueError(f'{POLICY}: expected schema_version=1 and repository')
    repository = doc['repository']
    if (not isinstance(repository, str) or not REPOSITORY_NAME.fullmatch(repository)
            or repository.endswith('.git')):
        raise ValueError(f'{POLICY}: repository must be a literal GitHub.com owner/repo')
    return repository


class UniqueLoader(yaml.SafeLoader):
    """Reject ambiguous mappings instead of letting the last uses win."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        return unique_pairs((self.construct_object(key, deep=deep),
                             self.construct_object(value, deep=deep))
                            for key, value in node.value)


def document(path):
    try:
        result = yaml.load(path.read_text(), Loader=UniqueLoader)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise ValueError(f'{path.name}: unreadable configuration ({error})') from error
    if not isinstance(result, dict):
        raise ValueError(f'{path.name}: expected a configuration mapping')
    return result


def local_workflows(root=ROOT):
    return [path for path in sorted((root / '.github/workflows').glob('*'))
            if path.suffix in {'.yml', '.yaml'}]


def workflow_documents(paths):
    result = {}
    for path in paths:
        if path in result:
            raise ValueError(f'{path.name}: duplicate workflow location')
        doc = document(path)
        jobs = doc.get('jobs')
        if not isinstance(jobs, dict) or not jobs:
            raise ValueError(f'{path.name}: missing jobs mapping')
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                raise ValueError(f'{path.name}/{job_id}: invalid job')
            steps = job.get('steps', [])
            if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
                raise ValueError(f'{path.name}/{job_id}: invalid steps')
        result[path] = doc
    return result


def required_document(documents, name):
    matches = [(path, doc) for path, doc in documents.items() if path.name == name]
    if len(matches) != 1:
        raise ValueError(f'{name}: missing or ambiguous required workflow')
    return matches[0]


def required_job(documents, name, job_id):
    _, doc = required_document(documents, name)
    if job_id not in doc['jobs']:
        raise ValueError(f'{name}/{job_id}: missing required library point')
    return doc['jobs'][job_id]


def reference(uses, repository, path, location):
    match = re.fullmatch(re.escape(repository + '/' + path) + r'@([0-9a-f]{40})',
                         uses if isinstance(uses, str) else '')
    if not match:
        raise ValueError(f'{location}: expected {repository}/{path}@<full SHA>; '
                         'missing, malformed or unapproved library reference')
    return match[1]


def required_step(job, name, location):
    matches = [(index, step) for index, step in enumerate(job.get('steps', []))
               if step.get('name') == name]
    if len(matches) != 1:
        raise ValueError(f'{location}/{name}: expected exactly one required step')
    return matches[0]


def _caller_inputs(job, expected, location):
    supplied = job.get('with')
    if (not isinstance(supplied, dict)
            or any(not isinstance(name, str) for name in supplied)):
        raise ValueError(f'{location}: expected caller inputs mapping with string keys')
    missing = sorted(set(expected) - set(supplied))
    unknown = sorted(set(supplied) - set(expected))
    if missing or unknown:
        raise ValueError(f'{location}: incompatible caller inputs; '
                         f'missing={missing}, unknown={unknown}')
    for name, value in expected.items():
        # bool is an int subclass in Python; equality alone would accept 1.
        if type(supplied[name]) is not type(value) or supplied[name] != value:
            raise ValueError(f'{location}: {name} must retain its reviewed input binding '
                             f'and {type(value).__name__} type')


def _dependencies(documents, repository):
    found = []
    for (name, job_id), target in CALLERS.items():
        job = required_job(documents, name, job_id)
        ref = reference(job.get('uses'), repository, target, f'{name}/{job_id}')
        _caller_inputs(job, CALLER_INPUTS[(name, job_id)], f'{name}/{job_id}')
        found.append({'caller': required_document(documents, name)[0], 'job': job, 'path': target,
                      'ref': ref, 'repository': repository})
    if len({entry['ref'] for entry in found}) != 1:
        raise ValueError('shared workflow callers must adopt one reviewed release together')
    for path, doc in documents.items():
        name = path.name
        for job_id, job in doc['jobs'].items():
            uses = job.get('uses', '')
            if isinstance(uses, str) and uses.startswith(repository + '/'):
                if (name, job_id) not in CALLERS:
                    raise ValueError(f'{name}/{job_id}: unregistered library workflow point')
    return found


def dependencies(root=ROOT):
    repository = approved_repository(root)
    return _dependencies(workflow_documents(local_workflows(root)), repository)


def _tooling(documents, repository, expected):
    pins = set()
    positions = set()
    for name, job_id in expected.items():
        job = required_job(documents, name, job_id)
        index, step = required_step(job, 'Install Trivy', f'{name}/{job_id}')
        pins.add(reference(step.get('uses'), repository, TRIVY,
                           f'{name}/{job_id}/Install Trivy'))
        positions.add((name, job_id, index))
    for path, doc in documents.items():
        name = path.name
        for job_id, job in doc['jobs'].items():
            for index, step in enumerate(job.get('steps', [])):
                uses = step.get('uses', '')
                if isinstance(uses, str) and uses.startswith(repository + '/'):
                    if (name, job_id, index) not in positions:
                        raise ValueError(f'{name}/{job_id}/step {index}: '
                                         'unregistered library action point')
    if len(pins) != 1:
        raise ValueError('promotion and recovery must use one Trivy setup SHA')


def tooling_consistency(paths, root=ROOT):
    _tooling(workflow_documents(paths), approved_repository(root), LOCAL_ACTIONS)


def _dependabot(root, repository):
    doc = document(root / '.github/dependabot.yml')
    updates = doc.get('updates')
    if not isinstance(updates, list) or any(not isinstance(item, dict) for item in updates):
        raise ValueError('dependabot.yml: expected updates list')
    entries = [item for item in updates
               if item.get('package-ecosystem') == 'github-actions' and item.get('directory') == '/']
    if len(entries) != 1:
        raise ValueError('dependabot.yml: expected one root github-actions configuration')
    groups = entries[0].get('groups')
    group = groups.get('reusable-container-pipeline') if isinstance(groups, dict) else None
    if not isinstance(group, dict) or group.get('patterns') != [repository + '*']:
        raise ValueError('dependabot.yml: reusable-container-pipeline must group the approved origin')


def _local_contract(root):
    repository = approved_repository(root)
    documents = workflow_documents(local_workflows(root))
    entries = _dependencies(documents, repository)
    _tooling(documents, repository, LOCAL_ACTIONS)
    _dependabot(root, repository)
    return repository, entries


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT,
                        help='consumer checkout containing the reviewed policy and callers')
    args = parser.parse_args(argv)
    try:
        _local_contract(args.root)
        print('Origin, pinned SHA and local caller/tooling contract verified.')
    except (OSError, ValueError) as error:
        print(f'::error::{error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
