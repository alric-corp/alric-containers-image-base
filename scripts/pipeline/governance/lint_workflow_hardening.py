"""Enforce the M16 hardening rules on the hand-written workflows.

actionlint cobre sintaxe e shell; estas regras cobrem o que ele não checa e
que o M16 exige valer daqui pra frente, não só uma vez: checkout sem
credencial Git persistida, nenhum dado de entrada interpolado dentro de um
`run`, limite de duração em todo job executor, permissões declaradas e
Actions externas fixadas por SHA completo.
"""
import re
import sys
from pathlib import Path

import yaml

SHA = re.compile(r'[^@]+@[0-9a-f]{40}$')
EXPRESSION = re.compile(r'\$\{\{.*?\}\}', re.DOTALL)


def check(name, doc):
    """Devolve a lista de violações de um workflow já carregado."""
    problems = []
    if 'permissions' not in doc:
        problems.append(f'{name}: workflow sem `permissions` explícito no topo')
    for job_id, job in (doc.get('jobs') or {}).items():
        uses = job.get('uses')
        if uses and not uses.startswith('./') and not SHA.fullmatch(uses):
            problems.append(f'{name}: job `{job_id}` chama workflow sem SHA completo')
        steps = job.get('steps')
        if steps is None:
            continue  # chamada de workflow reutilizável: sem steps próprios
        if 'timeout-minutes' not in job:
            problems.append(f'{name}: job `{job_id}` sem `timeout-minutes`')
        for step in steps:
            label = step.get('name') or step.get('uses') or step.get('id') or '?'
            uses = step.get('uses')
            if uses and not uses.startswith('./') and not SHA.match(uses):
                problems.append(f'{name}: `{job_id}` / `{label}` usa Action sem SHA completo')
            if uses and uses.split('@')[0] == 'actions/checkout':
                if (step.get('with') or {}).get('persist-credentials') is not False:
                    problems.append(
                        f'{name}: `{job_id}` / `{label}` precisa de `persist-credentials: false`')
            found = EXPRESSION.search(step.get('run') or '')
            if found:
                problems.append(
                    f'{name}: `{job_id}` / `{label}` interpola {found.group()} dentro de `run` — '
                    'passe por `env:` e use a variável com aspas')
    return problems


def local_call_permissions(documents):
    """Nested jobs cannot request more than the calling job grants.

    Workflow-level permissions are defaults, not a cap on the workflow's
    own jobs. The cap exists at a reusable workflow call boundary.
    """
    levels = {'none': 0, 'read': 1, 'write': 2}

    def level(permissions, scope):
        if isinstance(permissions, str):
            return levels[permissions.removesuffix('-all')]
        return levels[(permissions or {}).get(scope, 'none')]

    problems = []
    for name, document in documents.items():
        for job_id, job in (document.get('jobs') or {}).items():
            uses = job.get('uses', '')
            if not uses.startswith('./.github/workflows/'):
                continue
            target = uses.removeprefix('./.github/workflows/')
            if target not in documents:
                problems.append(f'{name}/{job_id}: missing local workflow {target}')
                continue
            granted = job.get('permissions', document.get('permissions'))
            callee = documents[target]
            for nested_id, nested in (callee.get('jobs') or {}).items():
                requested = nested.get('permissions', callee.get('permissions'))
                if not isinstance(requested, dict):
                    problems.append(f'{target}/{nested_id}: nested permissions must be explicit mappings')
                    continue
                for scope in requested:
                    if level(requested, scope) > level(granted, scope):
                        problems.append(f'{name}/{job_id} -> {target}/{nested_id}: '
                                        f'{scope}: {requested[scope]} exceeds caller permissions')
    return problems


def main(root=Path('.github/workflows')):
    problems = []
    documents = {}
    for path in sorted(root.glob('*.yml')):
        documents[path.name] = yaml.safe_load(path.read_text())
        problems += check(path.name, documents[path.name])
    problems += local_call_permissions(documents)
    for problem in problems:
        print(f'::error::{problem}', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
