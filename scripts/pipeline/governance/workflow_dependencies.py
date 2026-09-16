"""Resolve the reviewed GitHub.com library and verify its static callers.

The versioned policy approves the origin; literal uses approve the commits.
Checkout mode validates local references before emitting repository/ref.
Lint additionally verifies the consumed Git commit, workflow bytes and APIs.
Neither mode downloads code or grants access to a private repository.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY = Path('policies/governance/reusable-workflows.json')
REPOSITORY_NAME = re.compile(
    r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/'
    r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
SHA = re.compile(r'[0-9a-f]{40}')
# Locations, not origin-filtered search results, define the required inventory.
CALLERS = {
    ('validate-base-images.yml', 'validate'): '.github/workflows/validate-apko-images.yml',
    ('test-runtime-images.yml', 'runtime'): '.github/workflows/test-runtime-images.yml',
}
LOCAL_ACTIONS = {'promote-stable.yml': 'promote', 'recover-stable.yml': 'recover'}
SHARED_ACTIONS = {'validate-apko-images.yml': 'validate'}
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


def _dependencies(documents, repository):
    found = []
    for (name, job_id), target in CALLERS.items():
        job = required_job(documents, name, job_id)
        ref = reference(job.get('uses'), repository, target, f'{name}/{job_id}')
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
        raise ValueError('validation, promotion and recovery must use one Trivy setup SHA')


def tooling_consistency(paths, root=ROOT):
    _tooling(workflow_documents(paths), approved_repository(root),
             {**LOCAL_ACTIONS, **SHARED_ACTIONS})


def _checkout_wiring(documents):
    name = 'ci.yml'
    for job_id in ('test', 'lint-workflows'):
        job = required_job(documents, name, job_id)
        steps = job.get('steps', [])
        resolvers = [(i, step) for i, step in enumerate(steps) if step.get('id') == 'shared']
        if (len(resolvers) != 1 or resolvers[0][1].get('run') !=
                'python3 -B -m scripts.pipeline.governance.workflow_dependencies checkout'):
            raise ValueError(f'{name}/{job_id}: required reviewed-origin resolver missing or changed')
        index, step = required_step(job, 'Checkout reusable workflows at the caller SHA',
                                    f'{name}/{job_id}')
        uses = step.get('uses', '')
        settings = step.get('with')
        if (index <= resolvers[0][0] or not isinstance(uses, str)
                or not re.fullmatch(r'actions/checkout@[0-9a-f]{40}', uses)
                or settings != {'repository': '${{ steps.shared.outputs.repository }}',
                                'ref': '${{ steps.shared.outputs.ref }}',
                                'path': '.reusable-workflows', 'persist-credentials': False}):
            raise ValueError(f'{name}/{job_id}: checkout must consume reviewed repository/ref '
                             'outputs without extra credentials')


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
    _checkout_wiring(documents)
    _dependabot(root, repository)
    return repository, entries


def git_output(checkout, *args):
    return subprocess.run(['git', '--no-replace-objects', '-C', str(checkout), *args],
                          check=True, capture_output=True).stdout


def shared_workflows(root=ROOT, checkout=None):
    repository, entries = _local_contract(root)
    checkout = Path(checkout or os.environ.get('REUSABLE_WORKFLOWS_PATH')
                    or root / '.reusable-workflows').resolve()
    if not (checkout / '.git').exists():
        raise ValueError(f'missing shared checkout; check out {repository}@{entries[0]["ref"]}')
    origin = git_output(checkout, 'remote', 'get-url', '--all', 'origin').decode().strip()
    accepted_urls = {prefix + repository + suffix
                     for prefix in ('https://github.com/', 'git@github.com:', 'ssh://git@github.com/')
                     for suffix in ('', '.git')}
    if origin not in accepted_urls:
        raise ValueError('shared checkout origin differs from the approved GitHub.com repository')
    head = git_output(checkout, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    if not SHA.fullmatch(head) or head != entries[0]['ref']:
        raise ValueError('shared checkout HEAD differs from the caller release')
    files = []
    for entry in entries:
        path = checkout / entry['path']
        expected = git_output(checkout, 'show', f'{head}:{entry["path"]}')
        if not path.is_file() or path.is_symlink() or path.read_bytes() != expected:
            raise ValueError(f'{entry["path"]}: shared workflow differs from its pinned commit')
        doc = document(path)
        events = doc.get('on', doc.get(True))
        if not isinstance(events, dict) or set(events) != {'workflow_call'}:
            raise ValueError(f'{path.name}: shared executor must accept workflow_call only')
        call = events['workflow_call'] or {}
        if not isinstance(call, dict) or not isinstance(call.get('inputs', {}), dict):
            raise ValueError(f'{path.name}: invalid workflow_call inputs')
        declared = call.get('inputs', {})
        supplied = entry['job'].get('with', {})
        if (not isinstance(supplied, dict)
                or any(not isinstance(value, dict) for value in declared.values())):
            raise ValueError(f'{path.name}: invalid inputs mapping')
        missing = [name for name, definition in declared.items()
                   if definition.get('required') and name not in supplied]
        unknown = sorted(set(supplied) - set(declared))
        if missing or unknown:
            raise ValueError(f'{entry["caller"].name}: incompatible inputs; '
                             f'missing={missing}, unknown={unknown}')
        files.append(path)
    tooling_consistency(local_workflows(root) + files, root)
    return files


def workflow_files(root=ROOT, checkout=None):
    return local_workflows(root) + shared_workflows(root, checkout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['checkout', 'lint'])
    parser.add_argument('--root', type=Path, default=ROOT,
                        help='consumer checkout containing the reviewed policy and callers')
    args = parser.parse_args(argv)
    try:
        if args.mode == 'checkout':
            repository, entries = _local_contract(args.root)
            output = f'repository={repository}\nref={entries[0]["ref"]}\n'
            if os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                    stream.write(output)
            else:
                print(output, end='')
        else:
            from scripts.pipeline.governance.lint_workflow_hardening import check
            problems = []
            for path in workflow_files(args.root):
                problems += check(path.name, document(path))
            if problems:
                raise ValueError('; '.join(problems))
            print('Shared workflow origin, SHA, inputs and hardening verified.')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'::error::{error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
