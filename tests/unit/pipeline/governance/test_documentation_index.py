"""The documentation index states the current facts that versioned sources define.

Offline: compares docs/README.md and the README summary with the catalog, the
golden-path batch, the promotion policies and the support record, and resolves
the index's relative links. Facts read from AWS stay dated in the documents.
"""
import json
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[4]
INDEX = ROOT / 'docs/README.md'
LINK = re.compile(r'\]\(([^)\s]+)\)')


def row(text, domain):
    rows = [line for line in text.splitlines() if line.startswith(f'| {domain} |')]
    if len(rows) != 1:
        raise AssertionError(f'expected one current-state row for {domain}, found {len(rows)}')
    return rows[0]


class DocumentationIndexTests(unittest.TestCase):
    def setUp(self):
        self.text = INDEX.read_text(encoding='utf-8')
        self.current = self.text.split('## Estado atual', 1)[1].split('\n## ', 1)[0]

    def test_current_state_comes_first_and_history_last(self):
        headings = [line for line in self.text.splitlines() if line.startswith('## ')]
        self.assertEqual(headings[0], '## Estado atual')
        self.assertEqual(headings[-1], '## Histórico')

    def test_catalog_count_and_golden_path_match_the_sources(self):
        count = len(list((ROOT / 'frameworks').glob('*.yaml')))
        self.assertIn(f'{count} definições', row(self.current, 'Catálogo'))
        self.assertIn(f'**{count} definições**', (ROOT / 'README.md').read_text(encoding='utf-8').splitlines()[2])
        scope = json.loads((ROOT / 'policies/operations/health.json').read_text())['execution_scope']['current']
        workflow = yaml.safe_load((ROOT / '.github/workflows/workflow.yml').read_text())
        automatic = json.loads(workflow['jobs']['build-base-images']['with']['frameworks'])
        self.assertEqual(sorted(automatic), sorted(scope))
        self.assertIn('/'.join(f'`{name}`' for name in sorted(automatic)), row(self.current, 'Catálogo'))

    def test_hom_row_follows_the_promotion_policy(self):
        enabled = json.loads((ROOT / 'policies/pipeline/promote-hom.json').read_text())['enabled']
        hom = row(self.current, 'HOM')
        self.assertEqual('desabilitada' in hom and '`"enabled": false`' in hom, enabled is False)

    def test_support_row_names_every_variant_without_upstream_support(self):
        variants = json.loads((ROOT / 'policies/governance/catalog-support.json').read_text())['variants']
        unsupported = sorted(name for name, item in variants.items() if item['status'] != 'SUPPORTED')
        support = row(self.current, 'Suporte')
        for name in unsupported:
            with self.subTest(variant=name):
                self.assertIn(f'`{name}`', support)

    def test_index_links_resolve(self):
        for target in LINK.findall(self.text):
            if re.match(r'^(https?|mailto):', target):
                continue
            with self.subTest(target=target):
                self.assertTrue((INDEX.parent / target.split('#')[0]).resolve().exists())


if __name__ == '__main__':
    unittest.main()
