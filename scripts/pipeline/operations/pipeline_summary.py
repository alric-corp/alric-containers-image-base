#!/usr/bin/env python3
"""Tabela por framework do resultado real de um run (M11/M04).

Lê as evidências que os jobs já preservam como artifacts — scan, CVEs sem
correção, contrato funcional, publicação e promoção — e escreve uma tabela
única no `GITHUB_STEP_SUMMARY`, com a versão em JSON ao lado para auditoria.

Distinções que a tabela precisa manter, porque cada uma exige uma ação
diferente de quem lê:

- CVE com correção disponível (bloqueia o gate) x CVE sem correção
  (informativa, não bloqueia) x erro de infraestrutura do scanner (não é
  resultado de segurança nenhum e não pode ser lido como aprovação);
- framework sem evidência: aparece como lacuna explícita, nunca omitido —
  um job que morreu antes de subir o artifact não pode desaparecer da tabela;
- execução nativa e emulada, registradas separadamente por arquitetura.
"""
import argparse
import json
from pathlib import Path
import re

from scripts.pipeline.runtime.runtime_images import plan

KINDS = ('build-scans', 'publication', 'promotion-scans', 'promotion', 'runtime')
ARCHITECTURES = ('amd64', 'arm64')
ATTEMPT = re.compile(r'-(\d+)$')

# Estados de coluna: rótulo curto para a tabela.
MISSING = 'sem evidência'


def artifact_name(directory):
    """('build-scans', 'go1-26-dev') a partir de 'build-scans-go1-26-dev-1'."""
    name = ATTEMPT.sub('', directory)
    for kind in KINDS:
        if name.startswith(f'{kind}-'):
            return kind, name[len(kind) + 1:]
    return None, None


def evidence_map(root):
    """Mapeia (tipo, framework) -> diretório do artifact baixado."""
    found = {}
    for directory in sorted(Path(root).iterdir()) if Path(root).is_dir() else []:
        if not directory.is_dir():
            continue
        kind, framework = artifact_name(directory.name)
        if kind:
            # Tentativas maiores vêm depois na ordenação e substituem a anterior.
            found[(kind, framework)] = directory
    return found


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def count_findings(report):
    """Achados que o gate considera: vulnerabilidades com correção e secrets."""
    if not isinstance(report, dict):
        return None
    vulnerabilities = secrets = 0
    for result in report.get('Results') or []:
        vulnerabilities += len(result.get('Vulnerabilities') or [])
        secrets += len(result.get('Secrets') or [])
    return {'vulnerabilities': vulnerabilities, 'secrets': secrets}


def scan_result(directory):
    """Resultado do gate de scan, separando bloqueio real de erro do scanner."""
    if directory is None:
        return {'status': MISSING, 'platforms': {}}
    platforms, blocked, infrastructure = {}, [], []
    for arch in ARCHITECTURES:
        evidence = load(directory / f'evidence-{arch}.json')
        if evidence is None:
            platforms[arch] = {'status': MISSING}
            infrastructure.append(f'{arch}: evidência do scan ausente')
            continue
        findings = count_findings(load(directory / f'trivy-{arch}.json'))
        entry = {'exit_code': evidence.get('exit_code'),
                 'index_digest': evidence.get('index_digest'),
                 'manifest_digest': evidence.get('manifest_digest'),
                 'findings': findings}
        if evidence.get('error'):
            entry['status'] = 'erro de infraestrutura'
            entry['error'] = evidence['error']
            infrastructure.append(f"{arch}: {evidence['error']}")
        elif evidence.get('exit_code') == 0:
            entry['status'] = 'aprovado'
        elif evidence.get('exit_code') == 1:
            entry['status'] = 'bloqueado'
            total = (findings or {}).get('vulnerabilities', 0)
            secrets = (findings or {}).get('secrets', 0)
            blocked.append(f'{arch}: {total} CVE(s) com correção'
                           + (f' e {secrets} secret(s)' if secrets else ''))
        else:
            # Trivy usa 1 para achados; qualquer outro código é falha de
            # execução, não resultado de segurança.
            entry['status'] = 'erro de infraestrutura'
            infrastructure.append(f"{arch}: trivy terminou com {evidence.get('exit_code')}")
        platforms[arch] = entry
    if infrastructure:
        status = 'erro de infraestrutura'
    elif blocked:
        status = 'bloqueado'
    else:
        status = 'aprovado'
    return {'status': status, 'platforms': platforms,
            'reason': '; '.join(infrastructure or blocked)}


def unfixed_result(directory):
    """CVEs sem correção disponível: visibilidade, nunca bloqueio (M11)."""
    if directory is None:
        return {'status': MISSING}
    summary = load(directory / 'unfixed-cves-summary.json')
    if summary is None:
        return {'status': MISSING}
    counts, errors = {}, []
    for arch, entries in (summary.get('architectures') or {}).items():
        if isinstance(entries, dict) and 'error' in entries:
            errors.append(f"{arch}: {entries['error']}")
            counts[arch] = None
            continue
        counts[arch] = len(entries)
    return {'status': 'indisponível' if errors else 'coletado',
            'counts': counts, 'errors': errors}


def runtime_result(directory, framework):
    """Contrato funcional executado sobre o artifact candidato (M08/M10)."""
    if directory is None:
        return {'status': MISSING, 'platforms': {}}
    platforms = {}
    for arch in ARCHITECTURES:
        report = load(directory / f'runtime-{framework}-{arch}.json')
        if report is None:
            platforms[arch] = {'status': MISSING}
            continue
        platforms[arch] = {'status': report.get('status'),
                           'execution': report.get('execution'),
                           'contract': report.get('contract'),
                           'error': report.get('error')}
    statuses = {platform['status'] for platform in platforms.values()}
    if statuses == {'passed'}:
        status = 'aprovado'
    elif statuses == {MISSING}:
        status = MISSING
    else:
        status = 'reprovado'
    return {'status': status, 'platforms': platforms,
            'reason': '; '.join(f"{arch}: {platform['error']}"
                                for arch, platform in platforms.items() if platform.get('error'))}


def publication_result(directory):
    if directory is None:
        return {'status': 'não publicado'}
    evidence = load(directory / 'publication-evidence.json')
    if evidence is None:
        return {'status': 'não publicado', 'reason': 'evidência de publicação ausente'}
    return {'status': 'publicado', 'digest': evidence.get('remote_digest'),
            'image_ref': evidence.get('image_ref'),
            'platforms': list((evidence.get('platforms') or {}))}


def promotion_result(directory):
    if directory is None:
        return {'status': '—'}
    evidence = load(directory / 'promotion-evidence.json')
    if evidence is None:
        return {'status': MISSING}
    if evidence.get('promoted'):
        return {'status': 'promovido', 'digest': evidence.get('digest'),
                'tag': evidence.get('tag'), 'stable_age_hours': evidence.get('stable_age_hours')}
    return {'status': 'não promovido', 'reason': evidence.get('reason'),
            'stable_age_hours': evidence.get('stable_age_hours')}


def collect(root, frameworks=(), annotate_plan=False):
    found = evidence_map(root)
    names = sorted(set(frameworks) | {framework for _, framework in found})
    # Cobertura funcional planejada para ESTE lote, pelo mesmo código que
    # montou a matriz: um framework sem contrato aparece com o motivo, não
    # como buraco na tabela. Só faz sentido num run que executa contratos —
    # num run de promoção, o motivo do lote de build seria enganoso.
    _, skipped = plan(frameworks) if annotate_plan and frameworks else ((), {})
    rows = {}
    for framework in names:
        scans = found.get(('build-scans', framework))
        functional = runtime_result(found.get(('runtime', framework)), framework)
        if framework in skipped and functional['status'] == MISSING:
            functional['status'] = 'não executado'
            functional['reason'] = skipped[framework]
        rows[framework] = {
            'scan': scan_result(scans),
            'unfixed': unfixed_result(scans),
            'runtime': functional,
            'publication': publication_result(found.get(('publication', framework))),
            'promotion': promotion_result(found.get(('promotion', framework))),
            'artifacts': sorted(directory.name for (_, name), directory in found.items()
                                if name == framework),
        }
    executions = {}
    for row in rows.values():
        for platform in row['runtime']['platforms'].values():
            if platform.get('execution'):
                executions[platform['execution']] = executions.get(platform['execution'], 0) + 1
    totals = {
        'frameworks': len(rows),
        'scan_blocked': sum(1 for row in rows.values() if row['scan']['status'] == 'bloqueado'),
        'scan_infrastructure_error': sum(1 for row in rows.values()
                                         if row['scan']['status'] == 'erro de infraestrutura'),
        'without_evidence': sum(1 for row in rows.values() if row['scan']['status'] == MISSING),
        'published': sum(1 for row in rows.values() if row['publication']['status'] == 'publicado'),
        'promoted': sum(1 for row in rows.values() if row['promotion']['status'] == 'promovido'),
        'runtime_contract_failed': sum(1 for row in rows.values()
                                       if row['runtime']['status'] == 'reprovado'),
        'runtime_executions': executions,
    }
    return {'frameworks': rows, 'totals': totals}


def short(digest):
    return f'`{digest[7:19]}…`' if isinstance(digest, str) and digest.startswith('sha256:') else '—'


def architectures_cell(row):
    """Arquiteturas cobertas, com execução nativa/emulada quando houver teste."""
    cells = []
    for arch in ARCHITECTURES:
        scan = row['scan']['platforms'].get(arch, {})
        functional = row['runtime']['platforms'].get(arch, {})
        mark = 'ok' if scan.get('status') == 'aprovado' else '—'
        execution = functional.get('execution')
        cells.append(f'{arch}: {mark}' + (f' ({execution})' if execution else ''))
    return '<br>'.join(cells)


def unfixed_cell(unfixed):
    if unfixed['status'] != 'coletado':
        return unfixed['status']
    counts = unfixed.get('counts') or {}
    return ' / '.join(f'{arch}: {"?" if value is None else value}'
                      for arch, value in sorted(counts.items())) or '—'


def artifact_links(names, repository, run_id, ids):
    if not names:
        return '—'
    links = []
    for name in names:
        artifact = name
        if ids and name not in ids:
            kind, _ = artifact_name(name)
            attempt = ATTEMPT.search(name)
            if kind in ('promotion', 'promotion-scans') and attempt:
                artifact = f'{kind}-batch-{attempt.group(1)}'
        if ids and artifact in ids and repository and run_id:
            links.append(f'[{name}](https://github.com/{repository}/actions/runs/{run_id}'
                         f'/artifacts/{ids[artifact]})')
        else:
            links.append(f'`{name}`')
    return '<br>'.join(links)


def reason_cell(row):
    reasons = [row['scan'].get('reason'), row['runtime'].get('reason'),
               row['publication'].get('reason'), row['promotion'].get('reason')]
    return '; '.join(reason for reason in reasons if reason) or '—'


def render(summary, repository='', run_id='', artifact_ids=None, title='Resultado por framework'):
    totals = summary['totals']
    lines = [f'## {title}', '',
             f"{totals['frameworks']} framework(s): {totals['published']} publicado(s), "
             f"{totals['promoted']} promovido(s), {totals['scan_blocked']} bloqueado(s) por scan, "
             f"{totals['scan_infrastructure_error']} com erro de infraestrutura, "
             f"{totals['runtime_contract_failed']} com contrato funcional reprovado, "
             f"{totals['without_evidence']} sem evidência.", '']
    if totals['runtime_executions']:
        lines += ['Execuções do contrato funcional: '
                  + ', '.join(f'{mode} {count}'
                              for mode, count in sorted(totals['runtime_executions'].items()))
                  + '.', '']
    lines += ['| Framework | Digest validado | Arquiteturas | Scan (gate) | CVEs sem correção '
              '| Contrato funcional | Publicação | Promoção | Motivo | Evidências |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for framework, row in summary['frameworks'].items():
        # O digest que importa é o do índice multi-arquitetura: é ele que é
        # publicado, promovido e recuperado.
        validated = row['scan']['platforms'].get('amd64', {}).get('index_digest')
        cells = [f'`{framework}`', short(row['publication'].get('digest') or validated),
                 architectures_cell(row), row['scan']['status'], unfixed_cell(row['unfixed']),
                 row['runtime']['status'], row['publication']['status'],
                 row['promotion']['status'], reason_cell(row),
                 artifact_links(row['artifacts'], repository, run_id, artifact_ids)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines += ['',
              '`Scan (gate)` usa `--ignore-unfixed`: bloqueia só o que tem correção disponível. '
              '`CVEs sem correção` é visibilidade, não gate. `erro de infraestrutura` não é '
              'resultado de segurança — não pode ser lido como aprovação.', '']
    references = [(framework, row['publication'].get('image_ref'))
                  for framework, row in summary['frameworks'].items()
                  if row['publication'].get('image_ref')]
    if references:
        lines += ['<details><summary>Referências publicadas (digest completo)</summary>', '']
        lines += [f'- `{framework}`: `{reference}`' for framework, reference in references]
        lines += ['', '</details>', '']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', help='diretório com os artifacts baixados')
    parser.add_argument('--frameworks', default='[]',
                        help='JSON array esperado no run; entra na tabela mesmo sem evidência')
    parser.add_argument('--repository', default='')
    parser.add_argument('--run-id', default='')
    parser.add_argument('--artifacts', type=Path,
                        help='saída de `gh api .../actions/runs/<id>/artifacts` para links diretos')
    parser.add_argument('--title', default='Resultado por framework')
    parser.add_argument('--annotate-contract-plan', action='store_true',
                        help='marca o motivo de um contrato funcional não ter rodado neste lote')
    parser.add_argument('--markdown', type=Path, help='arquivo de saída (ex.: $GITHUB_STEP_SUMMARY)')
    parser.add_argument('--json', type=Path, dest='json_output')
    args = parser.parse_args()
    frameworks = json.loads(args.frameworks)
    if not isinstance(frameworks, list):
        raise SystemExit('--frameworks precisa ser um array JSON')
    summary = collect(args.evidence, frameworks, args.annotate_contract_plan)
    ids = None
    if args.artifacts and args.artifacts.is_file():
        listing = load(args.artifacts) or {}
        ids = {item['name']: item['id'] for item in listing.get('artifacts') or []}
    markdown = render(summary, args.repository, args.run_id, ids, args.title)
    if args.markdown:
        with args.markdown.open('a') as output:
            output.write(markdown)
    else:
        print(markdown, end='')
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(summary, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
