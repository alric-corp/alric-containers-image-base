"""G05: alert lifecycle with a pluggable transport; simulated GitHub Issues, no network."""
import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.operations import alert_delivery as delivery
from scripts.pipeline.operations import alert_events as alerts
from tests.unit.pipeline.operations.test_alert_events import CURRENT, PINS_OK, RUN, TOKEN, health

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)
CONFIG = dict(json.loads(alerts.POLICY.read_text())['adapters']['github-issues'],
              enabled=True, repository='alric-corp/factory-ops', assignees=['owner'], acknowledgers=['owner'])
HUMAN = {'login': 'owner', 'type': 'User'}


class FakeIssues:
    """GitHub Issues semantics the adapter relies on; failures are injected per call."""

    def __init__(self):
        self.issues, self.failures, self.calls = {}, {}, []

    def fail(self, method, *errors):
        self.failures.setdefault(method, []).extend(errors)

    def check(self, method, landed=None):
        self.calls.append(method)
        queue = self.failures.get(method) or []
        if queue:
            error = queue.pop(0)
            if isinstance(error, tuple):  # (exception, write-happened-first)
                if error[1] and landed:
                    landed()
                raise error[0]
            raise error

    def list_open_issues(self, label):
        self.check('list')
        return [dict(issue) for issue in self.issues.values()
                if issue['state'] == 'open' and label in [item['name'] for item in issue['labels']]]

    def _create(self, title, body, labels, assignees):
        number = len(self.issues) + 1
        self.issues[number] = dict(number=number, title=title, body=body, state='open',
                                   labels=[{'name': name} for name in labels], assignees=assignees,
                                   html_url=f'https://github.com/x/y/issues/{number}',
                                   created_at=NOW.isoformat(), comments=[], events=[])
        return self.issues[number]

    def create_issue(self, title, body, labels, assignees):
        holder = {}
        self.check('create', landed=lambda: holder.update(issue=self._create(title, body, labels, assignees)))
        return self._create(title, body, labels, assignees)

    def comment(self, number, body):
        self.check('comment')
        self.issues[number]['comments'].append(body)

    def add_labels(self, number, labels):
        self.check('label')
        self.issues[number]['labels'] += [{'name': name} for name in labels]

    def close(self, number):
        self.check('close')
        self.issues[number]['state'] = 'closed'

    def issue_events(self, number):
        self.check('events')
        return list(self.issues[number]['events'])

    def label_by(self, number, actor, name, at):
        self.issues[number]['events'].append({'id': len(self.issues[number]['events']) + 1, 'event': 'labeled',
                                              'actor': actor, 'label': {'name': name},
                                              'created_at': at.isoformat()})


def events(report=CURRENT, test_event=False):
    routed, _ = alerts.build(report, PINS_OK, alerts.load_policy(), RUN, NOW, test_event)
    return routed


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeIssues()
        self.adapter = delivery.GitHubIssuesAdapter(self.client, CONFIG)
        self.sleeps = []

    def cycle(self, routed):
        return delivery.run_cycle(routed, self.adapter, alerts.load_policy()['delivery'],
                                  acknowledgers={'owner'}, automation_actors={'github-actions[bot]'},
                                  clock=lambda: NOW, sleep=self.sleeps.append, secrets=(TOKEN,))

    def states(self, result, event_id):
        return [entry['state'] for entry in result['ledger'] if entry['event_id'] == event_id]

    def test_delivery_is_recorded_but_never_counts_as_acknowledgement(self):
        routed = events()
        result = self.cycle(routed)
        for event in routed:
            self.assertEqual(self.states(result, event['event_id']),
                             ['EVENT_CREATED', 'DELIVERY_ATTEMPTED', 'DELIVERED'])
            self.assertEqual(result['summary'][event['event_id']]['acknowledgement'], {'status': 'NOT_PROVEN'})
        self.assertEqual(len(self.client.issues), len(routed))
        healthy = self.cycle([])  # a green health resolves alerts; it never acknowledges them
        self.assertNotIn('ACKNOWLEDGED', [entry['state'] for entry in healthy['ledger']])

    def test_only_an_authorized_person_after_delivery_acknowledges(self):
        [event] = events(health(('alert', 'stable_age_hours', 'go1-26', 'sem dado')))
        self.cycle([event])
        label = CONFIG['ack_label']
        self.client.label_by(1, {'login': 'github-actions[bot]', 'type': 'Bot'}, label, NOW + timedelta(minutes=1))
        self.client.label_by(1, {'login': 'someone', 'type': 'User'}, label, NOW + timedelta(minutes=2))
        self.client.label_by(1, HUMAN, label, NOW - timedelta(minutes=5))
        self.client.label_by(1, HUMAN, 'unrelated', NOW + timedelta(minutes=3))
        result = self.cycle([event])
        self.assertNotIn('ACKNOWLEDGED', self.states(result, event['event_id']))
        self.assertEqual(sorted(item['reason'] for item in result['rejected_acknowledgements']),
                         ['acknowledged before delivery', 'actor is not an authorized acknowledger',
                          'not a human actor'])
        self.client.label_by(1, HUMAN, label, NOW + timedelta(minutes=10))
        result = self.cycle([event])
        ack = result['summary'][event['event_id']]['acknowledgement']
        self.assertEqual((ack['status'], ack['by']), ('ACKNOWLEDGED', 'owner'))
        self.assertTrue(ack['reference'].startswith('https://github.com/x/y/issues/1#event-'))

    def test_acknowledgement_needs_a_reference_and_a_readable_time(self):
        record = delivery.Record('e', 'https://github.com/x/y/issues/1', 1, NOW.isoformat())
        later, reference = (NOW + timedelta(minutes=1)).isoformat(), 'https://github.com/x/y/issues/1#event-1'
        cases = {'no verifiable reference': delivery.Ack('owner', 'User', later, ''),
                 'unreadable timestamp': delivery.Ack('owner', 'User', 'yesterday', reference)}
        for reason, ack in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(delivery.verify_ack(ack, record, {'owner'}, set()), (False, reason))
        self.assertEqual(delivery.verify_ack(delivery.Ack('owner', 'User', later, reference), record, {'owner'}, set()),
                         (True, ''))

    def test_a_repeated_condition_updates_the_open_alert_instead_of_duplicating(self):
        routed = events()
        self.cycle(routed)
        result = self.cycle(routed)
        self.assertEqual(len(self.client.issues), len(routed))
        self.assertTrue(all(len(issue['comments']) == 1 for issue in self.client.issues.values()))
        self.assertTrue(all(item['delivery'] == 'DELIVERED' for item in result['summary'].values()))

    def test_ambiguous_create_is_reconciled_from_the_destination(self):
        [event] = events(health(('alert', 'schedule_gap_hours', '23 3 * * *', 'x')))
        self.client.fail('create', (alerts.TransportTimeout('read timeout'), True))
        result = self.cycle([event])
        self.assertEqual(len(self.client.issues), 1)
        self.assertEqual(result['summary'][event['event_id']]['delivery'], 'DELIVERED')
        reconciled = [entry for entry in result['ledger'] if entry['state'] == 'DELIVERED']
        self.assertTrue(reconciled[0]['reconciled'])

    def test_retries_are_bounded_and_only_when_safe(self):
        [event] = events(health(('alert', 'schedule_gap_hours', '23 3 * * *', 'x')))
        cases = ((delivery.HttpError(503), True, 'DELIVERED', [2]),
                 (delivery.HttpError(429), True, 'DELIVERED', [2]),
                 (delivery.HttpError(401), False, 'FAILED_AUTH', []),
                 (delivery.HttpError(422), False, 'FAILED_HTTP', []),
                 (alerts.TransportError('refused', sent=False), True, 'DELIVERED', [2]))
        for error, retried, outcome, sleeps in cases:
            self.setUp()
            self.client.fail('create', error)
            with self.subTest(error=repr(error)):
                result = self.cycle([event])
                self.assertEqual(result['summary'][event['event_id']]['delivery'], outcome)
                self.assertEqual(self.sleeps, sleeps)
                self.assertEqual(self.client.calls.count('create'), 2 if retried else 1)
        self.setUp()
        self.client.fail('create', *[delivery.HttpError(503)] * 3)
        result = self.cycle([event])
        self.assertEqual(result['summary'][event['event_id']]['delivery'], 'FAILED_HTTP')
        self.assertEqual((self.client.calls.count('create'), self.sleeps), (3, [2, 8]))
        self.assertEqual(self.client.issues, {})

    def test_unreadable_destination_never_creates_blindly(self):
        routed = events()
        self.client.fail('list', delivery.HttpError(502))
        result = self.cycle(routed)
        self.assertNotIn('create', self.client.calls)
        self.assertEqual({item['delivery'] for item in result['summary'].values()}, {'FAILED_RECONCILE'})

    def test_failed_update_of_an_open_alert_stays_visible(self):
        [event] = events(health(('alert', 'stable_age_hours', 'go1-26', 'x')))
        self.cycle([event])
        self.client.fail('comment', delivery.HttpError(403, 'Bearer ' + TOKEN))
        result = self.cycle([event])
        summary = result['summary'][event['event_id']]
        self.assertEqual((summary['delivery'], summary['last_attempt']), ('ALREADY_DELIVERED', 'FAILED_AUTH'))
        self.assertEqual(self.client.calls.count('comment'), 1)
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_failed_update_of_an_open_alert_is_never_retried_or_reconciled(self):
        # Only creation is retried or reconciled; repeating an update could duplicate it.
        [event] = events(health(('alert', 'stable_age_hours', 'go1-26', 'x')))
        for error in (delivery.HttpError(429), delivery.HttpError(503), alerts.TransportError('refused', sent=False)):
            self.setUp()
            self.cycle([event])
            self.client.fail('comment', error)
            with self.subTest(error=repr(error)):
                result = self.cycle([event])
                self.assertEqual(result['summary'][event['event_id']]['delivery'], 'ALREADY_DELIVERED')
                self.assertEqual((self.client.calls.count('comment'), self.sleeps), (1, []))
                self.assertNotIn('DELIVERED', self.states(result, event['event_id']))

    def test_cleared_condition_resolves_and_reports_missing_acknowledgement(self):
        [event] = events(health(('alert', 'stable_age_hours', 'go1-26', 'x')))
        self.cycle([event])
        result = self.cycle([])
        self.assertEqual(self.states(result, event['event_id']), ['RESOLVED'])
        self.assertTrue(result['summary'][event['event_id']]['resolved_without_ack'])
        issue = self.client.issues[1]
        self.assertEqual(issue['state'], 'closed')
        self.assertIn(CONFIG['resolved_label'], [label['name'] for label in issue['labels']])
        self.cycle([event])  # recurrence opens a new alert, the closed one stays history
        self.assertEqual(len(self.client.issues), 2)

    def test_issues_not_created_by_the_adapter_are_never_touched(self):
        self.client._create('manual', 'no marker here', [CONFIG['base_label']], [])
        [event] = events(health(('alert', 'stable_age_hours', 'go1-26', 'x')))
        self.cycle([event])
        self.cycle([])
        self.assertEqual(self.client.issues[1]['state'], 'open')
        self.assertEqual(self.client.issues[1]['comments'], [])

    def test_issue_carries_only_the_minimized_event(self):
        [event] = events(health(('alert', 'schedule_gap_hours', '23 3 * * *',
                                 f'token {TOKEN} conta 712107929769')))
        self.cycle([event])
        body = self.client.issues[1]['body']
        self.assertNotIn(TOKEN, body)
        self.assertNotIn('712107929769', body)
        self.assertIn(f"event_id: {event['event_id']}", body)
        [test_event] = events(health(), test_event=True)
        self.cycle([test_event])
        self.assertTrue(self.client.issues[2]['title'].startswith('[TESTE] '))


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.events = self.root / 'alert-events.json'
        self.events.write_text(json.dumps({'events': events()}))

    def main(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            code = delivery.main(['--events', str(self.events), '--json', str(self.root / 'out.json'), *argv])
        return code, errors.getvalue()

    def policies(self, enabled, destination='github-issues', **adapter):
        policy = json.loads(alerts.POLICY.read_text())
        policy['adapters']['github-issues'].update(enabled=enabled, **adapter)
        health_policy = json.loads(alerts.HEALTH_POLICY.read_text())
        health_policy['channel']['external_destination'] = destination
        (self.root / 'alerting.json').write_text(json.dumps(policy))
        (self.root / 'health.json').write_text(json.dumps(health_policy))
        return ['--policy', str(self.root / 'alerting.json'), '--health-policy', str(self.root / 'health.json')]

    def test_repository_policy_keeps_delivery_off(self):
        with patch.object(delivery, 'GhCli', side_effect=AssertionError('no client without destination')):
            code, _ = self.main()
        self.assertEqual(code, 0)
        summary = json.loads((self.root / 'out.json').read_text())['summary']
        self.assertEqual({item['delivery'] for item in summary.values()}, {'NOT_CONFIGURED'})
        self.assertFalse(json.loads(alerts.POLICY.read_text())['adapters']['github-issues']['enabled'])

    def test_destination_without_an_enabled_adapter_or_owner_inputs_is_refused(self):
        for options in (self.policies(False), self.policies(True), self.policies(True, destination='teams',
                                                                                  repository='a/b',
                                                                                  assignees=['x'],
                                                                                  acknowledgers=['x'])):
            with patch.object(delivery, 'GhCli', side_effect=AssertionError('must not build a client')):
                with self.subTest(options=options):
                    self.assertEqual(self.main(*options)[0], 2)

    def test_enabled_adapter_runs_the_cycle_and_fails_visibly_on_delivery_errors(self):
        client = FakeIssues()
        options = self.policies(True, repository='alric-corp/factory-ops', assignees=['owner'],
                                acknowledgers=['owner'])
        with patch.object(delivery, 'GhCli', return_value=client):
            self.assertEqual(self.main(*options)[0], 0)
        self.assertEqual(len(client.issues), len(events()))
        client.fail('comment', delivery.HttpError(401))
        with patch.object(delivery, 'GhCli', return_value=client):
            code, errors = self.main(*options)
        self.assertEqual(code, 1)
        self.assertIn('FAILED_AUTH', errors)


if __name__ == '__main__':
    unittest.main()
