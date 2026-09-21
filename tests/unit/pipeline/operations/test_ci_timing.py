import unittest
from scripts.pipeline.operations.ci_timing import aggregate, breakdown


def run(created, updated, run_id=1):
    return {'id': run_id, 'event': 'pull_request', 'head_branch': 'x',
            'created_at': created, 'updated_at': updated}


def job(name, created, started, completed, steps=(), conclusion='success'):
    return {'name': name, 'conclusion': conclusion, 'created_at': created,
            'started_at': started, 'completed_at': completed,
            'steps': [{'name': step_name, 'started_at': step_start, 'completed_at': step_end}
                      for step_name, step_start, step_end in steps]}


class BreakdownTests(unittest.TestCase):
    def test_default_required_checks_match_current_ci_display_names(self):
        the_run = run('2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z')
        jobs = [job(name, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                    '2026-01-01T00:00:24Z') for name in
                ('Unit & integration tests', 'Repository & workflow lint')]
        result = breakdown(the_run, jobs)
        self.assertEqual(result['required_checks'], {'seconds': 24, 'missing': []})

    def test_queued_and_duration_from_real_timestamps(self):
        the_run = run('2026-01-01T00:00:00Z', '2026-01-01T00:00:20Z')
        jobs = [job('test', '2026-01-01T00:00:00Z', '2026-01-01T00:00:05Z', '2026-01-01T00:00:20Z')]
        result = breakdown(the_run, jobs)
        self.assertEqual(result['jobs'][0]['queued_seconds'], 5)
        self.assertEqual(result['jobs'][0]['duration_seconds'], 15)
        self.assertEqual(result['total_seconds'], 20)

    def test_steps_sorted_by_duration_descending(self):
        the_run = run('2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z')
        jobs = [job('lint-workflows', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z',
                    steps=[('checkout', '2026-01-01T00:00:00Z', '2026-01-01T00:00:02Z'),
                           ('actionlint', '2026-01-01T00:00:02Z', '2026-01-01T00:00:40Z'),
                           ('hardening', '2026-01-01T00:00:40Z', '2026-01-01T00:00:50Z')])]
        result = breakdown(the_run, jobs)
        names = [step['name'] for step in result['jobs'][0]['steps']]
        self.assertEqual(names, ['actionlint', 'hardening', 'checkout'])

    def test_dependent_and_serialized_jobs_flagged_not_hidden(self):
        the_run = run('2026-01-01T00:00:00Z', '2026-01-01T00:02:00Z')
        # build-push's queued_seconds is dominated by waiting for `validate`
        # to finish, not runner availability -- the caller must say so.
        jobs = [job('validate', '2026-01-01T00:00:00Z', '2026-01-01T00:00:01Z', '2026-01-01T00:01:00Z'),
                job('Build & push go1-26', '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z', '2026-01-01T00:02:00Z')]
        result = breakdown(the_run, jobs, dependent=['Build & push go1-26'], serialized=['validate'])
        by_name = {entry['job']: entry for entry in result['jobs']}
        self.assertTrue(by_name['Build & push go1-26']['dependent'])
        self.assertFalse(by_name['Build & push go1-26']['serialized'])
        self.assertTrue(by_name['validate']['serialized'])
        # Still reports the raw number -- flagging is not hiding.
        self.assertEqual(by_name['Build & push go1-26']['queued_seconds'], 60)

    def test_required_checks_seconds_uses_the_slowest_one(self):
        the_run = run('2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z')
        jobs = [job('test', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:24Z'),
                job('lint-workflows', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:05Z')]
        result = breakdown(the_run, jobs, required=['test', 'lint-workflows'])
        self.assertEqual(result['required_checks']['seconds'], 24)
        self.assertEqual(result['required_checks']['missing'], [])

    def test_required_checks_reports_missing_instead_of_guessing(self):
        the_run = run('2026-01-01T00:00:00Z', '2026-01-01T00:00:05Z')
        jobs = [job('test', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:05Z')]
        result = breakdown(the_run, jobs, required=['test', 'lint-workflows'])
        self.assertIsNone(result['required_checks']['seconds'])
        self.assertEqual(result['required_checks']['missing'], ['lint-workflows'])

    def test_skipped_job_reports_no_duration_instead_of_negative(self):
        # Real case found running this against actual PR runs: a `skipped`
        # job's completed_at can land before started_at in the API,
        # which would otherwise compute as a negative duration.
        the_run = run('2026-01-01T00:00:00Z', '2026-01-01T00:00:10Z')
        jobs = [job('promote-stable', '2026-01-01T00:00:05Z', '2026-01-01T00:00:05Z',
                    '2026-01-01T00:00:04Z', conclusion='skipped')]
        result = breakdown(the_run, jobs)
        self.assertIsNone(result['jobs'][0]['queued_seconds'])
        self.assertIsNone(result['jobs'][0]['duration_seconds'])
        self.assertEqual(result['jobs'][0]['steps'], [])

    def test_in_progress_job_has_no_duration_yet(self):
        the_run = run('2026-01-01T00:00:00Z', None)
        jobs = [{'name': 'validate', 'conclusion': None, 'created_at': '2026-01-01T00:00:00Z',
                'started_at': '2026-01-01T00:00:01Z', 'completed_at': None, 'steps': []}]
        result = breakdown(the_run, jobs)
        self.assertIsNone(result['jobs'][0]['duration_seconds'])
        self.assertIsNone(result['total_seconds'])


class AggregateTests(unittest.TestCase):
    def test_median_and_p90_across_runs(self):
        breakdowns = [
            breakdown(run('2026-01-01T00:00:00Z', f'2026-01-01T00:00:{seconds:02d}Z', run_id=i),
                      [job('test', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                           f'2026-01-01T00:00:{seconds:02d}Z')])
            for i, seconds in enumerate([10, 20, 30, 40, 50], start=1)
        ]
        result = aggregate(breakdowns)
        self.assertEqual(result['runs'], 5)
        self.assertEqual(result['total_seconds']['median'], 30)
        self.assertEqual(result['total_seconds']['n'], 5)

    def test_dominant_step_identified_by_median_duration(self):
        def one_run(actionlint_seconds, run_id):
            return breakdown(
                run('2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z', run_id=run_id),
                [job('lint-workflows', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z',
                    steps=[('checkout', '2026-01-01T00:00:00Z', '2026-01-01T00:00:02Z'),
                           ('actionlint', '2026-01-01T00:00:02Z',
                            f'2026-01-01T00:00:{2 + actionlint_seconds:02d}Z')])])
        breakdowns = [one_run(seconds, i) for i, seconds in enumerate([30, 32, 28], start=1)]
        result = aggregate(breakdowns)
        self.assertEqual(result['dominant_steps'][0]['step'], 'actionlint')
        self.assertEqual(result['dominant_steps'][0]['median'], 30)
        self.assertEqual(result['dominant_steps'][0]['n'], 3)

    def test_dependent_flag_preserved_through_aggregation(self):
        breakdowns = [breakdown(run('2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z', run_id=i),
                                [job('Build & push go1-26', '2026-01-01T00:00:00Z',
                                     '2026-01-01T00:00:30Z', '2026-01-01T00:01:00Z')],
                                dependent=['Build & push go1-26'])
                      for i in range(3)]
        result = aggregate(breakdowns)
        self.assertTrue(result['jobs']['Build & push go1-26']['dependent'])

    def test_requires_at_least_one_run(self):
        with self.assertRaises(ValueError):
            aggregate([])
