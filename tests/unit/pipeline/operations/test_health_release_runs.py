from datetime import datetime, timezone
import json
import unittest
from unittest.mock import Mock

from scripts.pipeline.operations import operational_health as health


class ReleaseRunHealthTests(unittest.TestCase):
    def test_only_develop_releases_consume_the_query_budget(self):
        now = datetime(2026, 9, 10, tzinfo=timezone.utc)
        runs = [dict(id=n, created_at='2026-09-10T00:00:00Z', event=event,
                     head_branch=branch) for n, event, branch in (
                         (1, 'pull_request', 'develop'),
                         (2, 'workflow_dispatch', 'feature'),
                         (4, 'push', 'main'),
                         (5, 'schedule', 'main'),
                         (6, 'workflow_dispatch', 'main'),
                         (3, 'push', 'develop'))]
        seen = []

        def jobs(identifier):
            seen.append(identifier)
            return [{'name': 'build-base-images / Build & push nodejs22',
                     'conclusion': 'success', 'completed_at': '2026-09-10T00:00:00Z'}]

        result = health.framework_health(jobs, runs, ['nodejs22'], now, max_queries=1)
        self.assertEqual(seen, [3])
        self.assertFalse(result['truncated'])
        self.assertEqual(result['frameworks']['nodejs22']['publication_run'], 3)

    def test_missing_branch_cannot_be_assumed_to_be_dev(self):
        now = datetime(2026, 9, 10, tzinfo=timezone.utc)
        jobs = Mock()
        result = health.framework_health(jobs, [
            {'id': 1, 'created_at': '2026-09-10T00:00:00Z', 'event': 'push'}
        ], ['nodejs22'], now)
        jobs.assert_not_called()
        self.assertIsNone(result['frameworks']['nodejs22']['publication_age_hours'])

    def test_main_schedules_cannot_count_as_develop_health(self):
        now = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
        policy = json.loads((health.ROOT / 'policies/operations/health.json').read_text())
        runs = [dict(id=index, event='schedule', head_branch=branch,
                     path='.github/workflows/workflow.yml',
                     created_at='2026-09-10T03:23:00Z',
                     run_started_at='2026-09-10T03:24:00Z')
                for index, branch in enumerate(('main', 'develop', 'feature', None), 1)]
        seen = []

        def fetch(endpoint):
            seen.append(endpoint)
            if '/actions/workflows?' in endpoint:
                return {'workflows': []}
            if '/actions/runs?' in endpoint:
                return {'workflow_runs': runs if endpoint.endswith('&page=1') else []}
            if '/actions/runs/2/jobs?' in endpoint:
                return {'jobs': [{'name': 'build-base-images / Build & push nodejs22',
                                 'conclusion': 'success',
                                 'completed_at': '2026-09-10T03:25:00Z'}]}
            self.fail(f'non-DEV job lookup: {endpoint}')

        result = health.collect(fetch, 'owner/repo', policy, now)
        self.assertEqual(result['runs_analysed'], 1)
        build_schedule = next(item for item in result['schedules']
                              if item['cron'] == '23 3 * * *')
        self.assertEqual(build_schedule['observed'], 1)
        self.assertEqual(result['queue']['samples'], 1)
        self.assertEqual(result['frameworks']['frameworks']['nodejs22']['publication_run'], 2)
        self.assertEqual(len([path for path in seen if '/jobs?' in path]), 1)
