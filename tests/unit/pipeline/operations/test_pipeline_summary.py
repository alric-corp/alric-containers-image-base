import json
from pathlib import Path
import tempfile
import unittest

from scripts.pipeline.operations import pipeline_summary as summary


def write(directory, name, payload):
    path = Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


class ArtifactNameTests(unittest.TestCase):
    def test_framework_names_with_dashes_survive_the_parsing(self):
        self.assertEqual(summary.artifact_name('build-scans-go1-26-dev-1'),
                         ('build-scans', 'go1-26-dev'))
        self.assertEqual(summary.artifact_name('promotion-scans-nodejs22-3'),
                         ('promotion-scans', 'nodejs22'))
        # `promotion-scans-` não pode ser lido como `promotion-` de um
        # framework chamado `scans`.
        self.assertEqual(summary.artifact_name('promotion-nodejs22-1'),
                         ('promotion', 'nodejs22'))
        self.assertEqual(summary.artifact_name('validated-oci-go1-26'), (None, None))


class ScanResultTests(unittest.TestCase):
    def test_infrastructure_error_is_never_reported_as_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'evidence-amd64.json', {'exit_code': 0, 'index_digest': 'sha256:a'})
            write(directory, 'trivy-amd64.json', {'Results': []})
            # Trivy usa 1 para achados; 2 é falha de execução do scanner.
            write(directory, 'evidence-arm64.json', {'exit_code': 2})
            result = summary.scan_result(Path(directory))
        self.assertEqual(result['status'], 'erro de infraestrutura')
        self.assertIn('trivy terminou com 2', result['reason'])
        self.assertEqual(result['platforms']['amd64']['status'], 'aprovado')

    def test_blocked_counts_only_findings_with_an_available_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            for arch in ('amd64', 'arm64'):
                write(directory, f'evidence-{arch}.json', {'exit_code': 1})
                write(directory, f'trivy-{arch}.json',
                      {'Results': [{'Vulnerabilities': [{'VulnerabilityID': 'CVE-1'},
                                                        {'VulnerabilityID': 'CVE-2'}],
                                    'Secrets': [{'RuleID': 'aws-access-key'}]}]})
            result = summary.scan_result(Path(directory))
        self.assertEqual(result['status'], 'bloqueado')
        self.assertIn('2 CVE(s) com correção e 1 secret(s)', result['reason'])

    def test_missing_scan_evidence_is_a_gap_not_a_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = summary.scan_result(Path(directory))
        self.assertEqual(result['status'], 'erro de infraestrutura')
        self.assertEqual(summary.scan_result(None)['status'], summary.MISSING)


class RowTests(unittest.TestCase):
    def test_runtime_records_native_and_emulated_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'runtime-nodejs22-amd64.json',
                  {'status': 'passed', 'execution': 'emulated', 'contract': 'interpreted'})
            write(directory, 'runtime-nodejs22-arm64.json',
                  {'status': 'failed', 'execution': 'native', 'error': 'bad TLS'})
            result = summary.runtime_result(Path(directory), 'nodejs22')
        self.assertEqual(result['status'], 'reprovado')
        self.assertEqual(result['platforms']['amd64']['execution'], 'emulated')
        self.assertEqual(result['platforms']['arm64']['execution'], 'native')
        self.assertIn('bad TLS', result['reason'])

    def test_promotion_distinguishes_promoted_from_skipped_with_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            write(directory, 'promotion-evidence.json',
                  {'promoted': False, 'reason': 'nenhum build novo completou o soak',
                   'stable_age_hours': 12.5})
            skipped = summary.promotion_result(Path(directory))
            write(directory, 'promotion-evidence.json',
                  {'promoted': True, 'digest': 'sha256:b', 'tag': '100926-0000'})
            promoted = summary.promotion_result(Path(directory))
        self.assertEqual(skipped['status'], 'não promovido')
        self.assertIn('soak', skipped['reason'])
        self.assertEqual(skipped['stable_age_hours'], 12.5)
        self.assertEqual(promoted['status'], 'promovido')


class CollectTests(unittest.TestCase):
    def test_framework_without_any_evidence_still_has_a_row(self):
        with tempfile.TemporaryDirectory() as directory:
            collected = summary.collect(directory, ['nodejs22', 'nodejs24'])
        self.assertEqual(set(collected['frameworks']), {'nodejs22', 'nodejs24'})
        self.assertEqual(collected['totals']['without_evidence'], 2)

    def test_promotion_table_does_not_borrow_the_build_batch_reason(self):
        # Num run de promoção nenhum contrato roda: repetir o motivo do lote de
        # build ali seria enganoso.
        with tempfile.TemporaryDirectory() as directory:
            collected = summary.collect(directory, ['go1-26'])
        self.assertEqual(collected['frameworks']['go1-26']['runtime']['status'], summary.MISSING)

    def test_contract_not_planned_for_this_batch_shows_the_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            # go1-26 sem o par -dev no lote: o contrato compilado não roda, e o
            # motivo tem de aparecer em vez de a coluna ficar vazia.
            collected = summary.collect(directory, ['go1-26'], annotate_plan=True)
        self.assertEqual(collected['frameworks']['go1-26']['runtime']['status'], 'não executado')
        self.assertIn('go1-26-dev', collected['frameworks']['go1-26']['runtime']['reason'])

    def test_rendered_table_has_one_row_per_framework_and_direct_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / 'build-scans-nodejs22-1', 'evidence-amd64.json',
                  {'exit_code': 0, 'index_digest': 'sha256:' + 'a' * 64})
            write(root / 'build-scans-nodejs22-1', 'evidence-arm64.json',
                  {'exit_code': 0, 'index_digest': 'sha256:' + 'a' * 64})
            write(root / 'build-scans-nodejs22-1', 'unfixed-cves-summary.json',
                  {'architectures': {'amd64': [{'id': 'CVE-9'}], 'arm64': []}})
            write(root / 'publication-nodejs22-1', 'publication-evidence.json',
                  {'remote_digest': 'sha256:' + 'a' * 64,
                   'image_ref': 'registry/image-base-nodejs22@sha256:' + 'a' * 64,
                   'platforms': {'linux/amd64': 'x', 'linux/arm64': 'y'}})
            collected = summary.collect(root, ['nodejs22'])
            markdown = summary.render(collected, 'owner/repo', '42',
                                      {'build-scans-nodejs22-1': 7})
        rows = [line for line in markdown.splitlines() if line.startswith('| `')]
        self.assertEqual(len(rows), 1)
        self.assertIn('publicado', rows[0])
        self.assertIn('amd64: 1 / arm64: 0', rows[0])
        self.assertIn('actions/runs/42/artifacts/7', rows[0])
        self.assertEqual(collected['totals']['published'], 1)


if __name__ == '__main__':
    unittest.main()
