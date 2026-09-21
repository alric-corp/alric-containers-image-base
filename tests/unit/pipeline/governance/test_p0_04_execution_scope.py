"""Guards for the temporary, exact P0-04 execution scope."""

import json
from pathlib import Path
import re
import unittest

import yaml

from scripts.pipeline.catalog import default_batch
from scripts.pipeline.runtime import runtime_images


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / '.github/workflows/workflow.yml'
PROMOTE_WORKFLOW = ROOT / '.github/workflows/promote-stable.yml'
RECOVER_WORKFLOW = ROOT / '.github/workflows/recover-stable.yml'
P0_04 = ['go1-26', 'go1-26-dev']


class P0_04ExecutionScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(WORKFLOW.read_text())
        cls.jobs = cls.document['jobs']
        cls.promotion = yaml.safe_load(PROMOTE_WORKFLOW.read_text())

    def test_build_and_pr_selection_is_exact(self):
        self.assertEqual(
            json.loads(self.jobs['validate-pr']['with']['frameworks']), P0_04)
        self.assertEqual(
            self.jobs['build-base-images']['with']['frameworks'],
                         '["go1-26", "go1-26-dev"]')

    def test_shared_pr_caller_is_the_current_full_batch(self):
        full = json.loads(self.jobs['validate-pr-full']['with']['frameworks'])
        names, policy, _ = default_batch.load()
        excluded, problems = default_batch.exclusions(policy)
        self.assertEqual(problems, [])
        self.assertEqual(full, default_batch.expected_batch(names, excluded))

    def test_other_frameworks_are_not_selected(self):
        selected = set(json.loads(self.jobs['validate-pr']['with']['frameworks']))
        for framework in ('java21', 'nodejs22', 'python3-13', 'dotnet10',
                          'go1-25', 'go1-25-dev'):
            self.assertNotIn(framework, selected)

    def test_catalog_remains_complete(self):
        catalog = {path.stem for path in (ROOT / 'frameworks').glob('*.yaml')}
        self.assertIn('java21', catalog)
        self.assertIn('nodejs22', catalog)
        self.assertIn('python3-13', catalog)
        self.assertIn('dotnet10', catalog)
        self.assertIn('go1-25', catalog)
        self.assertIn('go1-25-dev', catalog)
        self.assertTrue(set(P0_04) <= catalog)

    def test_dev_is_companion_of_go_runtime_contract(self):
        planned, skipped = runtime_images.plan(P0_04)
        self.assertEqual(planned, ['go1-26'])
        self.assertIn('go1-26-dev', skipped)

    def test_publication_scope_has_no_stable(self):
        selected = json.loads(self.jobs['validate-pr']['with']['frameworks'])
        self.assertEqual([f'image-base-{name}' for name in selected],
                         ['image-base-go1-26', 'image-base-go1-26-dev'])
        self.assertNotIn('stable', self.jobs['build-base-images']['with']['frameworks'])


class ScheduleSeparationTests(unittest.TestCase):
    """Build/publication scheduling lives in workflow.yml; stable promotion
    scheduling lives in promote-stable.yml, on its own native schedule."""

    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(WORKFLOW.read_text())
        cls.workflow_triggers = cls.workflow.get('on') or cls.workflow.get(True)
        cls.promotion = yaml.safe_load(PROMOTE_WORKFLOW.read_text())
        cls.promotion_triggers = cls.promotion.get('on') or cls.promotion.get(True)

    def test_workflow_yml_has_only_the_daily_build_schedule(self):
        crons = [entry['cron'] for entry in self.workflow_triggers['schedule']]
        self.assertEqual(crons, ['23 3 * * *'])
        policy = json.loads((ROOT / 'policies/operations/health.json').read_text())
        self.assertEqual(policy['schedules'][crons[0]]['gap_alert_hours'], 30)
        self.assertEqual(policy['schedules'][crons[0]]['workflow'], '.github/workflows/workflow.yml')
        self.assertIn(crons[0], self.workflow['jobs']['build-base-images']['if'])

    def test_promote_stable_job_is_absent_from_workflow_yml(self):
        self.assertNotIn('promote-stable', self.workflow['jobs'])

    def test_promote_stable_yml_has_the_hourly_promotion_schedule(self):
        crons = [entry['cron'] for entry in self.promotion_triggers['schedule']]
        self.assertEqual(crons, ['17 * * * *'])

    def test_no_cron_is_declared_in_more_than_one_workflow(self):
        crons_by_file = {}
        for path in sorted((ROOT / '.github/workflows').glob('*.yml')):
            document = yaml.safe_load(path.read_text()) or {}
            triggers = document.get(True) or document.get('on') or {}
            for entry in triggers.get('schedule') or []:
                crons_by_file.setdefault(entry['cron'], []).append(path.name)
        for cron, files in crons_by_file.items():
            with self.subTest(cron=cron):
                self.assertEqual(len(files), 1, f'{cron} declared in {files}')

    def _scheduled_run_default(self, name):
        step = self.promotion['jobs']['resolve-defaults']['steps'][0]
        match = re.search(rf'\$\{{{re.escape(name)}:-([^}}]*)\}}', step['run'])
        self.assertIsNotNone(match, f'no fallback found for {name}')
        return match.group(1)

    def test_scheduled_promotion_defaults_match_the_p0_04_profile(self):
        raw = self._scheduled_run_default('FRAMEWORKS').replace('\\"', '"')
        self.assertEqual(json.loads(raw), P0_04)

    def test_scheduled_promotion_soak_hours_default_is_six(self):
        self.assertEqual(self._scheduled_run_default('SOAK_HOURS'), '6')

    def test_promote_job_reads_the_resolved_defaults_not_raw_inputs(self):
        promote = self.promotion['jobs']['promote']
        self.assertIn('resolve-defaults', promote['needs'])
        self.assertNotIn('strategy', promote)
        execution = next(step for step in promote['steps'] if step.get('id') == 'candidate')
        self.assertEqual(execution['env']['FRAMEWORKS'],
                         '${{ needs.resolve-defaults.outputs.frameworks }}')
        self.assertEqual(execution['env']['SOAK_HOURS'],
                         '${{ needs.resolve-defaults.outputs.soak-hours }}')

    def test_promotion_only_changes_do_not_trigger_a_full_build(self):
        for event in ('push', 'pull_request'):
            self.assertNotIn('.github/workflows/promote-stable.yml',
                             self.workflow_triggers[event]['paths'])

    def test_promotion_and_recovery_share_the_same_concurrency_namespace(self):
        recovery = yaml.safe_load(RECOVER_WORKFLOW.read_text())
        promote_group = self.promotion['jobs']['promote']['concurrency']['group']
        recover_group = recovery['jobs']['recover']['concurrency']['group']

        def normalize(group):
            return (group
                    .replace('${{ inputs.aws-role-arn || vars.AWS_ROLE_ARN }}',
                            '${{ vars.AWS_ROLE_ARN }}')
                    .replace('${{ inputs.aws-region || vars.AWS_REGION }}',
                            '${{ vars.AWS_REGION }}')
                    .replace('${{ matrix.framework }}', '${{ FRAMEWORK }}')
                    .replace('${{ inputs.framework }}', '${{ FRAMEWORK }}'))

        self.assertEqual(normalize(promote_group), normalize(recover_group))
        self.assertFalse(self.promotion['jobs']['promote']['concurrency']['cancel-in-progress'])
        self.assertFalse(recovery['jobs']['recover']['concurrency']['cancel-in-progress'])


if __name__ == '__main__':
    unittest.main()
