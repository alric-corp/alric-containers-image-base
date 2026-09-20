import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.runtime import runtime_images, trust_plan

ROOT = Path(__file__).resolve().parents[4]


class TrustPlanTests(unittest.TestCase):
    def test_compiled_pairs_select_only_their_runtime_fixture(self):
        for runtime in ('go1-25', 'go1-26', 'java21', 'java25', 'dotnet10'):
            with self.subTest(runtime=runtime):
                self.assertEqual(trust_plan.plan(json.dumps([runtime, runtime + '-dev'])),
                                 [runtime])

    def test_python_and_node_including_dev_are_independent_fixtures(self):
        for framework in ('python3-13', 'python3-14', 'nodejs22', 'nodejs22-dev',
                          'nodejs24', 'nodejs24-dev'):
            with self.subTest(framework=framework):
                self.assertEqual(trust_plan.plan(json.dumps([framework])), [framework])
        self.assertEqual(trust_plan.plan('["nodejs22-dev", "nodejs22"]'),
                         ['nodejs22', 'nodejs22-dev'])

    def test_mixed_batch_retains_each_selected_family_without_extra_fixtures(self):
        requested = ['python3-14', 'java25-dev', 'go1-26-dev', 'nodejs24-dev',
                     'java25', 'go1-26']
        self.assertEqual(trust_plan.plan(json.dumps(requested)),
                         ['go1-26', 'java25', 'nodejs24-dev', 'python3-14'])

    def test_duplicate_and_reordered_requests_have_one_deterministic_plan(self):
        requested = ['nodejs24-dev', 'go1-26-dev', 'python3-13', 'go1-26']
        expected = ['go1-26', 'nodejs24-dev', 'python3-13']
        for batch in (requested, list(reversed(requested)), requested * 5):
            with self.subTest(batch=batch):
                self.assertEqual(trust_plan.plan(json.dumps(batch)), expected)

    def test_runtime_or_dev_without_its_compiled_pair_is_rejected(self):
        for runtime in ('go1-25', 'go1-26', 'java21', 'java25', 'dotnet10'):
            for orphan in (runtime, runtime + '-dev'):
                for requested in ([orphan], ['nodejs22', orphan]):
                    with self.subTest(requested=requested), self.assertRaises(ValueError):
                        trust_plan.plan(json.dumps(requested))

    def test_mismatched_compiled_pairs_do_not_satisfy_each_other(self):
        for requested in (['go1-25', 'go1-26-dev'], ['java21', 'java25-dev'],
                          ['dotnet10', 'go1-26', 'go1-26-dev']):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                trust_plan.plan(json.dumps(requested))

    def test_empty_malformed_unknown_and_unsafe_batches_fail(self):
        for requested in ('', 'invalid', '[', 'null', '{}', '[]', '"nodejs22"',
                          '[null]', '[true]', '[1]', '[{}]', '[[]]',
                          '["unknown"]', '["nodejs999"]', '["../nodejs22"]',
                          '["nodejs22;id"]', '["$(id)"]', '["nodejs22\\n"]',
                          '["nodejs22", "unknown"]', '["nodejs22", false]'):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                trust_plan.plan(requested)
        for requested in (None, [], {}, 1, True):
            with self.subTest(requested=requested), self.assertRaises(ValueError):
                trust_plan.plan(requested)

    def test_catalog_membership_does_not_silently_skip_an_unsupported_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'frameworks').mkdir()
            for name in ('unsupported-runtime', 'nodejs22'):
                (root / 'frameworks' / (name + '.yaml')).touch()
            with patch.object(runtime_images, 'ROOT', root):
                for requested in (['unsupported-runtime'], ['nodejs22', 'unsupported-runtime']):
                    with self.subTest(requested=requested), self.assertRaises(ValueError):
                        trust_plan.plan(json.dumps(requested))

    def test_contract_kind_drift_cannot_drop_a_requested_dev_image(self):
        with patch.object(runtime_images, 'supported', return_value='interpreted'):
            with self.assertRaisesRegex(ValueError, 'exactly the requested batch'):
                trust_plan.plan('["go1-26", "go1-26-dev"]')

    def test_project_metadata_drift_cannot_add_an_unrequested_fixture_build(self):
        changed_project = (ROOT / 'tests/runtime/projects/go', 'nodejs22', 'go version')
        with patch.object(runtime_images, 'project', return_value=changed_project):
            with self.assertRaisesRegex(ValueError, 'exactly the requested batch'):
                trust_plan.plan('["go1-26", "nodejs22"]')

    def test_full_catalog_has_eleven_fixtures_and_builds_exactly_its_sixteen_images(self):
        catalog = {path.stem for path in (ROOT / 'frameworks').glob('*.yaml') if path.is_file()}
        self.assertEqual(len(catalog), 16)
        fixtures = trust_plan.plan(json.dumps(sorted(catalog)))
        self.assertEqual(fixtures, [
            'dotnet10', 'go1-25', 'go1-26', 'java21', 'java25',
            'nodejs22', 'nodejs22-dev', 'nodejs24', 'nodejs24-dev',
            'python3-13', 'python3-14',
        ])
        self.assertTrue({'python3-13', 'nodejs22', 'go1-26', 'java21', 'dotnet10'}
                        .issubset(fixtures))
        expanded = set(fixtures)
        for fixture in fixtures:
            if runtime_images.supported(fixture) == 'compiled':
                expanded.add(fixture + '-dev')
        self.assertEqual(expanded, catalog)


class TrustPlanCliTests(unittest.TestCase):
    def run_cli(self, requested=None):
        environment = dict(os.environ)
        environment.pop('FRAMEWORKS', None)
        if requested is not None:
            environment['FRAMEWORKS'] = requested
        return subprocess.run(
            [sys.executable, '-B', '-m', 'scripts.pipeline.runtime.trust_plan'],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10)

    def test_cli_emits_only_the_sorted_json_fixture_list(self):
        result = self.run_cli('["go1-26-dev", "go1-26", "go1-26"]')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '["go1-26"]\n')
        self.assertEqual(result.stderr, '')

    def test_cli_errors_emit_no_matrix_or_untrusted_input(self):
        for requested in (None, '', '[]', '{', '[true]', '["go1-26"]',
                          '["java21-dev"]', '["unknown"]', '["$(touch injected)"]'):
            with self.subTest(requested=requested):
                result = self.run_cli(requested)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertIn('Invalid trust plan:', result.stderr)
                self.assertNotIn('$(touch injected)', result.stderr)


if __name__ == '__main__':
    unittest.main()
