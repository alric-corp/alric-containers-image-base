from datetime import datetime, timedelta, timezone
import unittest

from scripts.pipeline.operations import operational_health as health

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def run(created, event='schedule', started=None, identifier=1, conclusion='success'):
    return {'id': identifier, 'event': event, 'conclusion': conclusion,
            'created_at': created.isoformat().replace('+00:00', 'Z'),
            'run_started_at': (started or created).isoformat().replace('+00:00', 'Z'),
            'path': '.github/workflows/workflow.yml'}


class CronTests(unittest.TestCase):
    def test_lists_ranges_and_steps(self):
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)
        self.assertEqual(len(health.cron_occurrences('*/15 * * * *', start, end)), 5)
        self.assertEqual(len(health.cron_occurrences('0,30 * * * *', start, end)), 3)
        self.assertEqual(len(health.cron_occurrences('0 0-2 * * *', start, end)), 2)

    def test_unsupported_forms_are_refused_instead_of_guessed(self):
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        for expression in ('0 3 * * 1', '0 3 1 * *', '0 3 * 5 *', '0 3 * *', '0 99 * * *'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                health.cron_occurrences(expression, start, start + timedelta(days=2))


class ScheduleTests(unittest.TestCase):
    def test_the_cron_is_attributed_by_the_job_that_actually_ran(self):
        # A API não expõe `github.event.schedule`: num run da promoção horária
        # o chamador do build diário aparece `skipped`, e vice-versa.
        jobs = {
            1: [{'name': 'build-base-images', 'conclusion': 'skipped'},
                {'name': 'promote-stable / Promote nodejs22', 'conclusion': 'success'}],
            2: [{'name': 'build-base-images / Build & push nodejs22', 'conclusion': 'success'},
                {'name': 'promote-stable', 'conclusion': 'skipped'}],
            3: [{'name': 'build-base-images', 'conclusion': 'skipped'},
                {'name': 'promote-stable', 'conclusion': 'skipped'}],
        }
        runs = [run(datetime(2026, 9, 10, 4, 17, tzinfo=timezone.utc), identifier=1),
                run(datetime(2026, 9, 10, 7, 36, tzinfo=timezone.utc), identifier=2),
                run(datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc), identifier=3),
                run(datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc), event='push',
                    identifier=4)]
        schedules = {'0 3 * * *': {'job': 'build-base-images'},
                     '17 * * * *': {'job': 'promote-stable'}}
        attributed, unattributed = health.attribute_runs(lambda identifier: jobs[identifier],
                                                        runs, schedules)
        self.assertEqual([entry['id'] for entry in attributed['17 * * * *']], [1])
        self.assertEqual([entry['id'] for entry in attributed['0 3 * * *']], [2])
        # Run agendado em que nenhum job do cron rodou não é chutado para um
        # dos dois; e run de push não entra na conta do agendamento.
        self.assertEqual([entry['run_id'] for entry in unattributed], [3])

    def test_delay_is_measured_against_the_previous_occurrence_without_a_tolerance(self):
        start = datetime(2026, 9, 9, tzinfo=timezone.utc)
        now = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
        # Atraso real observado na conta: o cron diário das 03:00 disparou às
        # 07:36. Com tolerância fixa isso viraria "ocorrência sem run" e mais
        # um run órfão; medido contra a ocorrência anterior, é um atraso.
        runs = [run(datetime(2026, 9, 9, 7, 36, tzinfo=timezone.utc))]
        result = health.schedule_health('0 3 * * *', runs, start, now, now)
        self.assertEqual(result['expected'], 2)
        self.assertEqual(result['observed'], 1)
        self.assertEqual(result['trigger_delay_seconds']['max'], 16560.0)
        self.assertEqual(result['missing'], ['2026-09-10T03:00:00+00:00'])
        self.assertEqual(result['coverage_percent'], 50.0)

    def test_gap_and_time_since_last_run_expose_a_schedule_that_stopped(self):
        start = datetime(2026, 9, 3, tzinfo=timezone.utc)
        now = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
        runs = [run(datetime(2026, 9, 3, 3, 5, tzinfo=timezone.utc), identifier=1),
                run(datetime(2026, 9, 6, 3, 5, tzinfo=timezone.utc), identifier=2)]
        result = health.schedule_health('0 3 * * *', runs, start, now, now)
        self.assertEqual(result['max_gap_hours'], 72.0)
        self.assertEqual(result['hours_since_last_run'], 104.92)

    def test_two_runs_for_the_same_occurrence_are_reported_as_duplicates(self):
        start = datetime(2026, 9, 9, tzinfo=timezone.utc)
        now = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
        runs = [run(datetime(2026, 9, 9, 3, 5, tzinfo=timezone.utc), identifier=1),
                run(datetime(2026, 9, 9, 3, 40, tzinfo=timezone.utc), identifier=2)]
        result = health.schedule_health('0 3 * * *', runs, start, now, now)
        self.assertEqual(result['observed'], 2)
        self.assertEqual(result['duplicate_runs'], [2])
        self.assertEqual(result['coverage_percent'], 100.0)

    def test_queue_delay_measures_wait_for_a_runner(self):
        created = datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)
        runs = [run(created, started=created + timedelta(seconds=seconds), identifier=index)
                for index, seconds in enumerate((10, 20, 300))]
        result = health.queue_health(runs)
        self.assertEqual(result['samples'], 3)
        self.assertEqual(result['median'], 20.0)
        self.assertEqual(result['max'], 300.0)


class FrameworkHealthTests(unittest.TestCase):
    def jobs(self, promoted):
        return {'jobs': [
            {'name': 'build-base-images / Build & push nodejs22', 'conclusion': 'success',
             'completed_at': '2026-09-10T03:10:00Z', 'steps': []},
            {'name': 'promote-stable / Promote nodejs22', 'conclusion': 'success',
             'completed_at': '2026-09-10T04:20:00Z',
             'steps': [{'name': 'Promote to stable',
                        'conclusion': 'success' if promoted else 'skipped'}]},
        ]}

    def test_a_promotion_run_that_skipped_is_not_a_promotion(self):
        runs = [run(datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc))]
        result = health.framework_health(lambda identifier: self.jobs(False)['jobs'], runs,
                                        ['nodejs22'], NOW)
        entry = result['frameworks']['nodejs22']
        self.assertIsNone(entry['stable_age_hours'])
        # O gate rodou e avaliou: isso é medido separadamente de "promoveu".
        self.assertIsNotNone(entry['promotion_checked_age_hours'])
        self.assertEqual(entry['publication_age_hours'], 8.83)

    def test_promoted_run_sets_the_stable_pointer_age(self):
        runs = [run(datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc))]
        result = health.framework_health(lambda identifier: self.jobs(True)['jobs'], runs,
                                        ['nodejs22'], NOW)
        self.assertEqual(result['frameworks']['nodejs22']['stable_age_hours'], 7.67)

    def test_truncated_search_is_flagged_instead_of_reported_as_never(self):
        runs = [run(NOW - timedelta(hours=index), identifier=index) for index in range(1, 6)]
        result = health.framework_health(lambda identifier: [], runs,
                                        ['nodejs22'], NOW, max_queries=2)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['job_queries'], 2)


class EvaluateTests(unittest.TestCase):
    POLICY = {'thresholds': {'publication_age_hours': 30, 'stable_age_hours': 48,
                             'queue_delay_p90_seconds': 900, 'window_days': 7},
              'schedules': {'0 3 * * *': {'job': 'build-base-images', 'gap_alert_hours': 30},
                            '17 * * * *': {'job': 'promote-stable', 'gap_alert_hours': 12}},
              'exceptions': {'dotnet8': {'reason': 'sem pacote corrigido no Wolfi',
                                         'owner': '@owner', 'review_by': '2026-10-09'}}}

    def metrics(self, **overrides):
        base = {
            'frameworks': {'frameworks': {
                'nodejs22': {'publication_age_hours': 2.0, 'stable_age_hours': 5.0},
                'dotnet8': {'publication_age_hours': None, 'stable_age_hours': None},
            }, 'truncated': False, 'job_queries': 5},
            'schedules': [{'cron': '0 3 * * *', 'expected': 7, 'observed': 7, 'missing': [],
                           'hours_since_last_run': 4.0, 'max_gap_hours': 25.0}],
            'queue': {'samples': 3, 'p90': 30.0},
            'workflow': '.github/workflows/workflow.yml',
        }
        base.update(overrides)
        return base

    def test_documented_exception_is_known_not_a_new_alert(self):
        alerts = health.evaluate(self.metrics(), self.POLICY, NOW)
        levels = {alert['subject']: alert['level'] for alert in alerts}
        self.assertEqual(levels['dotnet8'], 'known')
        self.assertNotIn('nodejs22', levels)
        self.assertTrue(all(alert['level'] == 'known' for alert in alerts))

    # ADR-0004: execution_scope não deve interferir quando ausente (padrão
    # anterior a este campo) nem afetar frameworks que estão em `current`.
    def test_absent_execution_scope_behaves_exactly_as_before(self):
        alerts = health.evaluate(self.metrics(), self.POLICY, NOW)
        self.assertNotIn('out_of_scope', {alert['level'] for alert in alerts})

    def test_framework_outside_execution_scope_is_out_of_scope_not_alert(self):
        metrics = self.metrics()
        # Sem publicação/stable, como qualquer framework fora do lote
        # automático atual -- exatamente o caso real que este ADR cobre.
        metrics['frameworks']['frameworks']['nodejs22'] = {
            'publication_age_hours': None, 'stable_age_hours': None}
        policy = dict(self.POLICY, execution_scope={
            'current': ['go1-26', 'go1-26-dev'], 'reason': 'V1 de referência',
            'owner': '@owner', 'review_by': '2026-09-30'})
        alerts = health.evaluate(metrics, policy, NOW)
        levels = {alert['subject']: alert['level'] for alert in alerts
                  if alert['subject'] == 'nodejs22'}
        self.assertTrue(levels)
        self.assertTrue(all(level == 'out_of_scope' for level in levels.values()))

    def test_framework_inside_execution_scope_still_alerts_when_stale(self):
        metrics = self.metrics()
        metrics['frameworks']['frameworks']['nodejs22']['publication_age_hours'] = 40.0
        policy = dict(self.POLICY, execution_scope={
            'current': ['nodejs22'], 'reason': 'teste',
            'owner': '@owner', 'review_by': '2026-09-30'})
        alerts = health.evaluate(metrics, policy, NOW)
        stale = [a for a in alerts if a['subject'] == 'nodejs22'
                and a['metric'] == 'publication_age_hours']
        self.assertEqual(stale[0]['level'], 'alert')

    def test_execution_scope_without_review_by_is_flagged(self):
        policy = dict(self.POLICY, execution_scope={
            'current': ['go1-26'], 'reason': 'teste', 'owner': '@owner'})
        alerts = health.evaluate(self.metrics(), policy, NOW)
        flagged = [a for a in alerts if a['metric'] == 'execution_scope_review']
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]['level'], 'alert')

    def test_expired_execution_scope_review_alerts(self):
        policy = dict(self.POLICY, execution_scope={
            'current': ['go1-26'], 'reason': 'teste', 'owner': '@owner',
            'review_by': '2026-08-01'})
        alerts = health.evaluate(self.metrics(), policy, NOW)
        flagged = [a for a in alerts if a['metric'] == 'execution_scope_review']
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]['level'], 'alert')
        self.assertIn('2026-08-01', flagged[0]['message'])

    def test_expired_exception_becomes_an_alert_of_its_own(self):
        policy = dict(self.POLICY,
                      exceptions={'dotnet8': dict(self.POLICY['exceptions']['dotnet8'],
                                                  review_by='2026-08-01')})
        alerts = health.evaluate(self.metrics(), policy, NOW)
        expired = [alert for alert in alerts if alert['metric'] == 'exception_review']
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0]['level'], 'alert')

    def test_a_cron_that_stopped_generating_runs_alerts(self):
        # O caso que não deixa run vermelho para ninguém olhar: o agendador
        # simplesmente parou de disparar.
        metrics = self.metrics(schedules=[{'cron': '17 * * * *', 'expected': 168,
                                           'observed': 3, 'missing': ['x'] * 165,
                                           'hours_since_last_run': 40.0,
                                           'max_gap_hours': 40.0}])
        alerts = health.evaluate(metrics, self.POLICY, NOW)
        gap = [alert for alert in alerts if alert['metric'] == 'schedule_gap_hours']
        self.assertEqual(gap[0]['level'], 'alert')
        self.assertIn('40.0h', gap[0]['message'])

    def test_no_scheduled_run_at_all_alerts_instead_of_passing_silently(self):
        metrics = self.metrics(schedules=[{'cron': '17 * * * *', 'expected': 168, 'observed': 0,
                                           'missing': ['x'] * 168, 'hours_since_last_run': None,
                                           'max_gap_hours': None}])
        alerts = health.evaluate(metrics, self.POLICY, NOW)
        gap = [alert for alert in alerts if alert['metric'] == 'schedule_gap_hours']
        self.assertEqual(gap[0]['level'], 'alert')

    def test_truncated_search_reports_unknown_instead_of_a_false_alert(self):
        metrics = self.metrics()
        metrics['frameworks']['truncated'] = True
        alerts = health.evaluate(metrics, self.POLICY, NOW)
        levels = {(alert['metric'], alert['subject']): alert['level'] for alert in alerts}
        self.assertEqual(levels[('publication_age_hours', 'dotnet8')], 'unknown')
        self.assertEqual(levels[('job_queries_truncated', '.github/workflows/workflow.yml')],
                         'alert')

    def test_stale_publication_alerts_for_a_framework_without_exception(self):
        metrics = self.metrics()
        metrics['frameworks']['frameworks']['nodejs22']['publication_age_hours'] = 40.0
        alerts = health.evaluate(metrics, self.POLICY, NOW)
        stale = [alert for alert in alerts if alert['subject'] == 'nodejs22']
        self.assertEqual(stale[0]['level'], 'alert')
        self.assertIn('40.0h', stale[0]['message'])

    def test_the_versioned_policy_declares_exactly_the_scheduled_crons(self):
        import json
        policy = json.loads((health.ROOT / 'policies/operations/health.json').read_text())
        self.assertEqual(health.schedule_declaration(policy), [])


class RetentionTests(unittest.TestCase):
    POLICY = {'retention_days': {'build-scans-': 30, 'validated-oci-': 3, '$comment': 'ignorado'}}

    def test_declared_policy_must_match_the_workflows(self):
        entries = [{'file': 'a.yml', 'job': 'validate', 'name': 'build-scans-${{ x }}',
                    'prefix': 'build-scans-', 'retention_days': 7},
                   {'file': 'a.yml', 'job': 'validate', 'name': 'validated-oci-${{ x }}',
                    'prefix': 'validated-oci-', 'retention_days': 3}]
        problems = health.retention_drift(entries, self.POLICY)
        self.assertEqual(len(problems), 1)
        self.assertIn('retention-days=7', problems[0])

    def test_artifact_without_policy_and_policy_without_artifact_are_both_drift(self):
        entries = [{'file': 'a.yml', 'job': 'x', 'name': 'novo-artifact', 'prefix': 'novo-artifact',
                    'retention_days': 30}]
        problems = health.retention_drift(entries, self.POLICY)
        self.assertTrue(any('não tem retenção definida' in problem for problem in problems))
        self.assertTrue(any('nenhum workflow usa mais' in problem for problem in problems))

if __name__ == '__main__':
    unittest.main()
