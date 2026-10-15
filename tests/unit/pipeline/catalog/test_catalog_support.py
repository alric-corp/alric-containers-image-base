"""Support status per catalog variant stays complete and bound to the definitions.

Offline: reads policies/governance/catalog-support.json, frameworks/*.yaml and
the consumer pairs. Status records a fact and a pending decision; it does not
enable or block build, publication or promotion.
"""
from datetime import date
import json
from pathlib import Path
import re
import unittest

import yaml

from scripts.pipeline.consumer_apps.model import CATALOG, SCENARIOS

ROOT = Path(__file__).resolve().parents[4]
SUPPORT = ROOT / 'policies/governance/catalog-support.json'
DOCUMENT = ROOT / 'docs/catalog-support.md'
FIELDS = {'family', 'series', 'role', 'package', 'status', 'upstream', 'evidence', 'decision',
          'migration_target'}
STATUSES = {'SUPPORTED', 'UPSTREAM_EOL'}
DECISIONS = {None, 'AWAITING_OWNER_APPROVAL'}


def unique(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f'duplicate key: {key}')
        document[key] = value
    return document


class CatalogSupportTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(SUPPORT.read_text(encoding='utf-8'), object_pairs_hook=unique)
        self.variants = self.policy['variants']

    def definition(self, name):
        return yaml.safe_load((ROOT / 'frameworks' / f'{name}.yaml').read_text(encoding='utf-8'))

    def test_every_catalog_definition_has_exactly_one_status(self):
        definitions = sorted(path.stem for path in (ROOT / 'frameworks').glob('*.yaml'))
        self.assertEqual(sorted(self.variants), definitions)
        self.assertEqual(sorted(self.variants), sorted(CATALOG))

    def test_document_shape_owner_and_review_dates(self):
        self.assertEqual(set(self.policy), {'$comment', 'schema_version', 'owner', 'reviewed_at',
                                            'review_by', 'variants'})
        self.assertEqual(self.policy['schema_version'], 1)
        self.assertTrue(self.policy['owner'].strip())
        reviewed, review_by = (date.fromisoformat(self.policy[key]) for key in ('reviewed_at', 'review_by'))
        self.assertLess(reviewed, review_by)
        for name, item in self.variants.items():
            with self.subTest(variant=name):
                self.assertEqual(set(item), FIELDS)
                self.assertIn(item['status'], STATUSES)
                self.assertIn(item['decision'], DECISIONS)
                self.assertEqual(item['role'], 'dev' if name.endswith('-dev') else 'runtime')
                self.assertRegex(item['upstream'], r'^https://[^\s]+$')
                self.assertRegex(item['evidence'], r'\d{4}-\d{2}-\d{2}')

    def test_declared_package_is_the_one_the_definition_installs(self):
        for name, item in self.variants.items():
            with self.subTest(variant=name):
                packages = (self.definition(name).get('contents') or {}).get('packages') or []
                if item['package'] is None:
                    self.assertEqual(packages, [])
                else:
                    self.assertIn(item['package'], packages)
                if item['role'] == 'dev':
                    self.assertIsNotNone(item['package'])

    def test_runtime_and_dev_pairs_share_series_status_and_decision(self):
        for scenario in SCENARIOS:
            pair = [scenario['framework']] + ([scenario['dev_framework']] if scenario['dev_framework'] else [])
            first = self.variants[pair[0]]
            self.assertEqual(first['series'], scenario['expected_version'])
            for name in pair[1:]:
                with self.subTest(pair=pair):
                    for key in ('family', 'series', 'status', 'decision'):
                        self.assertEqual(self.variants[name][key], first[key], key)

    def test_unsupported_variant_has_a_pending_decision_and_a_supported_target(self):
        for name, item in self.variants.items():
            with self.subTest(variant=name):
                if item['status'] == 'SUPPORTED':
                    self.assertIsNone(item['decision'])
                    self.assertIsNone(item['migration_target'])
                    continue
                self.assertIsNotNone(item['decision'])
                target = self.variants[item['migration_target']]
                self.assertEqual(target['status'], 'SUPPORTED')
                self.assertEqual((target['family'], target['role']), (item['family'], item['role']))

    def test_go_1_25_records_the_upstream_end_and_a_pending_owner_decision(self):
        for name, target in (('go1-25', 'go1-26'), ('go1-25-dev', 'go1-26-dev')):
            with self.subTest(variant=name):
                item = self.variants[name]
                self.assertEqual((item['status'], item['decision'], item['migration_target']),
                                 ('UPSTREAM_EOL', 'AWAITING_OWNER_APPROVAL', target))

    def test_document_lists_every_variant_with_its_status(self):
        text = DOCUMENT.read_text(encoding='utf-8')
        for name, item in self.variants.items():
            with self.subTest(variant=name):
                rows = [line for line in text.splitlines() if line.startswith(f'| `{name}` |')]
                self.assertEqual(len(rows), 1)
                self.assertIn(f'| {item["status"]} |', rows[0])
        self.assertIn('G04_SUPPORT_DECISION=AWAITING_OWNER_APPROVAL', text)
        self.assertTrue(re.search(r'\[`policies/governance/catalog-support\.json`\]', text))


if __name__ == '__main__':
    unittest.main()
