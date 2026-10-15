"""The active ECR retention contract follows the lifecycle that Terraform applies.

Offline: reads versioned files only. The 30-day model of 2026-09-10 stays a
historical record; no Terraform, script or workflow may load it again.
"""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[4]
EFFECTIVE = ROOT / 'infra/ecr/policies/ecr-lifecycle-7-days.json'
HISTORICAL = 'operations/ecr-lifecycle.json'
CONTRACT = ROOT / 'docs/ecr-retention.md'
LABEL = re.compile(r'hist[óo]ric|modelo anterior|não aplicad|not applied', re.IGNORECASE)


class RetentionDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.text = CONTRACT.read_text(encoding='utf-8')
        self.rules = sorted(json.loads(EFFECTIVE.read_text())['rules'], key=lambda r: r['rulePriority'])

    def test_terraform_loads_only_the_effective_lifecycle(self):
        self.assertIn('file("${path.module}/policies/ecr-lifecycle-7-days.json")',
                      (ROOT / 'infra/ecr/locals.tf').read_text())
        executable = [path for pattern in ('infra/**/*.tf', 'infra/**/*.py', 'scripts/**/*.py',
                                           'scripts/**/*.sh', '.github/workflows/*.yml', 'Makefile')
                      for path in ROOT.glob(pattern) if path.is_file()]
        self.assertTrue(executable)
        for path in executable:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertNotIn(HISTORICAL, path.read_text(encoding='utf-8'))

    def test_contract_states_the_effective_rules(self):
        protect, expire = self.rules
        self.assertEqual(protect['selection']['tagPatternList'], ['stable'])
        self.assertEqual((expire['selection']['countType'], expire['selection']['countUnit']),
                         ('sinceImagePushed', 'days'))
        self.assertIn('[`infra/ecr/policies/ecr-lifecycle-7-days.json`]', self.text)
        self.assertIn(f"Expira {expire['selection']['countNumber']} dias após o push.", self.text)
        self.assertIn('Imagens com a tag `stable`, contagem acima de '
                      f"{protect['selection']['countNumber']}", self.text)
        untagged = any(rule['selection']['tagStatus'] == 'untagged' for rule in self.rules)
        self.assertEqual('| — | Imagens sem tag | Nenhuma regra. |' in self.text, not untagged)

    def test_contract_separates_environments(self):
        for heading in ('## Regras efetivas em DEV', '## HOM', '## Ambiente corporativo',
                        '## Histórico, não aplicado'):
            with self.subTest(heading=heading):
                self.assertEqual(self.text.splitlines().count(heading), 1)

    def test_historical_model_is_labeled_wherever_an_active_document_cites_it(self):
        # TODO/ holds planning material, not active contracts.
        documents = [path for path in ROOT.glob('**/*.md')
                     if '.venv' not in path.parts and path.relative_to(ROOT).parts[0] != 'TODO']
        cited = 0
        for path in documents:
            for block in re.split(r'\n\s*\n', path.read_text(encoding='utf-8')):
                if HISTORICAL in block:
                    cited += 1
                    with self.subTest(document=str(path.relative_to(ROOT)), block=block[:80]):
                        self.assertRegex(block, LABEL)
        self.assertGreater(cited, 0)


if __name__ == '__main__':
    unittest.main()
