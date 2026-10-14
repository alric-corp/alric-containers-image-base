"""G05: alert event contract, minimization and delivery semantics without a real destination."""
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import itertools
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from scripts.pipeline.operations import alert_events as alerts
from tests.helpers.subprocess_env import bash_command

NOW = datetime(2026, 10, 13, 12, 56, tzinfo=timezone.utc)
RUN = {'repository': 'alric-corp/alric-containers-image-base', 'workflow': 'Ops - Pipeline health',
       'run_id': '38400943111', 'run_attempt': '1', 'sha': 'a' * 40,
       'url': 'https://github.com/alric-corp/alric-containers-image-base/actions/runs/38400943111'}
TOKEN = 'ghp_' + 'x' * 36
EVENT_KEYS = {'schema_version', 'event_id', 'occurrence_id', 'state', 'test', 'severity',
              'severity_source', 'blocking', 'source', 'level', 'metric', 'subject', 'summary',
              'detected_at', 'routing_key', 'run', 'repetitions', 'acknowledgement'}


def health(*entries):
    """Shape of reports/operational-health.json, with only what the contract reads."""
    return {'generated_at': '2026-10-13T12:56:44+00:00',
            'alerts': [{'level': level, 'metric': metric, 'subject': subject, 'message': message}
                       for level, metric, subject, message in entries]}


def pins(*entries):
    return {'pins': [dict(entry) for entry in entries], 'update_prs': []}


# The three blocking alerts of hosted health run 38400943111 (13/10/2026), plus
# the suppressed and data-gap levels the health also produces.
CURRENT = health(('alert', 'stable_age_hours', 'go1-26', 'sem dado na janela analisada'),
                 ('alert', 'stable_age_hours', 'go1-26-dev', 'sem dado na janela analisada'),
                 ('alert', 'execution_scope_review', 'execution_scope',
                  'escopo de execução vencido em 2026-09-30, dono @alric-corp/github_xj7_maintainer'),
                 ('out_of_scope', 'stable_age_hours', 'java21', 'fora do escopo de execução atual'),
                 ('known', 'publication_age_hours', 'dotnet8', 'exceção conhecida'),
                 ('unknown', 'promotion_evidence', '38363913740', 'artifact de promoção expirado'))
PINS_OK = pins({'kind': 'action', 'name': 'actions/checkout', 'current': 'a' * 40,
                'file': '.github/workflows/ci.yml', 'available': True})


class FakeTransport:
    """Simulated destination: replies in order and records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, body, headers, timeout):
        self.requests.append((body, dict(headers), timeout))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


class EventContractTests(unittest.TestCase):
    def setUp(self):
        self.policy = alerts.load_policy()

    def build(self, report=CURRENT, pin_report=PINS_OK, run=RUN, test_event=False):
        return alerts.build(report, pin_report, self.policy, run, NOW, test_event)

    def test_current_alerts_are_routed_and_documented_levels_stay_visible(self):
        events, suppressed = self.build()
        routed = [(event['level'], event['metric'], event['subject'], event['blocking'])
                  for event in events]
        self.assertEqual(routed, [('alert', 'stable_age_hours', 'go1-26', True),
                                  ('alert', 'stable_age_hours', 'go1-26-dev', True),
                                  ('alert', 'execution_scope_review', 'execution_scope', True),
                                  ('unknown', 'promotion_evidence', '38363913740', False)])
        self.assertEqual([(item['level'], item['subject']) for item in suppressed],
                         [('out_of_scope', 'java21'), ('known', 'dotnet8')])
        for event in events:
            self.assertEqual(set(event), EVENT_KEYS)
            self.assertEqual(event['acknowledgement'], {'required': True, 'status': 'NOT_PROVEN'})
            self.assertEqual(event['state'], 'firing')

    def test_identity_is_stable_across_runs_and_unique_per_condition(self):
        first, _ = self.build()
        later = health(('alert', 'stable_age_hours', 'go1-26', 'stable_age_hours em 80h (limite 48h)'))
        second, _ = self.build(later, run=dict(RUN, run_id='38500000000', run_attempt='2'))
        self.assertEqual(first[0]['event_id'], second[0]['event_id'])
        self.assertNotEqual(first[0]['occurrence_id'], second[0]['occurrence_id'])
        self.assertNotEqual(first[0]['event_id'], first[1]['event_id'])
        self.assertEqual(len(first[0]['event_id']), 64)

    def test_a_repeated_condition_in_one_run_is_one_event(self):
        report = health(('alert', 'schedule_gap_hours', '17 * * * *', 'a'),
                        ('alert', 'schedule_gap_hours', '17 * * * *', 'b'))
        events, _ = self.build(report)
        self.assertEqual([(event['subject'], event['repetitions']) for event in events],
                         [('17 * * * *', 2)])

    def test_missing_or_invalid_reports_become_monitor_failures(self):
        for report, pin_report in ((None, PINS_OK), ({'alerts': 'broken'}, PINS_OK),
                                   (CURRENT, None), (CURRENT, {'pins': ['x']})):
            events, _ = self.build(report, pin_report)
            metrics = {event['metric']: event for event in events}
            missing = 'health_report_missing' if pin_report is PINS_OK else 'pins_report_missing'
            with self.subTest(missing=missing, report=report if report is not CURRENT else 'current'):
                self.assertTrue(metrics[missing]['blocking'])
                self.assertIn(metrics[missing]['severity'], ('critical', 'high'))

    def test_pin_failures_keep_their_distinct_meaning(self):
        report = pins({'kind': 'action', 'name': 'owner/action', 'current': 'b' * 40,
                       'file': 'a.yml', 'available': False},
                      {'kind': 'action', 'name': 'owner/action', 'current': 'b' * 40,
                       'file': 'b.yml', 'available': False},
                      {'kind': 'image', 'name': 'registry/tool', 'current': 'sha256:' + 'c' * 64,
                       'file': 'Makefile', 'available': None},
                      {'kind': 'local-key', 'name': 'wolfi-signing-key', 'current': 'sha256:' + 'd' * 64,
                       'file': 'melange/keys/wolfi-signing-key.json', 'available': False,
                       'remote_status': 'divergent'})
        events, _ = self.build(health(), report)
        found = {event['metric']: event for event in events}
        self.assertEqual((found['pin_unavailable']['blocking'], found['pin_unavailable']['repetitions']),
                         (True, 2))
        self.assertEqual((found['pin_unverified']['blocking'], found['pin_unverified']['severity']),
                         (False, 'low'))
        self.assertEqual(found['wolfi_key_status']['severity'], 'critical')
        self.assertIn('divergent', found['wolfi_key_status']['summary'])

    def test_unclassified_metric_or_level_still_routes_visibly(self):
        events, _ = self.build(health(('hold', 'release_hold', 'go1-26', 'pausa operacional')))
        self.assertEqual((events[0]['severity'], events[0]['severity_source'], events[0]['blocking']),
                         ('high', 'default', False))

    def test_payload_leaves_only_minimized_and_redacted_text(self):
        message = ('falha em arn:aws:iam::712107929769:role/x conta 248908662184 token ' + TOKEN
                   + ' github_pat_' + 'y' * 30 + ' chave AKIA' + 'Z' * 16
                   + ' url https://user:secret@example.invalid/x Bearer abc.def ops@example.com\n'
                   + 'linha ' * 80)
        events, _ = self.build(health(('alert', 'schedule_gap_hours', '23 3 * * *', message)))
        summary = events[0]['summary']
        for leaked in ('712107929769', '248908662184', TOKEN, 'github_pat_', 'AKIA', 'secret@',
                       'abc.def', 'ops@example.com', '\n'):
            self.assertNotIn(leaked, summary)
        self.assertEqual(len(summary), self.policy['payload']['max_summary_chars'])
        self.assertTrue(summary.endswith('…'))

    def test_test_event_is_identified_and_never_blocking(self):
        events, _ = self.build(health(), test_event=True)
        self.assertEqual([(event['metric'], event['test'], event['blocking'], event['severity'])
                          for event in events], [('alert_pipeline_test', True, False, 'low')])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.policy = alerts.load_policy()
        self.events, _ = alerts.build(CURRENT, PINS_OK, self.policy, RUN, NOW)
        self.event = self.events[:1]
        self.sleeps = []

    def deliver(self, transport, idempotent=False, events=None):
        destination = {'name': 'simulated', 'receipt_field': 'id', 'idempotency_key_supported': idempotent}
        return alerts.deliver(events or self.event, destination, self.policy['delivery'], transport,
                              credential=TOKEN, sleep=self.sleeps.append)

    def test_no_destination_records_not_configured_without_any_attempt(self):
        transport = FakeTransport(alerts.Response(200, b'{"id": "1"}'))
        records = alerts.deliver(self.events, None, self.policy['delivery'], transport)
        self.assertEqual({record['status'] for record in records}, {'NOT_CONFIGURED'})
        self.assertEqual(transport.requests, [])
        self.assertFalse(any(record['acknowledged'] for record in records))

    def test_accepted_delivery_is_not_an_acknowledgement(self):
        transport = FakeTransport(alerts.Response(202, b'{"id": "evt-1"}'))
        [record] = self.deliver(transport)
        self.assertEqual((record['status'], record['receipt'], record['acknowledged']),
                         ('ACCEPTED', 'evt-1', False))
        self.assertEqual(self.event[0]['acknowledgement']['status'], 'NOT_PROVEN')
        body, headers, timeout = transport.requests[0]
        self.assertEqual(json.loads(body)['event_id'], self.event[0]['event_id'])
        self.assertEqual(headers['Idempotency-Key'], self.event[0]['occurrence_id'])
        self.assertEqual(timeout, self.policy['delivery']['timeout_seconds'])

    def test_ambiguous_auth_and_client_errors_are_never_retried(self):
        for reply, status in ((alerts.Response(200, b'{}'), 'AMBIGUOUS'),
                              (alerts.Response(200, b'not json'), 'AMBIGUOUS'),
                              (alerts.Response(401, b''), 'FAILED_AUTH'),
                              (alerts.Response(403, b''), 'FAILED_AUTH'),
                              (alerts.Response(404, b''), 'FAILED_HTTP')):
            transport = FakeTransport(reply)
            with self.subTest(status=status, http=reply.status):
                [record] = self.deliver(transport, idempotent=True)
                self.assertEqual((record['status'], record['attempts']), (status, 1))

    def test_retries_are_bounded_and_only_when_safe(self):
        cases = (
            # (replies, idempotent, expected status, attempts)
            ((alerts.Response(429, b''),), False, 'RETRY_EXHAUSTED', 3),
            ((alerts.Response(429, b''), alerts.Response(200, b'{"id": 7}')), False, 'ACCEPTED', 2),
            ((alerts.Response(500, b''),), False, 'FAILED_HTTP', 1),
            ((alerts.Response(503, b''),), True, 'RETRY_EXHAUSTED', 3),
            ((alerts.TransportTimeout('read timeout'),), False, 'FAILED_TIMEOUT', 1),
            ((alerts.TransportTimeout('read timeout'),), True, 'RETRY_EXHAUSTED', 3),
            ((alerts.TransportError('connection refused', sent=False),), False, 'RETRY_EXHAUSTED', 3),
            ((alerts.TransportError('reset after send', sent=True),), False, 'FAILED_TRANSPORT', 1),
        )
        for replies, idempotent, status, attempts in cases:
            self.sleeps.clear()
            with self.subTest(replies=replies, idempotent=idempotent):
                [record] = self.deliver(FakeTransport(*replies), idempotent)
                self.assertEqual((record['status'], record['attempts']), (status, attempts))
                self.assertEqual(self.sleeps, self.policy['delivery']['backoff_seconds'][:attempts - 1])
                if status == 'RETRY_EXHAUSTED':
                    self.assertIsNotNone(record['last_failure'])

    def test_delivery_failure_never_leaks_the_credential_or_loses_the_event(self):
        transport = FakeTransport(alerts.TransportError(f'POST failed with Authorization: Bearer {TOKEN}',
                                                        sent=True))
        records = self.deliver(transport, events=self.events)
        self.assertEqual(len(records), len(self.events))
        self.assertNotIn(TOKEN, json.dumps(records))
        self.assertNotIn(TOKEN, json.dumps(self.events))
        for body, headers, _ in transport.requests:
            self.assertNotIn(TOKEN.encode(), body)
            self.assertEqual(headers['Authorization'], 'Bearer ' + TOKEN)

    def test_a_destination_without_an_approved_transport_is_refused(self):
        with self.assertRaises(ValueError):
            alerts.deliver(self.event, {'name': 'x'}, self.policy['delivery'])


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.health = self.root / 'operational-health.json'
        self.pins = self.root / 'tool-pins.json'
        self.health.write_text(json.dumps(CURRENT))
        self.pins.write_text(json.dumps(PINS_OK))

    def run_cli(self, *extra):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = alerts.main(['emit', '--health', str(self.health), '--pins', str(self.pins),
                                '--json', str(self.root / 'alert-events.json'),
                                '--markdown', str(self.root / 'summary.md'), *extra])
        return code, errors.getvalue()

    def test_emit_never_changes_the_health_result_or_its_inputs(self):
        digests = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.health, self.pins)}
        code, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (self.health, self.pins)}, digests)
        report = json.loads((self.root / 'alert-events.json').read_text())
        self.assertEqual(report['counts'], {'routed': 4, 'blocking': 3, 'suppressed': 2})
        self.assertEqual(report['channel'], {'current': 'github-actions-run', 'external_destination': None})
        self.assertEqual({record['status'] for record in report['delivery']}, {'NOT_CONFIGURED'})
        self.assertEqual(report['acknowledgement'], {'required': True, 'status': 'NOT_PROVEN', 'records': []})
        summary = (self.root / 'summary.md').read_text()
        self.assertIn('Destino externo: `null`', summary)
        self.assertIn('Reconhecimento humano: NOT_PROVEN', summary)

    def test_emit_with_missing_reports_still_records_the_monitor_failure(self):
        self.health.unlink()
        code, _ = self.run_cli()
        report = json.loads((self.root / 'alert-events.json').read_text())
        self.assertEqual(code, 0)
        self.assertIn('health_report_missing', [event['metric'] for event in report['events']])

    def test_a_configured_destination_fails_closed_until_a_transport_is_approved(self):
        policy = json.loads(alerts.HEALTH_POLICY.read_text())
        policy['channel']['external_destination'] = 'https://example.invalid/hook'
        health_policy = self.root / 'health.json'
        health_policy.write_text(json.dumps(policy))
        code, errors = self.run_cli('--health-policy', str(health_policy))
        self.assertEqual(code, 2)
        self.assertIn('approved adapter', errors)
        self.assertFalse((self.root / 'alert-events.json').exists())

    def test_an_enabled_adapter_defers_delivery_to_its_own_job(self):
        policy = json.loads(alerts.POLICY.read_text())
        policy['adapters']['github-issues'].update(enabled=True, repository='alric-corp/factory-ops',
                                                   assignees=['owner'], acknowledgers=['owner'])
        (self.root / 'alerting.json').write_text(json.dumps(policy))
        health_policy = json.loads(alerts.HEALTH_POLICY.read_text())
        health_policy['channel']['external_destination'] = 'github-issues'
        (self.root / 'health.json').write_text(json.dumps(health_policy))
        code, _ = self.run_cli('--policy', str(self.root / 'alerting.json'),
                               '--health-policy', str(self.root / 'health.json'))
        report = json.loads((self.root / 'alert-events.json').read_text())
        self.assertEqual(code, 0)
        self.assertEqual({record['status'] for record in report['delivery']}, {'DEFERRED_TO_DELIVERY_JOB'})
        self.assertEqual(report['acknowledgement']['status'], 'NOT_PROVEN')

    def test_repository_policy_preserves_the_owner_decision(self):
        self.assertIsNone(alerts.external_destination())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(alerts.main(['lint']), 0)
        policy = json.loads(alerts.POLICY.read_text())
        self.assertFalse(policy['adapters']['github-issues']['enabled'])
        for mutate in (lambda p: p['acknowledgement'].update(record='http-200'),
                       lambda p: p['adapters']['github-issues'].update(enabled=True),
                       lambda p: p['adapters']['github-issues'].update(ack_label='factory-alert'),
                       lambda p: p['adapters'].update(teams={'enabled': False})):
            changed = json.loads(alerts.POLICY.read_text())
            mutate(changed)
            path = self.root / 'alerting.json'
            path.write_text(json.dumps(changed))
            with self.subTest(mutate=mutate), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(alerts.main(['lint', '--policy', str(path)]), 2)


class WorkflowWiringTests(unittest.TestCase):
    """The health job emits events but keeps deciding its result alone."""

    @classmethod
    def setUpClass(cls):
        workflow = yaml.safe_load((alerts.ROOT / '.github/workflows/pipeline-health.yml').read_text())
        cls.steps = workflow['jobs']['health']['steps']
        cls.names = [step.get('name') for step in cls.steps]

    def step(self, name):
        return self.steps[self.names.index(name)]

    def test_events_are_built_after_detection_and_preserved_with_the_evidence(self):
        emit = self.step('Build alert events without external delivery')
        order = [self.names.index(name) for name in (
            'Measure operational health', 'Build alert events without external delivery',
            'Preserve health evidence', 'Fail on breached thresholds or unavailable pins')]
        self.assertEqual(order, sorted(order))
        self.assertEqual((emit['if'], emit['continue-on-error']), ('${{ !cancelled() }}', True))
        self.assertNotIn('env', emit)
        self.assertIn('--json reports/alert-events.json', emit['run'])
        self.assertEqual(self.step('Preserve health evidence')['with']['path'], 'reports/')

    def test_the_job_result_depends_only_on_pins_and_metrics(self):
        script = self.step('Fail on breached thresholds or unavailable pins')['run']
        outcomes = ('success', 'failure', 'skipped')
        for pins_outcome, metrics, emitted in itertools.product(outcomes, outcomes, outcomes):
            result = subprocess.run(bash_command('-c', script), capture_output=True, text=True,
                                    env={'PINS': pins_outcome, 'METRICS': metrics, 'ALERTS': emitted,
                                         'PATH': '/usr/bin:/bin'}, timeout=10)
            with self.subTest(pins=pins_outcome, metrics=metrics, alerts=emitted):
                self.assertEqual(result.returncode == 0,
                                 pins_outcome == 'success' and metrics == 'success')


if __name__ == '__main__':
    unittest.main()
