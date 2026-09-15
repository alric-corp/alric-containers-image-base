"""Guards for the temporary, exact P0-04 execution scope."""

import json
from pathlib import Path
import unittest

import yaml

from scripts.pipeline.catalog import default_batch
from scripts.pipeline.runtime import runtime_images


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / '.github/workflows/workflow.yml'
P0_04 = ['go1-26', 'go1-26-dev']


class P0_04ExecutionScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(WORKFLOW.read_text())
        cls.jobs = cls.document['jobs']

    def test_build_and_pr_selection_is_exact(self):
        self.assertEqual(
            json.loads(self.jobs['validate-pr']['with']['frameworks']), P0_04)
        self.assertEqual(
            self.jobs['build-base-images']['with']['frameworks'],
                         '["go1-26", "go1-26-dev"]')

    def test_promotion_caller_uses_the_same_exact_profile(self):
        self.assertEqual(
            json.loads(self.jobs['promote-stable']['with']['frameworks']), P0_04)
        promotion = yaml.safe_load((ROOT / '.github/workflows/promote-stable.yml').read_text())
        triggers = promotion.get('on') or promotion.get(True)
        self.assertTrue(triggers['workflow_call']['inputs']['frameworks']['required'])

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


if __name__ == '__main__':
    unittest.main()
