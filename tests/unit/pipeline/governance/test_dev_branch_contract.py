"""DEV execution remains branch-bound at entry points and AWS-capable jobs."""
from pathlib import Path
from types import SimpleNamespace
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[4]
REPOSITORY = 'alric-corp/alric-containers-image-base'


def workflow(name):
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())


def events(document):
    return document.get('on', document.get(True))


def enabled(name, job, *, branch='develop', event='workflow_dispatch',
            schedule='', authorized='true', base='develop', source=REPOSITORY):
    """Evaluate the repository's boolean guards against explicit event contexts."""
    expression = workflow(name)['jobs'][job]['if'].strip()
    github = SimpleNamespace(
        ref=f'refs/heads/{branch}', event_name=event, base_ref=base,
        repository=REPOSITORY,
        event=SimpleNamespace(
            schedule=schedule,
            pull_request=SimpleNamespace(
                head=SimpleNamespace(repo=SimpleNamespace(full_name=source)))))
    return bool(eval('(' + expression.replace('&&', ' and ').replace('||', ' or ') + ')',
                     {'__builtins__': {}},
                     {'github': github,
                      'needs': SimpleNamespace(
                          config=SimpleNamespace(outputs=SimpleNamespace(promotion_authorized=authorized)),
                          checks=SimpleNamespace(outputs=SimpleNamespace(infra_plan_enabled=authorized))),
                      'always': lambda: True}))


class DevBranchContractTests(unittest.TestCase):
    # Includes the reusable publisher's own guard; caller protection alone is
    # insufficient if another caller is introduced later.
    MUTATION_JOBS = (
        ('workflow.yml', 'build-base-images'),
        ('build-base-images.yml', 'build-push'),
        ('catalog-certification.yml', 'build-base-images'),
        ('promote-stable.yml', 'promote'),
        ('recover-stable.yml', 'recover'),
        ('infra-apply.yml', 'plan'),
        ('infra-apply.yml', 'apply'),
    )

    def test_main_and_other_branches_cannot_enter_dev_mutation_jobs(self):
        for name, job in self.MUTATION_JOBS:
            for branch in ('main', 'staging', 'feature/example'):
                for event in ('push', 'workflow_dispatch', 'schedule', 'pull_request'):
                    with self.subTest(workflow=name, job=job, branch=branch, event=event):
                        self.assertFalse(enabled(name, job, branch=branch, event=event,
                                                 schedule='23 3 * * *'))

    def test_develop_manual_operations_still_reach_their_existing_gates(self):
        for name, job in self.MUTATION_JOBS:
            with self.subTest(workflow=name, job=job):
                self.assertTrue(enabled(name, job))
        self.assertFalse(enabled('promote-stable.yml', 'promote', authorized='false'))
        self.assertFalse(enabled('promote-stable.yml', 'promote', authorized=''))

    def test_candidate_publication_requires_a_dev_producer_event(self):
        for name, job in self.MUTATION_JOBS[:2]:
            for event in ('push', 'workflow_dispatch', 'schedule'):
                with self.subTest(workflow=name, event=event):
                    self.assertTrue(enabled(name, job, event=event, schedule='23 3 * * *'))
            self.assertFalse(enabled(name, job, event='pull_request'))
            self.assertFalse(enabled(name, job, event='pull_request_target'))
        document = workflow('workflow.yml')
        self.assertEqual(events(document)['push']['branches'], ['develop'])
        self.assertNotIn('branches', events(document)['pull_request'])
        self.assertEqual(document['permissions'], {'contents': 'read'})
        for job in ('validate-pr', 'validate-pr-full'):
            self.assertEqual(document['jobs'][job]['uses'],
                             './.github/workflows/validate-base-images.yml')
            self.assertNotIn('permissions', document['jobs'][job])

    def test_catalog_app_and_recovery_keep_manual_only_authorization(self):
        for name, job in (('catalog-certification.yml', 'build-base-images'),
                          ('app-certification.yml', 'inventory'),
                          ('recover-stable.yml', 'recover')):
            with self.subTest(workflow=name):
                self.assertEqual(set(events(workflow(name))), {'workflow_dispatch'})
                self.assertTrue(enabled(name, job))
                self.assertFalse(enabled(name, job, branch='main'))
                self.assertFalse(enabled(name, job, event='push'))
                self.assertFalse(enabled(name, job, event='pull_request'))

    def test_infra_pr_backend_access_is_only_for_same_repo_develop_prs(self):
        document = workflow('infra-pr.yml')
        self.assertEqual(events(document)['pull_request']['branches'], ['develop'])
        self.assertTrue(enabled('infra-pr.yml', 'plan', event='pull_request'))
        self.assertFalse(enabled('infra-pr.yml', 'plan', event='pull_request', base='main'))
        self.assertFalse(enabled('infra-pr.yml', 'plan', event='pull_request',
                                 source='external/fork'))

    def test_schedules_keep_the_same_crons_and_target_only_dev(self):
        expected = {'workflow.yml': ('build-base-images', '23 3 * * *'),
                    'promote-stable.yml': ('promote', '17 * * * *'),
                    'pipeline-health.yml': ('health', '40 5 * * *')}
        scheduled = {path.name for path in (ROOT / '.github/workflows').glob('*.yml')
                     if 'schedule' in events(workflow(path.name))}
        self.assertEqual(scheduled, set(expected))
        for name, (job, cron) in expected.items():
            with self.subTest(workflow=name):
                self.assertEqual(events(workflow(name))['schedule'], [{'cron': cron}])
                self.assertTrue(enabled(name, job, event='schedule', schedule=cron))
                self.assertFalse(enabled(name, job, branch='main', event='schedule',
                                         schedule=cron))

    def test_generic_main_ci_still_has_no_aws_credentials_or_write_permissions(self):
        document = workflow('ci.yml')
        self.assertEqual(events(document)['push']['branches'], ['develop', 'main'])
        self.assertEqual(document['permissions'], {'contents': 'read'})
        for job in document['jobs'].values():
            self.assertNotIn('permissions', job)
            self.assertNotIn('uses', job)
            for step in job['steps']:
                self.assertNotIn('aws-actions/', step.get('uses', ''))


if __name__ == '__main__':
    unittest.main()
