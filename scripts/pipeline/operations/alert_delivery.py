"""Ciclo de vida dos alertas com transporte plugável, separado do health (G05).

O health emite `reports/alert-events.json` (alert_events.py). Este módulo é
o consumidor opcional desses eventos, executado num job próprio quando um
destino for aprovado. Para cada evento registra, em ordem:

- EVENT_CREATED: o evento existe neste run;
- DELIVERY_ATTEMPTED: cada tentativa, com resultado e erro mascarado;
- DELIVERED: o destino aceitou e devolveu uma referência;
- ACKNOWLEDGED: só a partir de uma ação humana lida do destino e verificada
  (pessoa autorizada, não automação, depois da entrega);
- RESOLVED: a condição sumiu de um run posterior e o destino foi atualizado.

Entrega, recibo ou health verde nunca produzem ACKNOWLEDGED. O destino é a
fonte de verdade entre runs: um alerta já aberto lá é atualizado, não
duplicado, e uma criação ambígua (timeout, 5xx) é reconciliada relendo o
destino antes de tentar de novo. O adapter recomendado usa Issues do GitHub;
nada aqui roda enquanto `external_destination` for null.
"""
import argparse
from collections import namedtuple
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from scripts.pipeline.operations.alert_events import (
    HEALTH_POLICY, POLICY, TransportError, TransportTimeout, destination_adapter, external_destination,
    load_policy, sanitize,
)

STATES = ('EVENT_CREATED', 'DELIVERY_ATTEMPTED', 'DELIVERED', 'ACKNOWLEDGED', 'RESOLVED')
GITHUB_ISSUES = 'github-issues'
EVENT_ID = re.compile(r'[0-9a-f]{64}')
# An alert the destination already holds.
Record = namedtuple('Record', 'event_id reference number delivered_at')
# A human action read from the destination; never produced locally.
Ack = namedtuple('Ack', 'actor actor_type at reference')


class HttpError(Exception):
    def __init__(self, status, message=''):
        super().__init__(message)
        self.status = status


def moment(value):
    return datetime.fromisoformat(str(value).replace('Z', '+00:00'))


def verify_ack(ack, record, acknowledgers, automation_actors):
    """(True, '') only for an authorized person acting after the delivery."""
    if ack.actor_type != 'User' or ack.actor in automation_actors:
        return False, 'not a human actor'
    if ack.actor not in acknowledgers:
        return False, 'actor is not an authorized acknowledger'
    if not ack.reference:
        return False, 'no verifiable reference'
    try:
        if moment(ack.at) < moment(record.delivered_at):
            return False, 'acknowledged before delivery'
    except (TypeError, ValueError):
        return False, 'unreadable timestamp'
    return True, ''


def classify(error, secrets):
    """(status, retryable, ambiguous, detail) for one failed attempt.

    Ambiguous means the write may have reached the destination.
    """
    detail = sanitize(str(error), 200, secrets)
    if isinstance(error, TransportTimeout):
        return 'FAILED_TIMEOUT', True, True, detail
    if isinstance(error, TransportError):
        return 'FAILED_TRANSPORT', True, error.sent, detail
    if isinstance(error, HttpError):
        if error.status in (401, 403):
            return 'FAILED_AUTH', False, False, detail
        if error.status in (408, 429):
            return 'FAILED_HTTP', True, False, detail
        if error.status >= 500:
            return 'FAILED_HTTP', True, True, detail
        return 'FAILED_HTTP', False, False, detail
    return 'FAILED_ADAPTER', False, True, detail


class Ledger:
    def __init__(self, clock):
        self.clock = clock
        self.entries = []

    def add(self, event_id, state, **detail):
        if state not in STATES:
            raise ValueError(f'unknown alert state {state}')
        self.entries.append(dict(event_id=event_id, state=state, at=self.clock().isoformat(), **detail))


def deliver_one(event, existing, adapter, settings, ledger, sleep, secrets):
    """Record for the alert at the destination after this run, or None."""
    event_id = event['event_id']
    for attempt in range(1, settings['max_attempts'] + 1):
        try:
            record = adapter.deliver(event, existing)
        except Exception as error:  # adapter boundary: classified and recorded, never swallowed
            status, retryable, ambiguous, detail = classify(error, secrets)
            ledger.add(event_id, 'DELIVERY_ATTEMPTED', attempt=attempt, status=status, detail=detail)
            if existing is not None:
                # The alert is already open there; repeating an update risks
                # duplicates and adds nothing, so stop here.
                return existing
            if ambiguous:
                try:
                    landed = adapter.open_alerts().get(event_id)
                except Exception:  # unreadable destination: no blind re-create
                    return None
                if landed is not None:
                    ledger.add(event_id, 'DELIVERED', reference=landed.reference, reconciled=True)
                    return landed
            if not retryable or attempt == settings['max_attempts']:
                return None
            sleep(settings['backoff_seconds'][attempt - 1])
            continue
        ledger.add(event_id, 'DELIVERY_ATTEMPTED', attempt=attempt, status='ACCEPTED')
        ledger.add(event_id, 'DELIVERED', reference=record.reference, reconciled=False)
        return record
    return None


def run_cycle(events, adapter, settings, *, acknowledgers, automation_actors, clock, sleep=time.sleep,
              secrets=()):
    """Deliver, read acknowledgements and resolve; returns the run's ledger and summary."""
    ledger = Ledger(clock)
    routed = {event['event_id']: event for event in events}
    for event in events:
        ledger.add(event['event_id'], 'EVENT_CREATED', occurrence_id=event['occurrence_id'],
                   severity=event['severity'], test=event['test'])
    try:
        known = adapter.open_alerts()
    except Exception as error:  # without the destination's view, no write is safe
        detail = sanitize(str(error), 200, secrets)
        for event_id in routed:
            ledger.add(event_id, 'DELIVERY_ATTEMPTED', attempt=0, status='FAILED_RECONCILE', detail=detail)
        return report(routed, {}, ledger, [])
    records = dict(known)
    for event_id, event in routed.items():
        record = deliver_one(event, known.get(event_id), adapter, settings, ledger, sleep, secrets)
        if record is not None:
            records[event_id] = record
    rejected = []
    for event_id, record in records.items():
        try:
            acknowledgements = adapter.acknowledgements(record)
        except Exception as error:  # unreadable ACK stays NOT_PROVEN
            rejected.append({'event_id': event_id, 'reason': sanitize(str(error), 200, secrets)})
            continue
        for ack in acknowledgements:
            valid, reason = verify_ack(ack, record, acknowledgers, automation_actors)
            if valid:
                ledger.add(event_id, 'ACKNOWLEDGED', by=ack.actor, acknowledged_at=ack.at,
                           reference=ack.reference)
                break
            rejected.append({'event_id': event_id, 'actor': ack.actor, 'reason': reason})
    for event_id, record in known.items():
        if event_id in routed:
            continue
        try:
            adapter.resolve(record)
        except Exception as error:  # stays open and visible at the destination
            rejected.append({'event_id': event_id, 'reason': 'resolve failed: '
                             + sanitize(str(error), 200, secrets)})
            continue
        ledger.add(event_id, 'RESOLVED', reference=record.reference, by='condition-cleared')
    return report(routed, known, ledger, rejected)


def report(routed, known, ledger, rejected):
    summary = {}
    for event_id in sorted(set(routed) | set(known)):
        entries = [entry for entry in ledger.entries if entry['event_id'] == event_id]
        names = [entry['state'] for entry in entries]
        attempts = [entry['status'] for entry in entries if entry['state'] == 'DELIVERY_ATTEMPTED']
        ack = next((entry for entry in entries if entry['state'] == 'ACKNOWLEDGED'), None)
        if 'DELIVERED' in names:
            delivery = 'DELIVERED'
        elif event_id in known:
            delivery = 'ALREADY_DELIVERED'
        else:
            delivery = attempts[-1] if attempts else 'NOT_ATTEMPTED'
        summary[event_id] = {
            'delivery': delivery,
            'last_attempt': attempts[-1] if attempts else None,
            'acknowledgement': ({'status': 'ACKNOWLEDGED', 'by': ack['by'], 'at': ack['acknowledged_at'],
                                 'reference': ack['reference']} if ack else {'status': 'NOT_PROVEN'}),
            'resolved': 'RESOLVED' in names,
            'resolved_without_ack': 'RESOLVED' in names and ack is None,
        }
    return {'ledger': ledger.entries, 'summary': summary, 'rejected_acknowledgements': rejected}


def not_configured(events, clock):
    ledger = Ledger(clock)
    for event in events:
        ledger.add(event['event_id'], 'EVENT_CREATED', occurrence_id=event['occurrence_id'],
                   severity=event['severity'], test=event['test'])
    return {'ledger': ledger.entries, 'rejected_acknowledgements': [],
            'summary': {event['event_id']: {'delivery': 'NOT_CONFIGURED', 'last_attempt': None,
                                            'acknowledgement': {'status': 'NOT_PROVEN'},
                                            'resolved': False, 'resolved_without_ack': False}
                        for event in events}}


def marked_event_id(body):
    for line in (body or '').splitlines():
        if line.startswith('event_id: '):
            value = line[len('event_id: '):].strip()
            return value if EVENT_ID.fullmatch(value) else None
    return None


class GitHubIssuesAdapter:
    """One open issue per event_id; acknowledgement is a label applied by a person."""

    def __init__(self, client, config):
        self.client = client
        self.config = config

    def label(self, event_id):
        return self.config['event_label_prefix'] + event_id[:16]

    def open_alerts(self):
        found = {}
        for issue in self.client.list_open_issues(self.config['base_label']):
            event_id = marked_event_id(issue.get('body'))
            labels = {label.get('name') for label in issue.get('labels') or []}
            if event_id is None or self.label(event_id) not in labels:
                continue  # not created by this adapter; never touched
            if event_id in found:
                raise ValueError(f'two open issues for event {event_id[:16]}; reconcile by hand')
            found[event_id] = Record(event_id, issue['html_url'], issue['number'], issue['created_at'])
        return found

    def body(self, event):
        run = event['run']
        return '\n'.join([
            f"**{event['severity']}** `{event['metric']}` em `{event['subject']}`", '',
            event['summary'], '',
            f"- Run: {run['url'] or 'local'} (tentativa {run['run_attempt'] or '-'})",
            f"- Detectado em: {event['detected_at']}",
            f"- Bloqueia o health: {'sim' if event['blocking'] else 'não'}", '',
            f"Reconhecer: uma pessoa autorizada aplica o rótulo `{self.config['ack_label']}`.", '',
            f"event_id: {event['event_id']}", f"occurrence_id: {event['occurrence_id']}"])

    def deliver(self, event, existing):
        if existing is not None:
            self.client.comment(existing.number, f"Ainda detectado: `{event['occurrence_id']}` "
                                                 f"({event['detected_at']}).")
            return existing
        prefix = '[TESTE] ' if event['test'] else ''
        issue = self.client.create_issue(
            title=f"{prefix}[{event['severity']}] {event['metric']}: {event['subject']}"[:200],
            body=self.body(event), labels=[self.config['base_label'], self.label(event['event_id'])],
            assignees=list(self.config['assignees']))
        return Record(event['event_id'], issue['html_url'], issue['number'], issue['created_at'])

    def acknowledgements(self, record):
        return [Ack((item.get('actor') or {}).get('login'), (item.get('actor') or {}).get('type'),
                    item.get('created_at'), f"{record.reference}#event-{item.get('id')}")
                for item in self.client.issue_events(record.number)
                if item.get('event') == 'labeled'
                and (item.get('label') or {}).get('name') == self.config['ack_label']]

    def resolve(self, record):
        self.client.comment(record.number, 'Condição não detectada no último run do health.')
        self.client.add_labels(record.number, [self.config['resolved_label']])
        self.client.close(record.number)


class GhCli:
    """`gh api` client for the Issues adapter. Never exercised locally; tests use a fake."""

    def __init__(self, repository, timeout):
        self.repository = repository
        self.timeout = timeout

    def call(self, method, path, payload=None):
        args = ['gh', 'api', '--method', method, f'repos/{self.repository}/{path}']
        if payload is not None:
            args += ['--input', '-']
        try:
            result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                                    capture_output=True, text=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise TransportTimeout('gh api timed out') from error
        except OSError as error:
            raise TransportError(str(error), sent=False) from error
        if result.returncode:
            found = re.search(r'\(HTTP (\d{3})\)', result.stderr)
            if not found:
                raise TransportError(result.stderr.strip()[:200], sent=True)
            raise HttpError(int(found[1]), result.stderr.strip()[:200])
        return json.loads(result.stdout) if result.stdout.strip() else None

    def list_open_issues(self, label):
        return self.call('GET', f'issues?state=open&labels={label}&per_page=100') or []

    def create_issue(self, title, body, labels, assignees):
        return self.call('POST', 'issues', {'title': title, 'body': body, 'labels': labels,
                                            'assignees': assignees})

    def comment(self, number, body):
        self.call('POST', f'issues/{number}/comments', {'body': body})

    def add_labels(self, number, labels):
        self.call('POST', f'issues/{number}/labels', {'labels': labels})

    def close(self, number):
        self.call('PATCH', f'issues/{number}', {'state': 'closed', 'state_reason': 'completed'})

    def issue_events(self, number):
        return self.call('GET', f'issues/{number}/events?per_page=100') or []


def utc_now():
    return datetime.now(timezone.utc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, default=Path('reports/alert-events.json'))
    parser.add_argument('--policy', type=Path, default=POLICY)
    parser.add_argument('--health-policy', type=Path, default=HEALTH_POLICY)
    parser.add_argument('--json', dest='json_output', type=Path)
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
        destination = external_destination(args.health_policy)
        events = json.loads(args.events.read_text())['events']
        adapter = destination_adapter(policy, destination)
        if adapter is None:
            result = not_configured(events, utc_now)
        else:
            if destination != GITHUB_ISSUES:
                raise ValueError(f'no client implemented for destination {destination!r}')
            result = run_cycle(events, GitHubIssuesAdapter(GhCli(adapter['repository'],
                                                                 policy['delivery']['timeout_seconds']),
                                                           adapter),
                               policy['delivery'], acknowledgers=set(adapter['acknowledgers']),
                               automation_actors=set(adapter['automation_actors']), clock=utc_now)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'::error::entrega de alertas não executada: {error}', file=sys.stderr)
        return 2
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    # A create reconciled as landed is delivered; an update that failed on an
    # alert already open still has to be visible.
    failed = [event['event_id'] for event in events
              if result['summary'][event['event_id']]['delivery'] not in
              ('DELIVERED', 'ALREADY_DELIVERED', 'NOT_CONFIGURED')
              or (result['summary'][event['event_id']]['delivery'] == 'ALREADY_DELIVERED'
                  and result['summary'][event['event_id']]['last_attempt'] not in (None, 'ACCEPTED'))]
    for event_id in failed:
        print(f'::error::alerta {event_id[:16]}: {result["summary"][event_id]["last_attempt"]}',
              file=sys.stderr)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
