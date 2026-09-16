#!/usr/bin/env python3
"""Manutenção verificável das ferramentas e da trust anchor Wolfi (M09/P1-03).

Três perguntas diferentes, respondidas separadamente:

1. `lint` (offline, determinístico): todo pin do repositório está sob algum
   gerenciador de atualização (Dependabot para Actions, Renovate para os
   digests de imagem/versões de ferramenta)? E o mesmo insumo aparece com o
   mesmo digest em todos os arquivos que o usam? Um pin sem gerenciador não
   é "estável", é esquecido; o mesmo insumo com digests diferentes em dois
   arquivos é divergência silenciosa entre o que roda e o que foi revisado.
2. `check` (rede): cada pin ainda existe na origem? Um digest recolhido do
   registry ou um SHA de Action que desapareceu quebra o pipeline no próximo
   run — melhor descobrir num job de saúde que numa publicação.
3. `prs` (rede): as PRs de atualização abertas por esses gerenciadores estão
   sendo revisadas, ou envelhecendo sem ninguém olhar?

`trust` verifica offline a chave pública Wolfi versionada e seus keyrings.
Esse pin exige revisão humana, nunca proposta/aplicação automática. `check`
compara a chave atual da origem somente para detectar rotação/divergência.

Nada aqui copia versão ou SHA de exemplo genérico: os pins vêm dos arquivos
do próprio repositório e a checagem confirma origem e disponibilidade.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from scripts.pipeline.governance import wolfi_trust

ROOT = Path(__file__).resolve().parents[3]
ACTION = re.compile(r'uses:\s*["\']?(?P<name>[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+)@(?P<ref>[^\s"\'#]+)')
IMAGE = re.compile(r'(?P<name>[a-z0-9.-]+(?::\d+)?/[a-z0-9._/-]+)'
                   r'(?::(?P<tag>[A-Za-z0-9_.-]+))?@(?P<digest>sha256:[0-9a-f]{64})')
TOOL_VERSION = re.compile(r'(?P<name>[A-Z0-9_]+_VERSION):\s*["\']?(?P<version>v?\d+[\w.+-]*)')
SHA = re.compile(r'[0-9a-f]{40}')



def scanned_files():
    """Arquivos onde este repositório fixa insumos externos."""
    files = sorted((ROOT / '.github/workflows').glob('*.yml'))
    files += [ROOT / 'Makefile']
    # Os scripts que o pipeline executa também fixam imagens (o Skopeo do
    # executor de contratos, por exemplo). Arquivos de teste ficam de fora:
    # o que há neles são fixtures, não insumos de um run real.
    for directory in (ROOT / 'scripts/pipeline', ROOT / '.github/scripts'):
        files += [path for path in sorted(directory.rglob('*.py'))
                  if not path.name.startswith('test_')]
    return [path for path in files if path.is_file()]


def pins(paths):
    """Todos os pins externos, com arquivo de origem e valor efetivo."""
    found = []
    for path in paths:
        text = path.read_text()
        relative = str(path.relative_to(ROOT))
        for match in ACTION.finditer(text):
            name, ref = match.group('name'), match.group('ref')
            if name.startswith('./'):
                continue
            found.append({'kind': 'reusable-workflow' if '/.github/workflows/' in name else 'action',
                          'file': relative, 'name': name, 'current': ref,
                          'pinned': bool(SHA.fullmatch(ref))})
        for match in IMAGE.finditer(text):
            found.append({'kind': 'image', 'file': relative, 'name': match.group('name'),
                          'current': match.group('digest'), 'tag': match.group('tag'),
                          'pinned': True})
        for match in TOOL_VERSION.finditer(text):
            found.append({'kind': 'tool', 'file': relative, 'name': match.group('name'),
                          'current': match.group('version'), 'pinned': True})
    return found


def unslash(pattern):
    """Renovate escreve padrões como /regex/; aceita as duas formas."""
    return pattern[1:-1] if pattern.startswith('/') and pattern.endswith('/') else pattern


def to_python_regex(expression):
    """Renovate usa grupos nomeados no estilo JS `(?<nome>...)`."""
    return re.sub(r'\(\?<(?![=!])', '(?P<', expression)


def renovate_matches(config, paths):
    """(arquivo, valor efetivo) -> origem declarada, para cada pin coberto.

    A correspondência é por arquivo e valor: foi exatamente aquele valor que o
    manager casou naquele arquivo. O nome da dependência pode vir de um grupo
    do próprio regex ou de `depNameTemplate` — quando vem do template, é a
    origem declarada para atualização, e é ela que a checagem de
    disponibilidade consulta.
    """
    covered = {}
    for manager in config.get('customManagers') or []:
        patterns = [re.compile(unslash(pattern))
                    for pattern in manager.get('managerFilePatterns') or []]
        expressions = [re.compile(to_python_regex(expression))
                       for expression in manager.get('matchStrings') or []]
        for path in paths:
            relative = str(path.relative_to(ROOT))
            if not any(pattern.search(relative) for pattern in patterns):
                continue
            text = path.read_text()
            for expression in expressions:
                for match in expression.finditer(text):
                    groups = match.groupdict()
                    value = (groups.get('currentDigest') or groups.get('currentValue')
                             or groups.get('currentVersion'))
                    if value is None:
                        continue
                    name = groups.get('depName') or manager.get('depNameTemplate')
                    covered[(relative, value)] = {
                        'name': name, 'datasource': manager.get('datasourceTemplate')}
    return covered


def dependabot_ecosystems(config):
    return {update.get('package-ecosystem') for update in config.get('updates') or []}


def coverage(entries, renovate, dependabot):
    """Quem propõe a atualização de cada pin; sem ninguém, é uma lacuna."""
    for entry in entries:
        managers = []
        if entry['kind'] == 'local-key':
            entry['managers'] = ['human-review']
            continue
        if entry['kind'] in ('action', 'reusable-workflow') and 'github-actions' in dependabot \
                and entry['file'].startswith('.github/workflows/'):
            managers.append('dependabot')
        match = renovate.get((entry['file'], entry['current']))
        if match:
            managers.append('renovate')
            # Origem declarada para atualização (ex.: TRIVY_VERSION ->
            # aquasecurity/trivy): é ela que a disponibilidade consulta.
            if match['datasource'] == 'github-releases' and (match['name'] or '').count('/') == 1:
                entry['source'] = match['name']
        entry['managers'] = managers
    return entries


def consistency(entries):
    """O mesmo insumo tem de aparecer com o mesmo valor em todos os arquivos."""
    values = {}
    for entry in entries:
        if entry['kind'] == 'tool':
            continue
        values.setdefault((entry['kind'], entry['name']), {}).setdefault(
            entry['current'], []).append(entry['file'])
    return [{'kind': kind, 'name': name, 'values': {value: files for value, files in options.items()}}
            for (kind, name), options in sorted(values.items()) if len(options) > 1]


def lint(entries):
    """Problemas offline: pin frouxo, pin sem gerenciador, valor divergente."""
    problems = []
    for entry in entries:
        if entry['kind'] == 'local-key':
            problems.extend(entry['errors'])
            continue
        if not entry['pinned']:
            problems.append(f"{entry['file']}: {entry['name']} usa `{entry['current']}` em vez de "
                            'um SHA completo')
        elif not entry['managers']:
            problems.append(f"{entry['file']}: {entry['name']} não tem gerenciador de atualização "
                            '(Dependabot ou Renovate) — ninguém vai propor a próxima versão')
    for divergence in consistency(entries):
        files = {value: sorted(paths) for value, paths in divergence['values'].items()}
        problems.append(f"{divergence['name']} aparece com valores diferentes: {files}")
    return problems


def load_dependabot():
    import yaml
    return yaml.safe_load((ROOT / '.github/dependabot.yml').read_text())


def gh_json(path, run=subprocess.run):
    result = run(['gh', 'api', path], check=False, capture_output=True, text=True, timeout=60)
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def image_available(reference, run=subprocess.run):
    result = run(['docker', 'buildx', 'imagetools', 'inspect', '--raw', reference],
                 check=False, capture_output=True, text=True, timeout=180)
    return result.returncode == 0


def availability(entries, run=subprocess.run):
    """Cada pin ainda resolve na origem? Sem rede, isto não roda."""
    checked = []
    for entry in entries:
        record = dict(entry)
        if entry['kind'] == 'local-key':
            record = wolfi_trust.upstream_status(entry)
        elif entry['kind'] in ('action', 'reusable-workflow'):
            owner_repo = '/'.join(entry['name'].split('/')[:2])
            commit = gh_json(f"repos/{owner_repo}/commits/{entry['current']}", run)
            record['available'] = bool(commit and commit.get('sha') == entry['current'])
            record['origin'] = f'https://github.com/{owner_repo}'
        elif entry['kind'] == 'image':
            tag = ':' + entry['tag'] if entry.get('tag') else ''
            record['available'] = image_available(f"{entry['name']}{tag}@{entry['current']}", run)
            record['origin'] = entry['name']
        else:
            source = entry.get('source')
            if not source:
                record['available'] = None
                record['origin'] = None
            else:
                release = gh_json(f"repos/{source}/releases/tags/{entry['current']}", run)
                record['available'] = bool(release and release.get('tag_name') == entry['current'])
                record['origin'] = f'https://github.com/{source}'
        checked.append(record)
    return checked


def update_prs(pulls, now, stale_days=7):
    """PRs de atualização abertas, idade e se já têm decisão de revisão."""
    entries = []
    for pull in pulls or []:
        login = ((pull.get('user') or {}).get('login') or '').lower()
        if not any(bot in login for bot in ('dependabot', 'renovate')):
            continue
        created = datetime.fromisoformat(pull['created_at'].replace('Z', '+00:00'))
        age = (now - created).total_seconds() / 86400
        entries.append({'number': pull['number'], 'title': pull['title'], 'author': login,
                        'age_days': round(age, 1), 'draft': bool(pull.get('draft')),
                        'stale': age > stale_days})
    return sorted(entries, key=lambda entry: -entry['age_days'])


def render(entries, prs=None, stale_days=7):
    lines = ['## Pins de ferramentas e trust anchor (M09/P1-03)', '',
             '| Insumo | Valor efetivo | Arquivo(s) | Gerenciador | Disponível |',
             '| --- | --- | --- | --- | --- |']
    grouped = {}
    for entry in entries:
        key = (entry['kind'], entry['name'], entry['current'])
        grouped.setdefault(key, {'files': [], 'managers': entry['managers'],
                                 'available': entry.get('available')})['files'].append(entry['file'])
    for (kind, name, current), data in sorted(grouped.items()):
        available = {True: 'sim', False: '**não**', None: 'não verificado'}[data['available']]
        short = current[:19] + '…' if len(current) > 20 else current
        lines.append(f"| `{name}` ({kind}) | `{short}` | "
                     f"{', '.join(f'`{path}`' for path in sorted(set(data['files'])))} | "
                     f"{', '.join(data['managers']) or '**nenhum**'} | {available} |")
    for entry in entries:
        if entry['kind'] == 'local-key':
            lines += ['', f"### {entry['name']} — detecção de rotação", '',
                      f"- SHA-256 esperado: `{entry['expected_sha256']}`",
                      f"- SHA-256 local: `{entry['actual_sha256']}`",
                      f"- SHA-256 remoto: `{entry.get('remote_sha256')}`",
                      f"- Estado remoto: `{entry.get('remote_status', 'not-checked')}`",
                      '- Monitoramento não atualiza a chave nem acrescenta dependência do endpoint remoto de comparação ao build.']
            lines += [f'- Erro local: {error}' for error in entry['errors']]
    if prs is not None:
        lines += ['', f'### PRs de atualização abertas (revisão pendente > {stale_days}d marcada)', '']
        if not prs:
            lines.append('Nenhuma PR de atualização aberta.')
        else:
            lines += ['| PR | Autor | Idade (dias) | Parada |', '| --- | --- | --- | --- |']
            lines += [f"| #{pr['number']} {pr['title']} | {pr['author']} | {pr['age_days']} | "
                      f"{'**sim**' if pr['stale'] else 'não'} |" for pr in prs]
    return '\n'.join(lines) + '\n'


def write(markdown, path):
    if path:
        with Path(path).open('a') as output:
            output.write(markdown)
    else:
        print(markdown, end='')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('lint', 'check', 'trust'))
    parser.add_argument('--repository', default='', help='owner/repo para as PRs de atualização')
    parser.add_argument('--stale-days', type=float, default=7)
    parser.add_argument('--markdown', help='arquivo de saída (ex.: $GITHUB_STEP_SUMMARY)')
    parser.add_argument('--json', dest='json_output', type=Path)
    args = parser.parse_args()

    local_key = wolfi_trust.local_pin(ROOT)
    if args.mode == 'trust':
        problems = local_key['errors'] + wolfi_trust.config_errors(ROOT)
        for problem in problems:
            print(f'::error::{problem}', file=sys.stderr)
        print(json.dumps(local_key, indent=2))
        return 1 if problems else 0

    paths = scanned_files()
    entries = coverage(pins(paths),
                       renovate_matches(json.loads((ROOT / 'renovate.json').read_text()), paths),
                       dependabot_ecosystems(load_dependabot()))
    entries.append(local_key)
    if args.mode == 'lint':
        problems = lint(entries) + wolfi_trust.config_errors(ROOT)
        for problem in problems:
            print(f'::error::{problem}', file=sys.stderr)
        print(f'{len(entries)} pin(s) conferidos em {len(paths)} arquivo(s).')
        return 1 if problems else 0

    entries = availability(entries)
    prs = None
    if args.repository:
        prs = update_prs(gh_json(f'repos/{args.repository}/pulls?state=open&per_page=100'),
                         datetime.now(timezone.utc), args.stale_days)
    markdown = render(entries, prs, args.stale_days)
    write(markdown, args.markdown)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(
            {'pins': entries, 'update_prs': prs}, indent=2) + '\n')
    unavailable = [entry for entry in entries if entry.get('available') is False]
    for entry in unavailable:
        print(f"::error::pin indisponível na origem: {entry['name']}@{entry['current']} "
              f"({entry['file']})", file=sys.stderr)
    return 1 if unavailable else 0


if __name__ == '__main__':
    raise SystemExit(main())
