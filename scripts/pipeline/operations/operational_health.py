#!/usr/bin/env python3
"""Saúde operacional do pipeline (M11/M04): o que medir e quando alertar.

Mede, com dados reais da API do GitHub (nada sintético):

- idade da tag `stable` por framework — quando o ponteiro foi movido pela
  última vez, lido do passo `Promote to stable` do job de promoção, que
  distingue "promoveu" de "rodou e pulou por não ter candidato";
- última publicação bem-sucedida por framework, pelo job de publicação;
- execução esperada x real do cron: as ocorrências que o cron deveria ter
  gerado na janela, quais viraram run e quais não — a ausência de run é o
  caso que passa despercebido, porque não existe run vermelho para olhar;
- atraso de fila: `created_at` -> `run_started_at`, que é espera por runner,
  não duração de job.

E `retention`, offline: confirma que a retenção declarada na política
(`policies/operations/health.json`) é a que os workflows realmente usam. Uma
política que diverge do `retention-days` efetivo não protege prazo nenhum.

Exceções conhecidas (framework fora do lote padrão por decisão registrada,
ex.: `dotnet8` até sua remoção do catálogo em 17/09/2026) são reportadas como
conhecidas,
com dono e data de revisão: sem isso, um bloqueio permanente vira ruído e
treina quem lê a ignorar o alerta. Uma exceção com revisão vencida gera
alerta própria — a exceção também não pode apodrecer em silêncio.

Este script mede e classifica; ele não entrega notificação. Enquanto o
destino externo não estiver definido (ver `docs/m11-m04-operational-health.md`),
o canal é a falha deste job e a tabela no resumo do run.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import statistics
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[3]
PUBLISH_JOB = 'Build & push {framework}'
PROMOTE_JOB = 'Promote {framework}'
PROMOTE_STEP = 'Promote to stable'


def moment(timestamp):
    if not timestamp:
        return None
    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))


def age_hours(timestamp, now):
    instant = moment(timestamp)
    return None if instant is None else round((now - instant).total_seconds() / 3600, 2)


def distribution(values):
    values = sorted(value for value in values if value is not None)
    if not values:
        return {'samples': 0}
    index = max(0, int(round(0.9 * (len(values) - 1))))
    return {'samples': len(values), 'median': round(statistics.median(values), 1),
            'p90': round(values[index], 1), 'max': round(values[-1], 1)}


def cron_field(spec, low, high):
    values = set()
    for part in spec.split(','):
        step = 1
        if '/' in part:
            part, raw = part.split('/', 1)
            step = int(raw)
        if part == '*':
            start, end = low, high
        elif '-' in part:
            start, end = (int(bound) for bound in part.split('-', 1))
        else:
            start = end = int(part)
        if not (low <= start <= end <= high) or step < 1:
            raise ValueError(f'campo de cron fora da faixa: {spec}')
        values |= set(range(start, end + 1, step))
    return values


def cron_occurrences(expression, start, end):
    """Ocorrências esperadas de um cron na janela [start, end].

    Só as formas que este repositório usa: minuto e hora com `*`, listas,
    faixas e passos; dia/mês/dia-da-semana precisam ser `*`. A semântica de
    OR entre dia-do-mês e dia-da-semana é uma armadilha conhecida do cron —
    em vez de implementá-la errado, recusa explicitamente.
    """
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(f'cron precisa de cinco campos: {expression!r}')
    minute, hour, day, month, weekday = fields
    if (day, month, weekday) != ('*', '*', '*'):
        raise ValueError(f'cron com restrição de dia/mês/semana não é suportado: {expression!r}')
    minutes, hours = cron_field(minute, 0, 59), cron_field(hour, 0, 23)
    current = start.replace(second=0, microsecond=0)
    if current < start:
        current += timedelta(minutes=1)
    occurrences = []
    while current <= end:
        if current.minute in minutes and current.hour in hours:
            occurrences.append(current)
        current += timedelta(minutes=1)
    return occurrences


def declared_schedules(policy):
    """Crons declarados na política; chaves `$...` são comentários."""
    return {cron: options for cron, options in (policy.get('schedules') or {}).items()
            if not cron.startswith('$')}


def executed_groups(jobs):
    """Grupos de job que realmente rodaram num run (não `skipped`).

    Um run agendado não diz qual cron o disparou — a API não expõe
    `github.event.schedule`. Mas os jobs dizem: o chamador condicionado ao
    cron diário aparece `skipped` num run da promoção horária e vice-versa.
    A atribuição sai do que rodou de fato, não de adivinhar pelo horário.
    """
    groups = {}
    for job in jobs or []:
        group = (job.get('name') or '').split(' / ')[0].strip()
        groups[group] = groups.get(group, False) or job.get('conclusion') != 'skipped'
    return {group for group, executed in groups.items() if executed}


def attribute_runs(jobs_for, runs, schedules):
    """Distribui os runs agendados entre os crons, pelo job que rodou."""
    attributed = {cron: [] for cron in schedules}
    unattributed = []
    for run in runs:
        if run.get('event') != 'schedule':
            continue
        groups = executed_groups(jobs_for(run['id']))
        matched = [cron for cron, options in schedules.items() if options['job'] in groups]
        if len(matched) == 1:
            attributed[matched[0]].append(run)
        else:
            # Nenhum job do cron rodou, ou mais de um: registrado como não
            # atribuído em vez de chutado para um dos crons.
            unattributed.append({'run_id': run['id'], 'created_at': run['created_at'],
                                 'executed_groups': sorted(groups)})
    return attributed, unattributed


def schedule_health(expression, runs, start, end, now):
    """Ocorrências esperadas x runs reais deste cron, com atraso e lacunas.

    O atraso de cada run é medido contra a última ocorrência anterior a ele —
    exato, sem depender de uma tolerância arbitrária. Ocorrência sem nenhum
    run atribuído é ocorrência que o agendador não entregou.
    """
    occurrences = cron_occurrences(expression, start, end)
    covered, delays, duplicates = {}, [], []
    for run in sorted(runs, key=lambda run: moment(run['created_at'])):
        created = moment(run['created_at'])
        previous = [occurrence for occurrence in occurrences if occurrence <= created]
        if not previous:
            continue
        occurrence = previous[-1]
        if occurrence in covered:
            duplicates.append(run['id'])
        covered.setdefault(occurrence, []).append(run['id'])
        delays.append((created - occurrence).total_seconds())
    times = sorted(moment(run['created_at']) for run in runs)
    gaps = [(later - earlier).total_seconds() / 3600
            for earlier, later in zip(times, times[1:])]
    return {'cron': expression, 'expected': len(occurrences), 'observed': len(times),
            'missing': [occurrence.isoformat() for occurrence in occurrences
                        if occurrence not in covered],
            'duplicate_runs': duplicates,
            'coverage_percent': round(100 * len(covered) / len(occurrences), 1)
            if occurrences else None,
            'trigger_delay_seconds': distribution(delays),
            'max_gap_hours': round(max(gaps), 2) if gaps else None,
            'hours_since_last_run': round((now - times[-1]).total_seconds() / 3600, 2)
            if times else None}


def queue_health(runs):
    """Espera por runner: created_at -> run_started_at, não duração de job."""
    delays = [(moment(run['run_started_at']) - moment(run['created_at'])).total_seconds()
              for run in runs if run.get('run_started_at') and run.get('created_at')]
    return distribution(delays)


def framework_health(jobs_for, runs, frameworks, now, max_queries=40):
    """Última publicação e última promoção efetiva de cada framework."""
    state = {framework: {} for framework in frameworks}

    def complete():
        return all('last_publication' in entry and 'last_promotion' in entry
                   for entry in state.values())

    queries, truncated = 0, False
    for run in sorted(runs, key=lambda run: moment(run['created_at']), reverse=True):
        # Only these main events can publish or promote. PRs and dispatches
        # on other branches cannot contribute evidence and must not consume
        # the query budget (the first hosted health run exhausted it on PRs).
        if run.get('event') not in ('push', 'schedule', 'workflow_dispatch') \
                or run.get('head_branch', 'main') != 'main':
            continue
        if complete():
            break
        if queries >= max_queries:
            truncated = True
            break
        jobs = jobs_for(run['id'])
        queries += 1
        for framework, entry in state.items():
            for job in jobs:
                name = job.get('name') or ''
                # Workflow reutilizável prefixa o nome do job chamador; o
                # sufixo é o nome real do job da matriz.
                if (name.endswith(PUBLISH_JOB.format(framework=framework))
                        and job.get('conclusion') == 'success'
                        and 'last_publication' not in entry):
                    entry['last_publication'] = job.get('completed_at')
                    entry['publication_run'] = run['id']
                if not name.endswith(PROMOTE_JOB.format(framework=framework)):
                    continue
                if job.get('conclusion') == 'success' and 'last_promotion_checked' not in entry:
                    entry['last_promotion_checked'] = job.get('completed_at')
                step = next((item for item in job.get('steps') or []
                             if item.get('name') == PROMOTE_STEP), None)
                if step and step.get('conclusion') == 'success' and 'last_promotion' not in entry:
                    entry['last_promotion'] = job.get('completed_at')
                    entry['promotion_run'] = run['id']
    for entry in state.values():
        entry['publication_age_hours'] = age_hours(entry.get('last_publication'), now)
        # Idade do ponteiro `stable`: quando ele foi movido pela última vez.
        # A imagem por trás dele é mais antiga que isso (passou pelo soak);
        # o `imagePushedAt` exato sai da evidência de promoção.
        entry['stable_age_hours'] = age_hours(entry.get('last_promotion'), now)
        entry['promotion_checked_age_hours'] = age_hours(entry.get('last_promotion_checked'), now)
    return {'frameworks': state, 'job_queries': queries, 'truncated': truncated,
            'note': 'sem dado na janela não significa "nunca": ver truncated e a janela'}


def evaluate(metrics, policy, now):
    """Alertas, separando falha real de exceção conhecida e documentada."""
    thresholds = policy['thresholds']
    exceptions = policy.get('exceptions') or {}
    # ADR-0004: `execution_scope` é distinto de `exceptions` -- não alimenta
    # default_batch.py::exclusions() nem remove nada do lote FULL/DEFAULT.
    # Ausente = sem restrição (todo framework é "em escopo", igual ao
    # comportamento anterior a este campo). Presente = frameworks fora de
    # `current` não geram `alert` de publicação/stable ausente; geram
    # `out_of_scope`, visível e não bloqueante, pela mesma razão de
    # `known`: visibilidade sem alarme, nunca ausência de visibilidade.
    execution_scope = policy.get('execution_scope') or {}
    current_scope = execution_scope.get('current')
    alerts = []

    def add(level, metric, subject, message):
        alerts.append({'level': level, 'metric': metric, 'subject': subject, 'message': message})

    # Busca truncada pelo limite de chamadas: ausência de dado é dado que
    # falta, não falha comprovada. Alertar aqui seria alarme por não ter
    # olhado o suficiente; o truncamento em si é reportado separadamente.
    truncated = metrics['frameworks']['truncated']
    for framework, entry in sorted(metrics['frameworks']['frameworks'].items()):
        exception = exceptions.get(framework)
        in_scope = current_scope is None or framework in current_scope
        if not in_scope:
            level = 'out_of_scope'
            suffix = f" (fora do escopo de execução atual: {execution_scope.get('reason', '')})"
        elif exception:
            level = 'known'
            suffix = f" (exceção conhecida: {exception['reason']})"
        else:
            level = 'alert'
            suffix = ''
        for metric, limit in (('publication_age_hours', thresholds['publication_age_hours']),
                              ('stable_age_hours', thresholds['stable_age_hours'])):
            age = entry.get(metric)
            if age is None:
                add('unknown' if truncated else level, metric, framework,
                    'sem dado na janela analisada'
                    + (' (busca de jobs truncada)' if truncated else '') + suffix)
            elif age > limit:
                add(level, metric, framework, f'{metric} em {age}h (limite {limit}h){suffix}')
    if truncated:
        add('alert', 'job_queries_truncated', metrics['workflow'],
            f"busca de jobs parou em {metrics['frameworks']['job_queries']} run(s): aumente "
            '--max-job-queries ou reduza a janela para medir sem lacuna')

    for schedule in metrics['schedules']:
        limit = declared_schedules(policy)[schedule['cron']]['gap_alert_hours']
        since = schedule['hours_since_last_run']
        if since is None:
            add('alert', 'schedule_gap_hours', schedule['cron'],
                'nenhum run agendado deste cron na janela analisada — cron que não gera '
                'run não deixa run vermelho para ninguém ver')
        elif since > limit:
            add('alert', 'schedule_gap_hours', schedule['cron'],
                f'último run agendado há {since}h (limite {limit}h)')
        elif schedule['max_gap_hours'] and schedule['max_gap_hours'] > limit:
            add('alert', 'schedule_gap_hours', schedule['cron'],
                f"maior intervalo entre runs na janela: {schedule['max_gap_hours']}h "
                f'(limite {limit}h)')

    for framework, exception in sorted(exceptions.items()):
        review = moment(exception.get('review_by') + 'T00:00:00+00:00'
                        if exception.get('review_by') else None)
        if review is None:
            add('alert', 'exception_review', framework, 'exceção sem `review_by` definido')
        elif review < now:
            add('alert', 'exception_review', framework,
                f"exceção vencida em {exception['review_by']}, dono {exception.get('owner')}")

    # Mesma disciplina de revisão de `exceptions`, agora para o escopo de
    # execução (ADR-0004): sem isso, `execution_scope` poderia congelar o
    # catálogo Go-only indefinidamente sem nunca virar um alerta próprio.
    if current_scope is not None:
        review = moment(execution_scope.get('review_by') + 'T00:00:00+00:00'
                        if execution_scope.get('review_by') else None)
        subject = 'execution_scope'
        if review is None:
            add('alert', 'execution_scope_review', subject,
                '`execution_scope` sem `review_by` definido')
        elif review < now:
            add('alert', 'execution_scope_review', subject,
                f"escopo de execução vencido em {execution_scope['review_by']}, "
                f"dono {execution_scope.get('owner')}")
    return alerts


def workflow_created_at(fetch, repository, workflow_path):
    """Quando o agendador passou a conhecer este workflow.

    Ocorrência anterior a isso nunca foi esperada — contá-la como ausente
    inventaria uma falha que não existiu.
    """
    listing = fetch(f'repos/{repository}/actions/workflows?per_page=100') or {}
    for workflow in listing.get('workflows') or []:
        if workflow.get('path') == workflow_path:
            return moment(workflow.get('created_at'))
    return None


def collect(fetch, repository, policy, now, max_queries=40):
    window_days = policy['thresholds']['window_days']
    start = now - timedelta(days=window_days)
    schedules = declared_schedules(policy)
    problems = schedule_declaration(policy)
    if problems:
        raise ValueError('política e workflows discordam sobre os crons: ' + '; '.join(problems))
    workflow_paths = sorted({options['workflow'] for options in schedules.values()})
    crons = sorted(schedules)
    # Catálogo como fonte única: todo framework versionado deveria estar
    # sendo publicado e promovido. Uma lista à parte na política divergiria
    # do catálogo em silêncio.
    frameworks = sorted(path.stem for path in (ROOT / 'frameworks').glob('*.yaml'))

    # O build diário e a promoção horária vivem em arquivos de workflow
    # diferentes desde a separação de schedules; a janela efetiva usa o mais
    # antigo dos dois, para não contar uma ocorrência anterior à existência
    # de qualquer um deles como ausente.
    created = [instant for instant in
              (workflow_created_at(fetch, repository, path) for path in workflow_paths)
              if instant is not None]
    effective_start = max(start, min(created)) if created else start
    end = now

    runs = []
    for page in range(1, 7):
        batch = (fetch(f'repos/{repository}/actions/runs?per_page=100&page={page}')
                 or {}).get('workflow_runs') or []
        runs += batch
        if not batch or moment(batch[-1]['created_at']) < effective_start:
            break
    window_runs = [run for run in runs
                   if moment(run['created_at']) >= effective_start
                   and run.get('path') in workflow_paths]

    cache = {}

    def jobs_for(run_id):
        if run_id not in cache:
            cache[run_id] = (fetch(f'repos/{repository}/actions/runs/{run_id}/jobs?per_page=100')
                             or {}).get('jobs') or []
        return cache[run_id]

    attributed, unattributed = attribute_runs(jobs_for, window_runs, schedules)
    return {
        'generated_at': now.isoformat(),
        'window': {'requested_start': start.isoformat(), 'start': effective_start.isoformat(),
                   'end': end.isoformat(), 'days': window_days,
                   'workflow_created_at': min(created).isoformat() if created else None},
        'workflow': ', '.join(workflow_paths),
        'runs_analysed': len(window_runs),
        'schedules': [dict(schedule_health(cron, attributed[cron], effective_start, end, now),
                           purpose=schedules[cron].get('purpose'))
                      for cron in crons],
        'unattributed_scheduled_runs': unattributed,
        'queue': queue_health(window_runs),
        'frameworks': framework_health(jobs_for, window_runs, frameworks, now, max_queries),
    }


def upload_retentions(paths):
    """Retenção efetiva de cada artifact declarado nos workflows."""
    entries = []
    for path in paths:
        document = yaml.safe_load(path.read_text())
        for job_id, job in (document.get('jobs') or {}).items():
            for step in job.get('steps') or []:
                uses = step.get('uses') or ''
                if not uses.startswith('actions/upload-artifact'):
                    continue
                options = step.get('with') or {}
                name = str(options.get('name', ''))
                entries.append({'file': path.name, 'job': job_id, 'name': name,
                                'prefix': name.split('${{')[0],
                                'retention_days': options.get('retention-days')})
    return entries


def retention_drift(entries, policy):
    """A política escrita tem de ser a retenção que os workflows aplicam."""
    # Chaves `$...` são comentários da política, não prefixos de artifact.
    declared = {key: value for key, value in policy['retention_days'].items()
                if not key.startswith('$')}
    problems, used = [], set()
    for entry in entries:
        keys = [key for key in declared if entry['prefix'].startswith(key)]
        if not keys:
            problems.append(f"{entry['file']}: artifact `{entry['name']}` não tem retenção "
                            'definida na política de evidências')
            continue
        key = max(keys, key=len)
        used.add(key)
        if entry['retention_days'] != declared[key]:
            problems.append(f"{entry['file']}: artifact `{entry['name']}` usa "
                            f"retention-days={entry['retention_days']}, política diz "
                            f'{declared[key]} dia(s) para `{key}`')
    for key in sorted(set(declared) - used):
        problems.append(f'política define retenção para `{key}`, que nenhum workflow usa mais')
    return problems


def render(metrics, alerts):
    window = metrics['window']
    lines = ['## Saúde operacional (M11/M04)', '',
             f"Janela: {window['start']} → {window['end']} "
             f"({window['days']} dia(s) pedidos; início limitado pela criação do workflow em "
             f"{window['workflow_created_at']}) — {metrics['runs_analysed']} run(s) de "
             f"`{metrics['workflow']}`.", '',
             '| Cron | Finalidade | Ocorrências | Runs | Cobertura | Atraso de disparo p90 '
             '| Maior intervalo | Último run |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for schedule in metrics['schedules']:
        delay = schedule['trigger_delay_seconds'].get('p90', '—')
        lines.append(f"| `{schedule['cron']}` | {schedule.get('purpose') or '—'} "
                     f"| {schedule['expected']} | {schedule['observed']} "
                     f"| {schedule['coverage_percent']}% | {delay}s "
                     f"| {schedule['max_gap_hours'] or '—'}h "
                     f"| há {schedule['hours_since_last_run'] or '—'}h |")
    if metrics['unattributed_scheduled_runs']:
        lines += ['', f"{len(metrics['unattributed_scheduled_runs'])} run(s) agendado(s) sem "
                  'cron atribuível (nenhum job condicionado ao cron rodou).']
    queue = metrics['queue']
    lines += ['', f"Espera por runner: {queue.get('samples', 0)} amostra(s), mediana "
              f"{queue.get('median', '—')}s, p90 {queue.get('p90', '—')}s, "
              f"máximo {queue.get('max', '—')}s.", '',
              '| Framework | Última publicação (h) | `stable` movido há (h) '
              '| Promoção avaliada há (h) |', '| --- | --- | --- | --- |']
    for framework, entry in sorted(metrics['frameworks']['frameworks'].items()):
        cells = [entry.get(key) for key in ('publication_age_hours', 'stable_age_hours',
                                            'promotion_checked_age_hours')]
        lines.append(f'| `{framework}` | '
                     + ' | '.join('sem dado' if value is None else str(value)
                                  for value in cells) + ' |')
    if metrics['frameworks']['truncated']:
        lines += ['', '⚠️ Consulta de jobs truncada pelo limite de chamadas: "sem dado" aqui '
                  'não quer dizer "nunca aconteceu".']
    lines += ['', '### Alertas', '',
              '`alert` rompe limite da política; `known` é exceção documentada com dono e data '
              'de revisão; `out_of_scope` está fora do escopo de execução atual (ADR-0004), '
              'não é exceção nem exclusão de catálogo; `unknown` é medida que faltou dado, '
              'não falha comprovada.', '']
    if not alerts:
        lines.append('Nenhum alerta.')
    else:
        lines += ['| Nível | Métrica | Assunto | Mensagem |', '| --- | --- | --- | --- |']
        lines += [f"| {alert['level']} | `{alert['metric']}` | `{alert['subject']}` "
                  f"| {alert['message']} |" for alert in alerts]
    return '\n'.join(lines) + '\n'


def gh_json(path):
    result = subprocess.run(['gh', 'api', path], check=False, capture_output=True,
                            text=True, timeout=120)
    if result.returncode:
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


def workflow_files():
    # Retention of artifacts the shared workflow uploads is that library's own
    # policy, verified by its own CI (see alric-containers-reusable-workflows);
    # this only covers artifacts this repository's own workflows upload.
    from scripts.pipeline.governance.workflow_dependencies import local_workflows
    return local_workflows(ROOT)


def scheduled_crons(root=ROOT):
    """Todo cron agendado nativamente por algum `.github/workflows/*.yml`, mapeado
    para o(s) arquivo(s) que o declaram."""
    found = {}
    for path in sorted((root / '.github/workflows').glob('*.yml')):
        workflow = yaml.safe_load(path.read_text()) or {}
        triggers = workflow.get(True) or workflow.get('on') or {}
        for entry in triggers.get('schedule') or []:
            found.setdefault(entry['cron'], []).append(str(path.relative_to(root)))
    return found


def schedule_declaration(policy):
    """A política tem de declarar exatamente os crons agendados nos workflows do
    repositório, cada um apontando para o arquivo que de fato o agenda."""
    declared = declared_schedules(policy)
    actual = scheduled_crons()
    problems = [f'cron `{cron}` agendado em mais de um workflow: {", ".join(files)}'
                for cron, files in sorted(actual.items()) if len(files) > 1]
    problems += [f'cron `{cron}` agendado em {", ".join(actual[cron])} sem declaração na '
                 'política (job de atribuição e limite de lacuna)'
                 for cron in sorted(set(actual) - set(declared))]
    problems += [f'política declara o cron `{cron}`, que nenhum workflow agenda mais'
                 for cron in sorted(set(declared) - set(actual))]
    for cron in sorted(set(actual) & set(declared)):
        options = declared[cron]
        missing = [key for key in ('job', 'workflow', 'purpose', 'gap_alert_hours')
                   if key not in options]
        if missing:
            problems.append(f'cron `{cron}` sem {", ".join(missing)} na política')
        elif options['workflow'] not in actual[cron]:
            problems.append(f'cron `{cron}` declarado para {options["workflow"]} na política, '
                            f'mas agendado em {", ".join(actual[cron])}')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('report', 'lint'))
    parser.add_argument('--policy', type=Path, default=ROOT / 'policies/operations/health.json')
    parser.add_argument('--repository', default='')
    parser.add_argument('--markdown', help='arquivo de saída (ex.: $GITHUB_STEP_SUMMARY)')
    parser.add_argument('--json', dest='json_output', type=Path)
    parser.add_argument('--max-job-queries', type=int, default=40)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())

    if args.mode == 'lint':
        problems = (retention_drift(upload_retentions(workflow_files()), policy)
                    + schedule_declaration(policy))
        for problem in problems:
            print(f'::error::{problem}', file=sys.stderr)
        print(f'Retenção e agendamento conferidos em {len(workflow_files())} workflow(s).')
        return 1 if problems else 0

    if not args.repository:
        raise SystemExit('--repository é obrigatório no modo report')
    now = datetime.now(timezone.utc)
    metrics = collect(gh_json, args.repository, policy, now, max_queries=args.max_job_queries)
    alerts = evaluate(metrics, policy, now)
    metrics['alerts'] = alerts
    markdown = render(metrics, alerts)
    if args.markdown:
        with Path(args.markdown).open('a') as output:
            output.write(markdown)
    else:
        print(markdown, end='')
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(metrics, indent=2) + '\n')
    blocking = [alert for alert in alerts if alert['level'] == 'alert']
    for alert in blocking:
        print(f"::error::{alert['metric']} / {alert['subject']}: {alert['message']}",
              file=sys.stderr)
    return 1 if blocking else 0


if __name__ == '__main__':
    raise SystemExit(main())
