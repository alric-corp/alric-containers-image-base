#!/usr/bin/env python3
"""Lote padrão do pipeline: catálogo menos os frameworks excluídos (ADR-0001).

O lote que `workflow.yml` pede em `validate-pr`, `build-base-images` e
`promote-stable` está escrito três vezes, como string JSON, porque o `with:`
de um workflow reutilizável não é calculado. Este lint garante que as três
listas sejam exatamente `catálogo (frameworks/*.yaml) − exclusões`, e que
cada exclusão seja uma decisão revisada: motivo, dono, `review_by` e ADR.

A lista de exclusões é `exceptions` em `policies/operations/health.json` —
a mesma que a saúde operacional usa para classificar a ausência de
publicação/promoção como `known` e para alertar quando `review_by` vence.
Uma única fonte: um framework fora do lote é, por definição, uma exceção
conhecida; um framework no lote que não publica é alerta, não exceção.

`review_by` vencido não reprova o lint (bloquearia todos os PRs por uma
data); esse caso é o alerta diário `exception_review` do job de saúde.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / 'frameworks'
POLICY = ROOT / 'policies/operations/health.json'
WORKFLOW = ROOT / '.github/workflows/workflow.yml'
# Jobs de workflow.yml que recebem lote explícito. O lote DEFAULT/FULL é o
# catálogo normal menos as exceptions. `P0_04_BATCH` é o perfil temporário
# `["go1-26", "go1-26-dev"]`: durante o rollout, build e promoção usam esse
# perfil. Callers explícitos, inclusive validações de impacto compartilhado,
# continuam podendo usar DEFAULT/FULL; o workflow reutilizável permanece apto
# a chamadas FULL independentes deste entrypoint.
BATCH_JOBS = ('validate-pr', 'build-base-images', 'promote-stable')
# Temporary rollout profile for the first corporate E2E. It is an execution
# selection only; the catalog and FULL policy remain unchanged.
P0_04_BATCH = ['go1-26', 'go1-26-dev']
REQUIRED_FIELDS = ('reason', 'owner', 'review_by', 'adr')

# Forma canônica de `with.frameworks`, conferida inteira (fullmatch), não um
# trecho `[…]` dentro do valor. O lote é um literal JSON de nomes na forma que
# validate_inputs aceita; em `build-base-images` ele é o fallback da única
# expressão permitida, a que escolhe o input do dispatch. Qualquer outra
# expressão `${{ }}` (vars, env, secrets, inputs, fromJSON, concatenação,
# fallback) é recusada: uma fonte externa passaria a decidir o lote
# automático, fora da política versionada e deste lint.
NAME = r'[a-z0-9]+(?:-[a-z0-9]+)*'
JSON_LIST = rf'\[\s*(?:"{NAME}"\s*(?:,\s*"{NAME}"\s*)*)?\]'
DISPATCH_PREFIX = "${{ github.event_name == 'workflow_dispatch' && inputs.frameworks || '"
DISPATCH_SUFFIX = "' }}"
STATIC_FORM = 'array JSON literal `["…"]`'
DISPATCH_FORM = f'`{DISPATCH_PREFIX}["…"]{DISPATCH_SUFFIX}`'
FORMS = {
    'validate-pr': (re.compile(f'({JSON_LIST})'), STATIC_FORM),
    'build-base-images': (re.compile(re.escape(DISPATCH_PREFIX) + f'({JSON_LIST})'
                                     + re.escape(DISPATCH_SUFFIX)), DISPATCH_FORM),
    'promote-stable': (re.compile(f'({JSON_LIST})'), STATIC_FORM),
}

# Convenção de docs/adr/README.md: `docs/adr/NNNN-titulo.md`, primeira linha
# `# ADR-NNNN …`. O campo `adr` da política é esse caminho relativo, e nada mais.
ADR_DIR = ('docs', 'adr')
ADR_FILE = re.compile(r'(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md')


def catalog(directory=CATALOG):
    """Nomes do catálogo: um arquivo `frameworks/<nome>.yaml` por framework."""
    return sorted(path.stem for path in Path(directory).glob('*.yaml') if path.is_file())


def adr_problem(adr, root=ROOT):
    """Por que `adr` não é um ADR válido do repositório, ou None.

    Caminho relativo diretamente em docs/adr/, sem `..`, `/` inicial ou
    subdiretório (conferido no texto, não após resolver); nenhum componente
    entre a raiz do repositório e o arquivo é link simbólico; o arquivo é
    regular e, resolvido, fica fisicamente em `<raiz canônica>/docs/adr/`;
    o nome é `NNNN-titulo.md` e a primeira linha é o título `# ADR-NNNN …`
    com o mesmo número.
    """
    parts = adr.split('/')
    name = ADR_FILE.fullmatch(parts[-1]) if len(parts) == 3 else None
    if tuple(parts[:2]) != ADR_DIR or name is None:
        return (f'ADR `{adr}` precisa ser um caminho relativo `docs/adr/NNNN-titulo.md` '
                '(sem `..`, `/` inicial ou subdiretório)')
    # Contenção física. Só a raiz é canonizada; `docs/adr` é acrescentado
    # depois, no texto — resolver `root/docs/adr` faria um `docs` ou `docs/adr`
    # apontando para fora virar a nova raiz "permitida". Cada componente é
    # conferido como não-link, e o arquivo resolvido tem de cair exatamente
    # nesse diretório (que, por construção, está dentro da raiz canônica).
    try:
        repo = Path(root).resolve(strict=True)
    except (OSError, RuntimeError):
        return f'ADR `{adr}`: raiz do repositório `{root}` não resolve'
    for depth in range(1, len(parts) + 1):
        if repo.joinpath(*parts[:depth]).is_symlink():
            return (f'ADR `{adr}`: `{"/".join(parts[:depth])}` é link simbólico; o ADR precisa '
                    'estar fisicamente em docs/adr/ do repositório')
    path = repo / adr
    if not path.is_file():
        return f'ADR `{adr}` não existe no repositório como arquivo regular'
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return f'ADR `{adr}` não existe no repositório como arquivo regular'
    if resolved.parent != repo.joinpath(*ADR_DIR):
        return f'ADR `{adr}` resolve para fora de docs/adr/ do repositório'
    title = f'# ADR-{name.group(1)} '
    if not path.read_text().startswith(title):
        return f'ADR `{adr}` precisa começar com o título `{title}…` (convenção de docs/adr/README.md)'
    return None


def exclusions(policy, root=ROOT):
    """Frameworks fora do lote padrão e os problemas de forma de cada entrada.

    Cada entrada precisa ser um objeto com os campos obrigatórios; chaves
    `$...` não são aceitas aqui porque a saúde itera `exceptions` como
    frameworks. `review_by` precisa ser uma data ISO (AAAA-MM-DD) real e
    `adr` um ADR válido de docs/adr/ (ver `adr_problem`).
    """
    entries = policy.get('exceptions') or {}
    problems = []
    if not isinstance(entries, dict):
        return {}, ['`exceptions` na política precisa ser um objeto {framework: {...}}']
    for framework, entry in sorted(entries.items()):
        if not isinstance(entry, dict):
            problems.append(f'exceção `{framework}` precisa ser um objeto com '
                            + ', '.join(REQUIRED_FIELDS))
            continue
        for field in REQUIRED_FIELDS:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f'exceção `{framework}` sem `{field}`')
        review = entry.get('review_by')
        if isinstance(review, str) and review.strip():
            try:
                date.fromisoformat(review)
            except ValueError:
                problems.append(f'exceção `{framework}`: `review_by` {review!r} não é data ISO '
                                '(AAAA-MM-DD)')
        adr = entry.get('adr')
        if isinstance(adr, str) and adr.strip():
            problem = adr_problem(adr, root)
            if problem:
                problems.append(f'exceção `{framework}`: {problem}')
    return {framework: entry for framework, entry in entries.items()
            if isinstance(entry, dict)}, problems


def batches(workflow):
    """Valor bruto de `with.frameworks` de cada job do lote (None se ausente)."""
    jobs = workflow.get('jobs') or {}
    return {job_id: ((jobs.get(job_id) or {}).get('with') or {}).get('frameworks')
            for job_id in BATCH_JOBS}


def parse_batch(job_id, raw):
    """(nomes, None) se `raw` está na forma canônica do job; (None, problema) se não.

    A forma é comparada inteira: `${{ vars.X || '[…]' }}` é recusada mesmo
    com o literal certo, porque `vars.X` substituiria o lote em execução.
    """
    # P0-04 deliberately uses a fixed literal for the build entrypoint so a
    # manual dispatch cannot widen the corporate E2E scope. Keep the normal
    # dispatch form available to reusable/full callers and tests.
    if job_id in ('validate-pr', 'build-base-images') and raw == json.dumps(P0_04_BATCH):
        return list(P0_04_BATCH), None
    pattern, form = FORMS[job_id]
    match = pattern.fullmatch(raw) if isinstance(raw, str) else None
    if match:
        return json.loads(match.group(1)), None
    if raw is None:
        return None, f'`{job_id}`: `with.frameworks` ausente em workflow.yml; esperado {form}'
    shown = raw if isinstance(raw, str) and len(raw) <= 60 else str(raw)[:57] + '…'
    return None, (f'`{job_id}`: `frameworks` fora da forma canônica (`{shown}`). O lote '
                  f'automático precisa ser estático — {form} — e não pode depender de fonte '
                  'externa: vars, env, secrets, inputs, fromJSON, concatenação ou fallback '
                  'dinâmico substituiriam a política versionada em execução')


def expected_batch(names, excluded):
    return sorted(name for name in names if name not in excluded)


def lint(names, excluded, found):
    """Divergências entre os lotes escritos e `catálogo − exclusões`."""
    problems = [f'exceção `{framework}` não existe no catálogo'
                for framework in sorted(excluded) if framework not in names]
    expected = expected_batch(names, excluded)
    for job_id, raw in found.items():
        batch, problem = parse_batch(job_id, raw)
        if batch is None:
            problems.append(problem)
            continue
        seen = set()
        for name in batch:
            if name in seen:
                problems.append(f'`{job_id}`: framework `{name}` repetido no lote')
            seen.add(name)
            if name not in names:
                problems.append(f'`{job_id}`: framework `{name}` não existe no catálogo')
            elif name in excluded:
                problems.append(f'`{job_id}`: framework `{name}` está fora do lote padrão '
                                f"({excluded[name].get('adr') or 'exceção na política'})")
        # P0-04 is an explicit execution profile, not a catalog exclusion.
        # A rollout caller may use it for build or promotion; reusable FULL
        # callers remain governed by the catalog batch rule.
        required = [] if batch == P0_04_BATCH else expected
        for name in required:
            if name not in seen:
                problems.append(f'`{job_id}`: framework `{name}` do catálogo ausente do lote padrão '
                                '(inclua-o ou registre a exclusão na política)')
    return problems


def load(policy_path=POLICY, workflow_path=WORKFLOW, catalog_dir=CATALOG):
    policy = json.loads(Path(policy_path).read_text())
    workflow = yaml.safe_load(Path(workflow_path).read_text())
    return catalog(catalog_dir), policy, workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('lint', 'list'))
    parser.add_argument('--policy', type=Path, default=POLICY)
    parser.add_argument('--workflow', type=Path, default=WORKFLOW)
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    args = parser.parse_args()

    names, policy, workflow = load(args.policy, args.workflow, args.catalog)
    excluded, problems = exclusions(policy)
    found = batches(workflow)
    problems += lint(names, excluded, found)

    if args.mode == 'list':
        print(json.dumps({'catalog': names, 'excluded': sorted(excluded),
                          'default_batch': expected_batch(names, excluded),
                          'jobs': {job_id: parse_batch(job_id, raw)[0] for job_id, raw in found.items()},
                          'problems': problems}, indent=2))
        return 1 if problems else 0

    for problem in problems:
        print(f'::error::{problem}', file=sys.stderr)
    print(f'Lote padrão conferido: {len(names)} framework(s) no catálogo, '
          f'{len(excluded)} excluído(s), {len(found)} job(s) de workflow.yml.')
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
