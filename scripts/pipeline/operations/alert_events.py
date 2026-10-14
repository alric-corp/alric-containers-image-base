"""Eventos de alerta a partir dos relatórios do health, sem entrega externa (G05).

O job de health já detecta (pins e saúde operacional) e falha; este módulo
transforma o que ele encontrou em eventos estáveis e mínimos, que um destino
externo aprovado poderia receber, e registra o que aconteceu com cada um:

- identidade: `event_id` resume só origem, métrica e assunto, então a mesma
  condição mantém o mesmo id entre runs (deduplicação); `occurrence_id`
  identifica esta detecção (run e tentativa);
- classificação: severidade de `policies/operations/alerting.json`; `known` e
  `out_of_scope` ficam visíveis como suprimidos, nunca descartados em silêncio;
- minimização: só campos da allow-list saem do repositório, com resumo
  truncado e contas AWS, ARNs, tokens e credenciais mascarados;
- entrega: o destino externo é null por decisão do owner (health.json), então
  o canal é o próprio run (falha do job + resumo). `deliver` existe para um
  destino aprovado e é exercitado somente com transportes simulados;
- reconhecimento: nunca inferido. HTTP 2xx é no máximo ACCEPTED pelo destino;
  o ACK humano continua NOT_PROVEN até existir um registro dele.

A CLI nunca muda o resultado do health: sai 0 com qualquer alerta e 2 só
quando o próprio contrato é inválido.
"""
import argparse
from collections import namedtuple
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / 'policies/operations/alerting.json'
HEALTH_POLICY = ROOT / 'policies/operations/health.json'
SCHEMA_VERSION = 1
SEVERITIES = ('critical', 'high', 'medium', 'low')
CHANNEL = 'github-actions-run'
# Statuses a destination can produce; none of them is a human acknowledgement.
NOT_CONFIGURED, ACCEPTED, AMBIGUOUS = 'NOT_CONFIGURED', 'ACCEPTED', 'AMBIGUOUS'
NOT_PROVEN = 'NOT_PROVEN'
# Ordered: ARNs before the bare account ids they contain.
REDACTIONS = (
    (re.compile(r'(?i)\bbearer\s+[a-z0-9._~+/-]+=*'), 'Bearer <redacted>'),
    (re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}'), '<redacted-token>'),
    (re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}'), '<redacted-token>'),
    (re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'), '<redacted-key>'),
    (re.compile(r'(https?://)[^/\s:@]+:[^/\s@]+@'), r'\1<redacted>@'),
    (re.compile(r'\barn:aws[a-z-]*:[^\s,;)]+'), '<arn>'),
    (re.compile(r'\b\d{12}\b'), '<aws-account>'),
    (re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+'), '<email>'),
)
Response = namedtuple('Response', 'status body')


class TransportTimeout(Exception):
    """No answer in time; the destination may have processed the request."""


class TransportError(Exception):
    """Connection failure; `sent` tells whether the request left the runner."""

    def __init__(self, message, sent=False):
        super().__init__(message)
        self.sent = sent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_policy(path=POLICY):
    policy = json.loads(Path(path).read_text())
    require(isinstance(policy, dict) and set(policy) - {'$comment'} == {
        'schema_version', 'status', 'routing_key', 'routed_levels', 'suppressed_levels',
        'severity', 'payload', 'delivery', 'acknowledgement'}, 'alerting policy: unexpected keys')
    require(policy['schema_version'] == SCHEMA_VERSION, 'alerting policy: unsupported schema')
    require(isinstance(policy['routing_key'], str) and re.fullmatch(r'[a-z0-9-]{1,64}', policy['routing_key']),
            'alerting policy: invalid routing_key')
    require(not set(policy['routed_levels']) & set(policy['suppressed_levels']),
            'alerting policy: a level cannot be routed and suppressed')
    severity = policy['severity']
    require(severity.get('default') in SEVERITIES
            and all(value in SEVERITIES for value in severity.get('metrics', {}).values()),
            'alerting policy: unknown severity')
    require(80 <= policy['payload'].get('max_summary_chars', 0) <= 1000,
            'alerting policy: summary limit out of range')
    delivery = policy['delivery']
    require(1 <= delivery['timeout_seconds'] <= 30 and 1 <= delivery['max_attempts'] <= 5
            and len(delivery['backoff_seconds']) == delivery['max_attempts'] - 1
            and all(0 <= value <= 60 for value in delivery['backoff_seconds']),
            'alerting policy: delivery bounds out of range')
    # Until an owner-approved record exists, ACK can only be NOT_PROVEN.
    require(policy['acknowledgement'] == {'required': True, 'record': None},
            'alerting policy: acknowledgement must stay required and unrecorded')
    return policy


def external_destination(path=HEALTH_POLICY):
    return (json.loads(Path(path).read_text()).get('channel') or {}).get('external_destination')


def sanitize(text, limit, secrets=()):
    text = ' '.join(str(text).split())
    for secret in secrets:
        if secret:
            text = text.replace(secret, '<redacted>')
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def event_id(source, metric, subject):
    identity = json.dumps({'source': source, 'metric': metric, 'subject': subject},
                          sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(identity.encode()).hexdigest()


def findings(health, pins):
    """Raw (source, level, metric, subject, message, blocking) tuples."""
    found = []
    alerts = health.get('alerts') if isinstance(health, dict) else None
    if not isinstance(alerts, list) or not all(isinstance(item, dict) for item in alerts):
        found.append(('health_monitor', 'alert', 'health_report_missing', 'operational-health',
                      'relatório de saúde operacional ausente ou inválido', True))
    else:
        for item in alerts:
            level = str(item.get('level'))
            found.append(('operational_health', level, str(item.get('metric')), str(item.get('subject')),
                          str(item.get('message', '')), level == 'alert'))
    entries = pins.get('pins') if isinstance(pins, dict) else None
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        found.append(('health_monitor', 'alert', 'pins_report_missing', 'tool-pins',
                      'relatório de pins ausente ou inválido', True))
        return found
    for item in entries:
        if item.get('available') is True:
            continue
        name = f"{item.get('name')}@{item.get('current')}"
        if item.get('kind') == 'local-key':
            metric, message = 'wolfi_key_status', f"chave Wolfi: {item.get('remote_status')}"
        elif item.get('available') is False:
            metric, message = 'pin_unavailable', f"pin indisponível na origem ({item.get('file')})"
        else:
            metric, message = 'pin_unverified', f"pin não verificado ({item.get('file')})"
        found.append(('pin_inventory', 'alert' if item.get('available') is False else 'unknown',
                      metric, name, message, item.get('available') is False))
    return found


def run_context(environ=os.environ):
    repository, run_id = environ.get('GITHUB_REPOSITORY', ''), environ.get('GITHUB_RUN_ID', '')
    server = environ.get('GITHUB_SERVER_URL', 'https://github.com')
    return {'repository': repository, 'workflow': environ.get('GITHUB_WORKFLOW', ''),
            'run_id': run_id, 'run_attempt': environ.get('GITHUB_RUN_ATTEMPT', ''),
            'sha': environ.get('GITHUB_SHA', ''),
            'url': f'{server}/{repository}/actions/runs/{run_id}' if repository and run_id else ''}


def build(health, pins, policy, run, now, test_event=False):
    """Routed events plus visible suppressions; inputs are never modified."""
    limit = policy['payload']['max_summary_chars']
    severity = policy['severity']
    detected_at = health.get('generated_at') if isinstance(health, dict) else None
    found = findings(health, pins)
    if test_event:
        found.append(('health_monitor', 'test', 'alert_pipeline_test', 'controlled-test',
                      'evento de teste controlado; não indica falha', False))
    events, suppressed, seen = [], [], {}
    for source, level, metric, subject, message, blocking in found:
        if level in policy['suppressed_levels']:
            suppressed.append({'level': level, 'metric': metric,
                               'subject': sanitize(subject, 120)})
            continue
        identity = event_id(source, metric, subject)
        if identity in seen:
            seen[identity]['repetitions'] += 1
            continue
        test = metric == 'alert_pipeline_test'
        # A metric added to the health without classification still routes,
        # visibly marked, instead of being dropped.
        classified = test or metric in severity['metrics']
        event = {
            'schema_version': SCHEMA_VERSION, 'event_id': identity,
            'occurrence_id': f"{run['run_id'] or 'local'}-{run['run_attempt'] or '0'}-{identity[:16]}",
            'state': 'firing', 'test': test,
            'severity': 'low' if test else severity['metrics'].get(metric, severity['default']),
            'severity_source': 'policy' if classified else 'default',
            'blocking': blocking, 'source': source, 'level': level, 'metric': metric,
            'subject': sanitize(subject, 120), 'summary': sanitize(message, limit),
            'detected_at': detected_at or now.isoformat(), 'routing_key': policy['routing_key'],
            'run': run, 'repetitions': 1,
            'acknowledgement': {'required': True, 'status': NOT_PROVEN},
        }
        seen[identity] = event
        events.append(event)
    return events, suppressed


def _receipt(body, field):
    try:
        document = json.loads(body.decode() if isinstance(body, bytes) else body)
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None
    value = document.get(field) if isinstance(document, dict) and field else None
    return value if isinstance(value, (str, int)) and str(value).strip() else None


def deliver(events, destination, settings, transport=None, credential='', sleep=time.sleep):
    """Delivery attempts for an approved destination; never an acknowledgement.

    Retries are bounded and only when safe: the request never left the runner,
    the destination signalled it did not process it (408/429), or it
    deduplicates by idempotency key. A 2xx without the destination's receipt
    field is AMBIGUOUS and is not retried blindly.
    """
    if destination is None:
        return [{'event_id': event['event_id'], 'occurrence_id': event['occurrence_id'],
                 'destination': None, 'status': NOT_CONFIGURED, 'attempts': 0, 'acknowledged': False}
                for event in events]
    require(transport is not None, 'destination configured without an approved transport')
    idempotent = destination.get('idempotency_key_supported') is True
    records = []
    for event in events:
        body = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
        headers = {'Content-Type': 'application/json', 'Idempotency-Key': event['occurrence_id']}
        if credential:
            headers['Authorization'] = 'Bearer ' + credential
        attempts, http_status, receipt, detail = 0, None, None, ''
        while True:
            attempts += 1
            retry = False
            try:
                response = transport(body, headers, settings['timeout_seconds'])
            except TransportTimeout as error:
                status, retry, detail = 'FAILED_TIMEOUT', idempotent, str(error)
            except TransportError as error:
                status, retry, detail = 'FAILED_TRANSPORT', not error.sent or idempotent, str(error)
            else:
                http_status = response.status
                if 200 <= response.status < 300:
                    receipt = _receipt(response.body, destination.get('receipt_field'))
                    status = ACCEPTED if receipt is not None else AMBIGUOUS
                elif response.status in (401, 403):
                    status = 'FAILED_AUTH'
                elif response.status in (408, 429):
                    status, retry = 'FAILED_HTTP', True
                elif response.status >= 500:
                    status, retry = 'FAILED_HTTP', idempotent
                else:
                    status = 'FAILED_HTTP'
            if not retry or attempts >= settings['max_attempts']:
                break
            sleep(settings['backoff_seconds'][attempts - 1])
        records.append({'event_id': event['event_id'], 'occurrence_id': event['occurrence_id'],
                        'destination': destination.get('name', 'external'),
                        'status': 'RETRY_EXHAUSTED' if retry else status,
                        'last_failure': None if status == ACCEPTED else status,
                        'attempts': attempts, 'http_status': http_status, 'receipt': receipt,
                        'detail': sanitize(detail, 200, (credential,)), 'acknowledged': False})
    return records


def render(report):
    lines = ['### Eventos de alerta (contrato G05)', '',
             f"Destino externo: `{json.dumps(report['channel']['external_destination'])}` — canal atual "
             f"`{CHANNEL}` (falha do job e este resumo). Reconhecimento humano: "
             f"{report['acknowledgement']['status']}.", '']
    if report['events']:
        lines += ['| Severidade | Bloqueia | Métrica | Assunto | Evento | Entrega |',
                  '| --- | --- | --- | --- | --- | --- |']
        delivery = {record['event_id']: record['status'] for record in report['delivery']}
        lines += [f"| {event['severity']} | {'sim' if event['blocking'] else 'não'} "
                  f"| `{event['metric']}` | `{event['subject']}` | `{event['event_id'][:12]}` "
                  f"| {delivery.get(event['event_id'], '—')} |" for event in report['events']]
    else:
        lines.append('Nenhum evento roteável.')
    counts = {}
    for item in report['suppressed']:
        counts[item['level']] = counts.get(item['level'], 0) + 1
    if counts:
        lines += ['', 'Suprimidos e visíveis: ' + ', '.join(f'{level}={count}'
                                                          for level, count in sorted(counts.items())) + '.']
    return '\n'.join(lines) + '\n'


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def emit(health_path, pins_path, policy, destination, run, now, test_event=False):
    events, suppressed = build(read_json(health_path), read_json(pins_path), policy, run, now, test_event)
    if destination is not None:
        # No transport has been approved; refuse instead of implying delivery.
        raise ValueError('external destination configured without an approved transport')
    return {'schema_version': SCHEMA_VERSION, 'contract_status': policy['status'],
            'generated_at': now.isoformat(), 'run': run,
            'channel': {'current': CHANNEL, 'external_destination': destination},
            'events': events, 'suppressed': suppressed,
            'delivery': deliver(events, destination, policy['delivery']),
            'acknowledgement': {'required': True, 'status': NOT_PROVEN, 'records': []},
            'counts': {'routed': len(events), 'blocking': sum(event['blocking'] for event in events),
                       'suppressed': len(suppressed)}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('emit', 'lint'))
    parser.add_argument('--health', type=Path, default=Path('reports/operational-health.json'))
    parser.add_argument('--pins', type=Path, default=Path('reports/tool-pins.json'))
    parser.add_argument('--policy', type=Path, default=POLICY)
    parser.add_argument('--health-policy', type=Path, default=HEALTH_POLICY)
    parser.add_argument('--json', dest='json_output', type=Path)
    parser.add_argument('--markdown', help='arquivo de saída (ex.: $GITHUB_STEP_SUMMARY)')
    parser.add_argument('--test-event', action='store_true',
                        help='acrescenta um evento de teste identificado, não bloqueante')
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        destination = external_destination(args.health_policy)
        if args.mode == 'lint':
            require(destination is None, 'external destination requires an approved transport first')
            print('Contrato de alertas conferido; destino externo null.')
            return 0
        report = emit(args.health, args.pins, policy, destination, run_context(),
                      datetime.now(timezone.utc), args.test_event)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'::error::contrato de alertas inválido: {error}', file=sys.stderr)
        return 2
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    markdown = render(report)
    if args.markdown:
        with Path(args.markdown).open('a') as output:
            output.write(markdown)
    else:
        print(markdown, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
