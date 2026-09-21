"""Manual certification uses the production engine without widening its defaults."""
import json
from pathlib import Path
import unittest

import yaml

from scripts.pipeline.release.promotion_batch import promotion_units
from scripts.pipeline.runtime.runtime_images import plan, publication_contract
from scripts.pipeline.runtime.trust_plan import plan as trust_plan


ROOT = Path(__file__).resolve().parents[4]
FULL = ['dotnet10', 'dotnet10-dev', 'go1-25', 'go1-25-dev', 'go1-26', 'go1-26-dev',
        'java21', 'java21-dev', 'java25', 'java25-dev', 'nodejs22', 'nodejs22-dev',
        'nodejs24', 'nodejs24-dev', 'python3-13', 'python3-14']
PAIRS = [[name, name + '-dev'] for name in ('dotnet10', 'go1-25', 'go1-26', 'java21', 'java25')]
INDEPENDENT = ['nodejs22', 'nodejs22-dev', 'nodejs24', 'nodejs24-dev', 'python3-13', 'python3-14']


def workflow(name):
    return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())


def events(document):
    return document.get('on', document.get(True))


class CatalogCertificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = workflow('catalog-certification.yml')
        cls.jobs = cls.document['jobs']
        cls.job = cls.jobs['build-base-images']
        cls.requested = json.loads(cls.job['with']['frameworks'])
        cls.normal = workflow('workflow.yml')
        cls.publisher = cls.normal['jobs']['build-base-images']

    def test_manual_only_without_scope_or_bypass_inputs(self):
        self.assertEqual(self.document['name'], 'Distroless - Catalog certification')
        self.assertEqual(events(self.document), {'workflow_dispatch': {}})
        self.assertEqual(self.job['if'],
                         "github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch'")

    def test_fixed_batch_is_exact_complete_catalog_without_duplicates(self):
        self.assertEqual(self.requested, FULL)
        self.assertEqual(len(self.requested), 16)
        self.assertEqual(len(set(self.requested)), 16)
        self.assertEqual(sorted(self.requested),
                         sorted(path.stem for path in (ROOT / 'frameworks').glob('*.yaml')))

    def test_only_job_calls_real_engine_without_build_or_stable_steps(self):
        self.assertEqual(set(self.jobs), {'build-base-images'})
        self.assertEqual(set(self.job), {'if', 'concurrency', 'permissions', 'uses', 'with'})
        self.assertEqual(self.job['uses'], './.github/workflows/build-base-images.yml')
        self.assertEqual(self.job['uses'], self.publisher['uses'])
        self.assertEqual(set(self.job['with']), {'frameworks', 'aws-region', 'aws-role-arn'})
        self.assertNotIn('secrets', self.job)
        # One call with no executable steps or second release job: certification
        # has no alternative build path, stable write, or promotion call.
        self.assertNotIn('steps', self.job)

    def test_destination_and_permissions_match_existing_publisher_exactly(self):
        self.assertEqual(self.document['permissions'], {'contents': 'read'})
        self.assertEqual(self.job['permissions'], self.publisher['permissions'])
        self.assertEqual(self.job['permissions'], workflow('build-base-images.yml')['permissions'])
        for name in ('aws-region', 'aws-role-arn'):
            self.assertEqual(self.job['with'][name], self.publisher['with'][name])

    def test_candidate_publication_shares_one_non_cancelling_slot(self):
        self.assertEqual(self.job['concurrency'], self.publisher['concurrency'])
        self.assertEqual(self.job['concurrency'], {
            'group': 'factory-build-publish-${{ github.repository }}',
            'cancel-in-progress': False,
        })
        self.assertNotIn('concurrency', self.document)

    def test_all_artifacts_require_current_contracts_with_complete_compiled_pairs(self):
        compiled = set()
        for framework in self.requested:
            with self.subTest(framework=framework):
                contract = publication_contract(framework, self.requested)
                self.assertIs(contract['required'], True)
                if contract['dev_framework']:
                    pair = (contract['runtime_framework'], contract['dev_framework'])
                    self.assertTrue(set(pair) <= set(self.requested))
                    compiled.add(pair)
        self.assertEqual(compiled, {tuple(pair) for pair in PAIRS})
        expected_contracts = [pair[0] for pair in PAIRS] + INDEPENDENT
        planned, _ = plan(self.requested)
        self.assertEqual(sorted(planned), sorted(expected_contracts))
        self.assertEqual(sorted(trust_plan(json.dumps(self.requested))), sorted(expected_contracts))

    def test_production_promotion_plan_has_eleven_units_and_six_hour_minimum(self):
        self.assertEqual(promotion_units(self.requested, 6), PAIRS + [[name] for name in INDEPENDENT])
        self.assertEqual(len(promotion_units(self.requested, 6)), 11)
        with self.assertRaises(ValueError):
            promotion_units(self.requested, 0)

    def test_normal_build_and_promotion_defaults_stay_on_reference_pair(self):
        self.assertEqual(json.loads(self.publisher['with']['frameworks']), ['go1-26', 'go1-26-dev'])
        self.assertEqual(events(self.normal)['schedule'], [{'cron': '23 3 * * *'}])
        promotion = workflow('promote-stable.yml')
        dispatch = events(promotion)['workflow_dispatch']['inputs']
        self.assertEqual(json.loads(dispatch['frameworks']['default']), ['go1-26', 'go1-26-dev'])
        self.assertEqual(dispatch['soak-hours']['default'], 6)
        self.assertIn("vars.STABLE_PROMOTION_AUTHORIZED == 'true'", promotion['jobs']['promote']['if'])


if __name__ == '__main__':
    unittest.main()
