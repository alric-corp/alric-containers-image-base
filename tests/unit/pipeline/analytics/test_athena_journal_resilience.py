"""Abrupt runner loss around the Athena journal (audit G18), against service-shaped fakes only.

RunnerLost derives from BaseException: as with a killed runner, nothing after the
crash point runs, not even the executor's `except Exception` journal flush. The
journal file left on disk is the only state a restarted executor sees. These
tests prove local behavior; they are not a hosted runner-loss proof and execute
no Athena, Glue, S3 or GitHub operation. Round identifiers are TEST values.
"""
import copy
import io
import itertools
import json
from contextlib import redirect_stdout
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics import athena_restore as r, athena_run as a, s3_run
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.spdx import AnalyticsError, canonical, sha256
from tests.unit.pipeline.analytics import test_athena_restore as restore_support, test_athena_run as support
from tests.unit.pipeline.analytics.s3_support import ServiceError

AUTH = 'TEST_ONLY owner ref'


class RunnerLost(BaseException):
    """The runner disappears: no handler, journal flush or artifact upload runs after this point."""


def entry(journal, statement):
    return (journal or {}).get('executions', {}).get(statement)


class JournalResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.AthenaRunTests.setUpClass.__func__(cls)  # Same fakes/profile as the executor tests.

    def setUp(self):
        support.AthenaRunTests.setUp(self)
        self.plan = json.loads(self.raw)
        self.ids = [s['id'] for s in self.plan['statements']]
        self.statement = {s['id']: s for s in self.plan['statements']}

    def execute(self, journal=None, **kwargs):
        return a.execute_plan(self.raw, self.athena, journal or self.journal, authorized_sha256=sha256(self.raw),
                              authorization_reference=AUTH, **kwargs)

    def run_round(self, reports, output):
        return a.run(self.s3, self.sts, self.athena, self.glue, self.expected, self.settings, self.session, 'test-round',
                     reports, output, authorized_sha256=sha256(self.raw), authorization_reference=AUTH)

    def persisted(self, path=None):
        path = path or self.journal
        return json.loads(path.read_bytes()) if path.exists() else None

    def lose_runner_at_journal_write(self, predicate, *, after=False, path=None):
        """Lose the runner at the first journal write whose content matches, before or after it lands."""
        original, fired, target = s3_run.write_json, [], path or self.journal

        def write(destination, value):
            if Path(destination) == target and not fired and predicate(value):
                fired.append(copy.deepcopy(value))
                if after:
                    original(destination, value)
                raise RunnerLost('journal write')
            return original(destination, value)
        return patch.object(s3_run, 'write_json', write), fired

    def lose_runner_inside_start(self, statement, *, submitted):
        """Lose the runner during StartQueryExecution of one statement, before or after AWS accepted it."""
        original, fired = self.athena.start_query_execution, []
        wanted = a.request(self.statement[statement], self.plan)

        def start(**kwargs):
            if kwargs == wanted and not fired:
                fired.append(original(**kwargs) if submitted else None)
                raise RunnerLost('start')
            return original(**kwargs)
        self.athena.start_query_execution = start
        return original, fired

    def assert_one_execution_per_statement(self, journal=None):
        journal = journal or self.persisted()
        self.assertEqual(len(self.athena.tokens), len(self.ids))
        for call in self.athena.calls:  # Every (re)transmission carried the frozen request and token.
            self.assertEqual(call, self.athena.tokens[call['ClientRequestToken']]['request'])
        for statement in self.plan['statements']:
            self.assertEqual(entry(journal, statement['id'])['request'], a.request(statement, self.plan))
            self.assertEqual(entry(journal, statement['id'])['state'], 'VERIFIED')
        self.assertEqual(len({e['query_id'] for e in journal['executions'].values()}), len(self.ids))

    def test_point_1_lost_before_the_new_entry_reaches_the_journal(self):
        lose, fired = self.lose_runner_at_journal_write(lambda j: entry(j, 'table-1') is not None)
        with lose, self.assertRaises(RunnerLost):
            self.execute()
        journal = self.persisted()
        self.assertEqual((list(journal['executions']), entry(journal, 'table-0')['state']), (['table-0'], 'VERIFIED'))
        self.assertEqual(len(self.athena.tokens), 1)
        result = self.execute()
        self.assertEqual((result['historically_reserved_requests'], result['api_calls']['new_starts'],
                          result['api_calls']['idempotent_retransmissions']), (1, 17, 0))
        self.assert_one_execution_per_statement()

    def test_point_2_lost_after_request_and_token_are_journaled(self):
        lose, _ = self.lose_runner_at_journal_write(
            lambda j: entry(j, 'table-1') is not None and 'start_attempts' not in entry(j, 'table-1'), after=True)
        with lose, self.assertRaises(RunnerLost):
            self.execute()
        saved = entry(self.persisted(), 'table-1')
        self.assertEqual((saved['state'], saved['query_id']), ('PREPARED', None))
        self.assertEqual(saved['request'], a.request(self.statement['table-1'], self.plan))
        self.assertEqual(len(self.athena.tokens), 1)  # The service never saw table-1.
        result = self.execute()
        # A journaled request is always re-sent as a retransmission: the executor cannot know it never left.
        self.assertEqual((result['historically_reserved_requests'], result['api_calls']['idempotent_retransmissions']), (2, 1))
        self.assert_one_execution_per_statement()

    def test_point_3_lost_before_the_remote_call(self):
        lose, _ = self.lose_runner_at_journal_write(lambda j: (entry(j, 'table-1') or {}).get('start_attempts') == 1, after=True)
        with lose, self.assertRaises(RunnerLost):
            self.execute()
        self.assertEqual(entry(self.persisted(), 'table-1')['start_attempts'], 1)
        self.assertEqual(len(self.athena.tokens), 1)
        self.execute()
        self.assertEqual(entry(self.persisted(), 'table-1')['start_attempts'], 2)  # The attempt history is kept.
        self.assert_one_execution_per_statement()

    def test_point_4_lost_after_submission_before_the_id_arrives(self):
        original, fired = self.lose_runner_inside_start('table-1', submitted=True)
        with self.assertRaises(RunnerLost):
            self.execute()
        self.athena.start_query_execution = original
        saved = entry(self.persisted(), 'table-1')
        self.assertEqual((saved['query_id'], saved['start_attempts']), (None, 1))
        self.assertEqual(len(self.athena.tokens), 2)  # Accepted remotely, unknown locally.
        self.execute()
        self.assertEqual(entry(self.persisted(), 'table-1')['query_id'], fired[0]['QueryExecutionId'])
        token = a.request(self.statement['table-1'], self.plan)['ClientRequestToken']
        self.assertEqual([c['ClientRequestToken'] for c in self.athena.calls].count(token), 2)  # Lost call + restart, same token.
        self.assert_one_execution_per_statement()

    def test_point_5_lost_after_the_id_arrives_before_it_is_journaled(self):
        lose, fired = self.lose_runner_at_journal_write(lambda j: (entry(j, 'table-1') or {}).get('query_id') is not None)
        with lose, self.assertRaises(RunnerLost):
            self.execute()
        self.assertIsNone(entry(self.persisted(), 'table-1')['query_id'])
        lost_id = entry(fired[0], 'table-1')['query_id']
        self.execute()
        self.assertEqual(entry(self.persisted(), 'table-1')['query_id'], lost_id)
        self.assert_one_execution_per_statement()

    def test_point_6_lost_while_polling_keeps_the_original_deadline(self):
        self.athena.running = True
        original, polls = self.athena.get_query_execution, []

        def poll(**kwargs):
            polls.append(kwargs)
            raise RunnerLost('polling')
        self.athena.get_query_execution = poll
        with self.assertRaises(RunnerLost):
            self.execute()
        self.athena.get_query_execution = original
        saved = entry(self.persisted(), 'table-0')
        self.assertEqual((saved['state'], saved['recorded_get_attempts']), ('SUBMITTED', 1))
        submitted_at, starts = saved['submitted_at'], len(self.athena.calls)
        # Restarted after the ORIGINAL deadline while AWS still runs it: stop, never a new submission.
        with self.assertRaisesRegex(IngestionError, 'ATHENA_QUERY_TIMEOUT'):
            self.execute(clock=lambda: submitted_at + 121, sleep=lambda _: None)
        saved = entry(self.persisted(), 'table-0')
        self.assertEqual((saved['state'], saved['submitted_at'], saved['cancellation_observation']['Status']['State']),
                         ('TIMED_OUT', submitted_at, 'CANCELLED'))
        self.assertEqual(self.athena.stopped, saved['query_id'])
        with self.assertRaisesRegex(IngestionError, 'ATHENA_PRIOR_EXECUTION_FAILED'):
            self.execute()
        self.assertEqual(len(self.athena.calls), starts)
        self.assertEqual(len(self.athena.tokens), 1)

    def test_point_6_wall_clock_step_back_after_restart_cannot_extend_the_deadline(self):
        self.athena.running = True
        original = self.athena.get_query_execution

        def lost(**kwargs):
            raise RunnerLost('polling')
        self.athena.get_query_execution = lost
        with self.assertRaises(RunnerLost):
            self.execute()
        submitted_at = entry(self.persisted(), 'table-0')['submitted_at']
        # The restarted runner starts past the deadline; the wall clock is set back while the GET is in flight.
        wall, ticks = [submitted_at + 121], itertools.count()

        def poll(**kwargs):
            wall[0] = submitted_at + 1
            return original(**kwargs)
        self.athena.get_query_execution = poll
        with self.assertRaisesRegex(IngestionError, 'ATHENA_QUERY_TIMEOUT'):
            self.execute(clock=lambda: wall[0], monotonic=lambda: next(ticks), sleep=lambda _: None)
        # One poll plus the cancellation read: the age measured at restart is never forgotten.
        self.assertEqual(entry(self.persisted(), 'table-0')['recorded_get_attempts'], 3)
        self.assertEqual(len(self.athena.tokens), 1)

    def test_point_6_restart_within_the_deadline_only_reads_by_id(self):
        self.athena.running = True
        original = self.athena.get_query_execution

        def lost(**kwargs):
            raise RunnerLost('polling')
        self.athena.get_query_execution = lost
        with self.assertRaises(RunnerLost):
            self.execute()
        self.athena.get_query_execution, self.athena.running = original, False
        before = entry(self.persisted(), 'table-0')
        result = self.execute()
        after = entry(self.persisted(), 'table-0')
        self.assertEqual((after['query_id'], after['submitted_at']), (before['query_id'], before['submitted_at']))
        self.assertEqual(after['recorded_get_attempts'], before['recorded_get_attempts'] + 1)
        self.assertEqual(result['api_calls']['idempotent_retransmissions'], 0)
        self.assert_one_execution_per_statement()

    def test_point_7_lost_before_the_final_evidence_is_published(self):
        reports = self.root / 'reports'
        with patch.object(a, '_final_readback', side_effect=RunnerLost('final evidence')), self.assertRaises(RunnerLost):
            self.run_round(reports, self.root / 'recovered-1')
        self.assertFalse((reports / 'execution-failure.json').exists())
        journal = self.persisted(reports / 'execution-journal.json')
        self.assertTrue(all(e['state'] == 'VERIFIED' for e in journal['executions'].values()))
        starts = len(self.athena.calls)
        result = self.run_round(reports, self.root / 'recovered-2')  # The restored journal on a new runner.
        self.assertEqual((result['code'], result['historically_reserved_requests'], result['remaining_unreserved_executions']),
                         ('ATHENA_RESULTS_VERIFIED', 18, 0))
        self.assertEqual((result['api_calls']['new_starts'], result['api_calls']['idempotent_retransmissions']), (0, 0))
        self.assertEqual(len(self.athena.calls), starts)
        self.assert_one_execution_per_statement(self.persisted(reports / 'execution-journal.json'))

    def test_ambiguous_5xx_start_after_server_side_creation_reuses_the_token(self):
        original = self.athena.start_query_execution

        def start(**kwargs):
            original(**kwargs)
            raise ServiceError(500, 'InternalServerException')
        self.athena.start_query_execution = start
        with self.assertRaises(IngestionError) as raised:
            self.execute()
        self.assertEqual((raised.exception.code, raised.exception.retryable), ('ATHENA_START_OUTCOME_UNKNOWN', True))
        self.athena.start_query_execution = original
        self.execute()
        self.assertEqual(len(self.athena.calls), 19)  # 18 statements + one identical retransmission.
        self.assert_one_execution_per_statement()

    def test_lost_latest_journal_and_existing_catalog_blocks_before_any_start(self):
        self.execute()
        reports = self.root / 'reports'
        reports.mkdir()
        older = self.persisted()
        older['executions'] = {'table-0': older['executions']['table-0']}  # The previous artifact, before the loss.
        (reports / 'execution-journal.json').write_bytes(canonical(older))
        starts = len(self.athena.calls)
        with self.assertRaisesRegex(IngestionError, 'ATHENA_CATALOG_NAME_CONFLICT'):
            self.run_round(reports, self.root / 'recovered')
        self.assertEqual(len(self.athena.calls), starts)
        failure = json.loads((reports / 'execution-failure.json').read_bytes())
        self.assertEqual(failure['code'], 'ATHENA_CATALOG_NAME_CONFLICT')

    def test_lost_latest_journal_replays_a_select_by_token_and_fails_closed(self):
        self.execute()
        original = self.persisted()
        older = dict(original, executions={k: original['executions'][k] for k in self.ids[:10]})
        self.journal.write_bytes(canonical(older))
        lost = self.ids[10]
        for _ in range(2):  # Every later restart stays blocked: an operator must reconcile by GET.
            with self.assertRaisesRegex(IngestionError, 'ATHENA_TIMING_INVALID'):
                self.execute(clock=lambda: time.time() + 5)
            replayed = entry(self.persisted(), lost)
            self.assertEqual((replayed['query_id'], replayed['state']), (original['executions'][lost]['query_id'], 'SUCCEEDED'))
            self.assertEqual(len(self.athena.tokens), 18)  # The token returned the existing execution; none was added.
            self.assertEqual(len(self.persisted()['executions']), 11)

    def test_corrupt_tampered_or_gapped_journal_stops_before_any_call(self):
        lose, _ = self.lose_runner_at_journal_write(lambda j: entry(j, 'table-1') is not None)
        with lose, self.assertRaises(RunnerLost):
            self.execute()
        good, calls = self.journal.read_bytes(), len(self.athena.calls)
        tampered = json.loads(good)
        tampered['executions']['table-0']['request']['ClientRequestToken'] = '0' * 64
        gapped = json.loads(good)
        gapped['executions'] = {'table-1': dict(gapped['executions']['table-0'])}
        unknown = json.loads(good)
        unknown['executions']['table-0']['query_id'] = 'unknown-execution'
        unknown['executions']['table-0']['execution']['QueryExecutionId'] = 'unknown-execution'
        for name, raw, error in (('truncated', good[:len(good) // 2], AnalyticsError),
                                 ('tampered-token', canonical(tampered), IngestionError),
                                 ('gap', canonical(gapped), IngestionError),
                                 ('unknown-id', canonical(unknown), IngestionError)):
            self.journal.write_bytes(raw)
            with self.subTest(name=name), self.assertRaises(error):
                self.execute()
            self.assertEqual(len(self.athena.calls), calls)
            self.assertEqual(len(self.athena.tokens), 1)

    def test_history_only_grows_across_repeated_losses(self):
        snapshots = []
        for predicate in (lambda j: entry(j, 'table-1') is not None and 'start_attempts' not in entry(j, 'table-1'),
                          lambda j: (entry(j, 'table-1') or {}).get('start_attempts') == 1,
                          lambda j: (entry(j, 'view-0') or {}).get('query_id') is not None):
            lose, _ = self.lose_runner_at_journal_write(predicate, after=True)
            with lose, self.assertRaises(RunnerLost):
                self.execute()
            snapshots.append(self.persisted())
        self.execute()
        snapshots.append(self.persisted())
        for before, after in zip(snapshots, snapshots[1:]):
            for statement, old in before['executions'].items():
                new = after['executions'][statement]
                self.assertEqual((new['request'], new['submitted_at']), (old['request'], old['submitted_at']))
                for counter in ('start_attempts', 'recorded_get_attempts'):
                    self.assertGreaterEqual(new.get(counter, 0), old.get(counter, 0))
                if old['query_id'] is not None:
                    self.assertEqual(new['query_id'], old['query_id'])
        self.assert_one_execution_per_statement()


class ArtifactRecoveryLossTests(unittest.TestCase):
    """Crash point 8: the exact-artifact restore, before any AWS credential."""
    setUpClass = classmethod(support.historical_profile)

    def setUp(self):
        restore_support.AthenaRestoreTests.setUp(self)

    def restore(self):
        return restore_support.AthenaRestoreTests.restore(self)

    def resume_main(self):
        report = self.root / 'reports/result.json'
        with patch.object(a, 'aws_clients', side_effect=AssertionError('no AWS client after a failed restore')) as clients, \
                redirect_stdout(io.StringIO()):
            status = a.main(['--config', str(support.HISTORICAL / 'lab-poc.json'),
                             '--athena-config', str(support.HISTORICAL / 'athena-lab-poc.json'),
                             '--report', str(report), '--output', str(self.root / 'out'),
                             '--session-name', 'test-session', '--round-id', 'lab-sbom-athena-v1',
                             '--authorized-plan-sha256', restore_support.PLAN_HASH,
                             '--authorization-reference', restore_support.AUTH,
                             '--resume-receipt', str(self.root / 'reports/resume-receipt.json')])
        return status, json.loads(report.read_bytes()), clients.called

    def test_truncated_download_never_becomes_a_working_journal(self):
        self.client.raw = self.raw[:len(self.raw) // 2]
        with self.assertRaisesRegex(IngestionError, 'RESUME_ZIP_DIGEST_DIFFERS'):
            self.restore()
        self.assertFalse((self.root / 'reports/execution-journal.json').exists())
        status, result, clients = self.resume_main()
        self.assertEqual((status, result['status'], clients), (1, 'ERROR', False))

    def test_loss_while_copying_leaves_an_unusable_partial_restore(self):
        with patch.object(r.os, 'chmod', side_effect=RunnerLost('restore copy')), self.assertRaises(RunnerLost):
            self.restore()
        reports = self.root / 'reports'
        self.assertTrue((reports / 'execution-journal.json').exists())
        self.assertFalse((reports / 'sql-plan.json').exists() or (reports / 'resume-receipt.json').exists())
        with self.assertRaisesRegex(IngestionError, 'RESUME_DESTINATION_EXISTS'):
            self.restore()  # Never overwrites what a lost attempt left behind.
        status, result, clients = self.resume_main()
        self.assertEqual((status, result['status'], clients), (1, 'ERROR', False))


if __name__ == '__main__':
    unittest.main()
