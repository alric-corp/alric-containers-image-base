import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

from scripts.pipeline.catalog import default_batch as batch

ROOT = pathlib.Path(__file__).resolve().parents[4]
# 'sample-runtime' é um nome de framework sintético, sem correspondência com
# nenhum framework real (histórico ou atual): estes testes exercitam o
# mecanismo de exclusão em si, não um caso real. O `adr` aponta para um ADR
# real e válido só para testar a checagem de caminho/arquivo; ADR-0002 é
# usado por não ter relação nenhuma com a razão de exclusão sintética abaixo.
CATALOG = {'go1-26', 'go1-26-dev', 'nodejs22', 'sample-runtime'}
EXCLUSION = {'reason': 'motivo de teste', 'owner': '@owner',
             'review_by': '2026-10-09', 'adr': 'docs/adr/0002-sigstore-trust-model.md'}


def dispatch_form(names):
    """A única expressão aceita em build-base-images: input do dispatch ou o literal."""
    return batch.DISPATCH_PREFIX + json.dumps(names) + batch.DISPATCH_SUFFIX


def workflow(*batches):
    """workflow.yml mínimo com um lote por job, na mesma forma do real."""
    validate, build, promote = batches
    return {'jobs': {
        'validate-pr': {'with': {'frameworks': json.dumps(validate)}},
        'build-base-images': {'with': {'frameworks': dispatch_form(build)}},
        'promote-stable': {'with': {'frameworks': json.dumps(promote), 'soak-hours': 6}},
    }}


def run_cli(*args, cwd=ROOT):
    return subprocess.run([sys.executable, '-B', '-m', 'scripts.pipeline.catalog.default_batch', *args],
                          cwd=cwd, capture_output=True, text=True,
                          env={'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'})


class RealTreeTests(unittest.TestCase):
    """O estado versionado é o primeiro caso de aceite (A01/A02).

    dotnet8 foi removido do catálogo em 17/09/2026 (fim de suporte LTS em
    11/2026; ver docs/adr/0001-dotnet8-fora-do-lote-padrao.md, adendo, e
    docs/adr/0007-multi-source-alpine-recusado.md): a árvore real não tem
    mais nenhuma exceção registrada, e os três lotes são o catálogo inteiro.
    """

    def test_the_three_batches_are_the_catalog_with_no_exclusions(self):
        names, policy, document = batch.load()
        excluded, problems = batch.exclusions(policy)
        self.assertEqual(problems, [])
        self.assertEqual(excluded, {})
        found = batch.batches(document)
        self.assertEqual(batch.lint(names, excluded, found), [])
        expected = batch.expected_batch(names, excluded)
        self.assertEqual(expected, names)
        for job_id in batch.BATCH_JOBS:
            names_in_job, problem = batch.parse_batch(job_id, found[job_id])
            self.assertIsNone(problem)
            expected_for_job = (batch.P0_04_BATCH
                                if found[job_id] == json.dumps(batch.P0_04_BATCH)
                                else expected)
            self.assertEqual(sorted(names_in_job), sorted(expected_for_job), job_id)

    def test_the_cli_lint_and_list_agree_with_the_tree(self):
        lint = run_cli('lint')
        self.assertEqual(lint.returncode, 0, lint.stderr)
        listing = run_cli('list')
        self.assertEqual(listing.returncode, 0, listing.stderr)
        report = json.loads(listing.stdout)
        self.assertEqual(report['excluded'], [])
        self.assertEqual(report['problems'], [])
        self.assertEqual(len(report['default_batch']), len(report['catalog']))


class LintTests(unittest.TestCase):
    EXCLUDED = {'sample-runtime': EXCLUSION}
    BATCH = ['go1-26', 'go1-26-dev', 'nodejs22']

    def lint(self, *batches, excluded=None):
        found = batch.batches(workflow(*batches))
        return batch.lint(sorted(CATALOG), self.EXCLUDED if excluded is None else excluded, found)

    def test_catalog_minus_exclusions_passes_in_any_order(self):
        self.assertEqual(self.lint(self.BATCH, list(reversed(self.BATCH)), self.BATCH), [])

    def test_p0_profile_is_valid_for_promotion_during_rollout(self):
        # O caller de promoção pode usar o perfil P0-04 sem registrar
        # frameworks ausentes como exceptions do catálogo.
        self.assertEqual(self.lint(self.BATCH, self.BATCH, batch.P0_04_BATCH), [])

    def test_excluded_framework_present_in_the_batches_is_one_problem_per_job(self):
        # N02: framework excluído aparecendo nos três lotes mesmo assim.
        old = self.BATCH + ['sample-runtime']
        problems = self.lint(old, old, old)
        self.assertEqual(len(problems), 3)
        for job_id, problem in zip(batch.BATCH_JOBS, problems):
            self.assertIn(f'`{job_id}`', problem)
            self.assertIn('fora do lote padrão', problem)
            self.assertIn(EXCLUSION['adr'], problem)

    def test_unknown_and_duplicated_names_are_rejected(self):
        # N03
        problems = self.lint(self.BATCH + ['python3-99'], self.BATCH, self.BATCH + ['nodejs22'])
        self.assertTrue(any('`python3-99` não existe no catálogo' in p for p in problems))
        self.assertTrue(any('`nodejs22` repetido' in p for p in problems))
        self.assertEqual(len(problems), 2)

    def test_exclusion_outside_the_catalog_is_a_problem(self):
        problems = self.lint(self.BATCH, self.BATCH, self.BATCH,
                             excluded={'sample-runtime': EXCLUSION, 'ruby3': EXCLUSION})
        self.assertEqual(problems, ['exceção `ruby3` não existe no catálogo'])

    def test_unreadable_batch_is_reported_not_ignored(self):
        document = workflow(self.BATCH, self.BATCH, self.BATCH)
        document['jobs']['promote-stable']['with']['frameworks'] = 'not json'
        del document['jobs']['validate-pr']['with']
        found = batch.batches(document)
        self.assertEqual(found['promote-stable'], 'not json')
        self.assertIsNone(found['validate-pr'])
        problems = batch.lint(sorted(CATALOG), self.EXCLUDED, found)
        self.assertEqual(len(problems), 2)
        self.assertIn('`validate-pr`: `with.frameworks` ausente', problems[0])
        self.assertIn('`promote-stable`: `frameworks` fora da forma canônica (`not json`)', problems[1])

    def test_without_exclusions_the_batch_is_the_whole_catalog(self):
        # N05: `exceptions` ausente ou null tem comportamento definido.
        for policy in ({}, {'exceptions': None}):
            with self.subTest(policy=policy):
                excluded, problems = batch.exclusions(policy)
                self.assertEqual((excluded, problems), ({}, []))
                full = sorted(CATALOG)
                self.assertEqual(self.lint(full, full, full, excluded=excluded), [])


class BatchFormTests(unittest.TestCase):
    """N07: o lote automático é o literal canônico, nunca uma expressão externa."""
    BATCH = ['go1-26', 'go1-26-dev', 'nodejs22']
    LITERAL = json.dumps(BATCH)
    DYNAMIC = (
        "${{ vars.DEFAULT_FRAMEWORKS || '" + LITERAL + "' }}",       # exemplo do reviewer
        "${{ toJSON(fromJSON(vars.DEFAULT_FRAMEWORKS)) }}",
        "${{ env.DEFAULT_FRAMEWORKS }}",
        "${{ secrets.DEFAULT_FRAMEWORKS }}",
        "${{ inputs.frameworks }}",
        "${{ inputs.frameworks || '" + LITERAL + "' }}",              # sem a guarda de evento
        "${{ format('{0}', '" + LITERAL + "') }}",
        "${{ github.event_name == 'workflow_dispatch' && inputs.frameworks || '" + LITERAL
        + "' || vars.X }}",                                            # fallback extra
        LITERAL + " ${{ vars.EXTRA }}",                                # concatenação
        "${{ '" + LITERAL + "' }}",                                    # literal dentro de expressão
    )

    def test_the_canonical_forms_parse_and_tolerate_spacing_inside_the_literal(self):
        spaced = '[ "go1-26" ,"go1-26-dev",  "nodejs22" ]'
        for job_id in ('validate-pr', 'promote-stable'):
            self.assertEqual(batch.parse_batch(job_id, spaced), (self.BATCH, None), job_id)
        self.assertEqual(batch.parse_batch('build-base-images', dispatch_form(self.BATCH)),
                         (self.BATCH, None))
        self.assertEqual(batch.parse_batch('validate-pr', '[]'), ([], None))

    def test_dynamic_expressions_are_rejected_in_every_job_with_the_reason(self):
        for job_id in batch.BATCH_JOBS:
            for raw in self.DYNAMIC + (dispatch_form(self.BATCH) + ' ',):
                with self.subTest(job=job_id, raw=raw):
                    names, problem = batch.parse_batch(job_id, raw)
                    self.assertIsNone(names)
                    self.assertIn(f'`{job_id}`', problem)
                    self.assertIn('fora da forma canônica', problem)
                    self.assertIn('precisa ser estático', problem)
                    self.assertIn('fonte externa', problem)

    def test_each_job_accepts_only_its_own_form(self):
        # O literal puro perde o input do dispatch; a expressão do dispatch não
        # pertence aos jobs de PR e promoção. Nenhum dos dois é aceito no outro.
        self.assertIsNone(batch.parse_batch('build-base-images', self.LITERAL)[0])
        for job_id in ('validate-pr', 'promote-stable'):
            self.assertIsNone(batch.parse_batch(job_id, dispatch_form(self.BATCH))[0])

    def test_values_that_are_not_a_json_list_of_catalog_shaped_names_are_rejected(self):
        for raw in (None, ['go1-26'], 42, '"go1-26"', '["Go1-26"]', '["go1-26", 1]',
                    '{"frameworks": []}', '["go1-26"]\n', "['go1-26']"):
            with self.subTest(raw=raw):
                names, problem = batch.parse_batch('validate-pr', raw)
                self.assertIsNone(names)
                self.assertIn('`validate-pr`', problem)

    def test_lint_reports_the_form_problem_once_and_checks_the_other_jobs(self):
        document = workflow(self.BATCH, self.BATCH, self.BATCH)
        document['jobs']['build-base-images']['with']['frameworks'] = self.DYNAMIC[0]
        problems = batch.lint(sorted(CATALOG), {'sample-runtime': EXCLUSION}, batch.batches(document))
        self.assertEqual(len(problems), 1)
        self.assertIn('`build-base-images`', problems[0])
        self.assertIn('vars.DEFAULT_FRAMEWORKS', problems[0])


class AdrTests(unittest.TestCase):
    """N08: `adr` é um ADR do repositório em docs/adr/, e nada mais."""
    REJECTED_PATHS = ('README.md', '/etc/hosts', '../algum-arquivo.md',
                      'docs/adr/../../README.md', 'docs/adr/README.md', 'docs/adr/',
                      'docs/adr/sub/0001-x.md', 'docs/adr/0001-Example.md',
                      'docs/adr/0001-example-decision.md/', 'docs/adr/1-x.md',
                      './docs/adr/0001-example-decision.md',
                      '/docs/adr/0001-example-decision.md',
                      'docs\\adr\\0001-example-decision.md')

    def test_the_versioned_adr_is_accepted(self):
        self.assertIsNone(batch.adr_problem('docs/adr/0002-sigstore-trust-model.md'))

    def test_paths_outside_the_convention_are_rejected_before_touching_the_disk(self):
        for adr in self.REJECTED_PATHS:
            with self.subTest(adr=adr):
                problem = batch.adr_problem(adr, root=pathlib.Path('/nonexistent'))
                self.assertIn('precisa ser um caminho relativo `docs/adr/NNNN-titulo.md`', problem)

    def test_missing_symlinked_or_untitled_adr_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / 'docs/adr').mkdir(parents=True)
            (root / 'docs/adr/0002-sem-titulo.md').write_text('# Decisão\n')
            (root / 'docs/adr/0003-numero-errado.md').write_text('# ADR-0004 — x\n')
            (root / 'docs/adr/0004-link.md').symlink_to(ROOT / 'README.md')
            (root / 'docs/adr/0005-valido.md').write_text('# ADR-0005 — decisão\n\n## Contexto\n')
            self.assertIsNone(batch.adr_problem('docs/adr/0005-valido.md', root))
            self.assertIn('não existe', batch.adr_problem('docs/adr/0001-inexistente.md', root))
            self.assertIn('`docs/adr/0004-link.md` é link simbólico',
                          batch.adr_problem('docs/adr/0004-link.md', root))
            for adr, title in (('docs/adr/0002-sem-titulo.md', '# ADR-0002 '),
                               ('docs/adr/0003-numero-errado.md', '# ADR-0003 ')):
                with self.subTest(adr=adr):
                    problem = batch.adr_problem(adr, root)
                    self.assertIn(f'precisa começar com o título `{title}…`', problem)

    def test_symlinked_ancestors_cannot_move_docs_adr_outside_the_repository(self):
        # Finding remanescente da 2ª revisão: o arquivo final não é link, mas
        # `docs/adr` (ou `docs`) aponta para fora do repositório — is_file()
        # era verdadeiro e o ADR aceito vinha de fora.
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            external = base / 'external'
            for target in (external / 'adr', external / 'docs/adr'):
                target.mkdir(parents=True)
                (target / '0001-test.md').write_text('# ADR-0001 — externo\n')
            repo_adr = base / 'repo-adr'
            (repo_adr / 'docs').mkdir(parents=True)
            (repo_adr / 'docs/adr').symlink_to(external / 'adr')
            repo_docs = base / 'repo-docs'
            repo_docs.mkdir()
            (repo_docs / 'docs').symlink_to(external / 'docs')
            for root, component in ((repo_adr, 'docs/adr'), (repo_docs, 'docs')):
                with self.subTest(component=component):
                    path = root / 'docs/adr/0001-test.md'
                    self.assertTrue(path.is_file() and not path.is_symlink())  # o bypass reportado
                    problem = batch.adr_problem('docs/adr/0001-test.md', root)
                    self.assertIn(f'`{component}` é link simbólico', problem)
                    policy = {'exceptions': {'sample-runtime': dict(EXCLUSION, adr='docs/adr/0001-test.md')}}
                    self.assertEqual(len(batch.exclusions(policy, root=root)[1]), 1)
            # Link intermediário dentro de docs/adr: cai na regra textual
            # (subdiretório), antes de qualquer acesso ao disco.
            repo_link = base / 'repo-link'
            (repo_link / 'docs/adr').mkdir(parents=True)
            (repo_link / 'docs/adr/link').symlink_to(external / 'adr')
            self.assertTrue((repo_link / 'docs/adr/link/0001-test.md').is_file())
            self.assertIn('precisa ser um caminho relativo',
                          batch.adr_problem('docs/adr/link/0001-test.md', repo_link))

    def test_a_symlinked_repository_root_is_canonicalised_not_rejected(self):
        # Só a raiz é canonizada (ex.: /tmp -> /private/tmp no macOS); os
        # componentes abaixo dela continuam tendo de ser reais.
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            real = base / 'real'
            (real / 'docs/adr').mkdir(parents=True)
            (real / 'docs/adr/0005-valido.md').write_text('# ADR-0005 — decisão\n')
            (base / 'alias').symlink_to(real)
            self.assertIsNone(batch.adr_problem('docs/adr/0005-valido.md', base / 'alias'))
            self.assertIn('não resolve', batch.adr_problem('docs/adr/0005-valido.md', base / 'nao-existe'))

    def test_exclusions_report_the_adr_problem_per_entry(self):
        policy = {'exceptions': {'sample-runtime': dict(EXCLUSION, adr='README.md')}}
        excluded, problems = batch.exclusions(policy)
        self.assertEqual(sorted(excluded), ['sample-runtime'])
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith('exceção `sample-runtime`: ADR `README.md` precisa ser'))


class ExclusionFieldTests(unittest.TestCase):
    def problems(self, entry):
        return batch.exclusions({'exceptions': {'sample-runtime': entry}})[1]

    def test_each_missing_field_is_reported(self):
        # N04
        for field in batch.REQUIRED_FIELDS:
            with self.subTest(field=field):
                entry = dict(EXCLUSION)
                del entry[field]
                problems = self.problems(entry)
                self.assertEqual(problems, [f'exceção `sample-runtime` sem `{field}`'])
        for blank in ('', '   ', None, 3):
            with self.subTest(blank=blank):
                self.assertEqual(self.problems(dict(EXCLUSION, owner=blank)),
                                 ['exceção `sample-runtime` sem `owner`'])

    def test_review_by_must_be_an_iso_date(self):
        for review in ('2026-13-40', '09/10/2026', '2026-10', 'soon'):
            with self.subTest(review=review):
                problems = self.problems(dict(EXCLUSION, review_by=review))
                self.assertEqual(len(problems), 1)
                self.assertIn('não é data ISO', problems[0])

    def test_adr_must_exist_in_the_repository(self):
        problems = self.problems(dict(EXCLUSION, adr='docs/adr/9999-inexistente.md'))
        self.assertEqual(problems, ['exceção `sample-runtime`: ADR `docs/adr/9999-inexistente.md` '
                                    'não existe no repositório como arquivo regular'])

    def test_non_object_entries_are_rejected_because_health_iterates_them(self):
        excluded, problems = batch.exclusions({'exceptions': {'$comment': 'x', 'sample-runtime': EXCLUSION}})
        self.assertEqual(sorted(excluded), ['sample-runtime'])
        self.assertEqual(len(problems), 1)
        self.assertIn('`$comment` precisa ser um objeto', problems[0])
        excluded, problems = batch.exclusions({'exceptions': ['sample-runtime']})
        self.assertEqual(excluded, {})
        self.assertEqual(len(problems), 1)


class CliTests(unittest.TestCase):
    BATCH = ['go1-26', 'go1-26-dev', 'nodejs22']

    def tree(self, root, document, policy=None):
        (root / 'frameworks').mkdir()
        for name in CATALOG:
            (root / 'frameworks' / f'{name}.yaml').write_text('contents: {}\n')
        (root / 'health.json').write_text(json.dumps(policy or {'exceptions': {'sample-runtime': EXCLUSION}}))
        (root / 'workflow.yml').write_text(yaml.safe_dump(document))
        return ('--policy', str(root / 'health.json'), '--workflow', str(root / 'workflow.yml'),
                '--catalog', str(root / 'frameworks'))

    def test_lint_fails_on_a_tree_where_the_batch_diverges(self):
        with tempfile.TemporaryDirectory() as temporary:
            old = self.BATCH + ['sample-runtime']
            result = run_cli('lint', *self.tree(pathlib.Path(temporary), workflow(old, old, old)))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count('::error::'), 3)
            self.assertIn('`sample-runtime` está fora do lote padrão', result.stderr)

    def test_lint_fails_when_a_variable_can_replace_the_batch(self):
        # N07, exemplo do reviewer: o literal está certo, mas `vars.*` mandaria.
        with tempfile.TemporaryDirectory() as temporary:
            document = workflow(self.BATCH, self.BATCH, self.BATCH)
            document['jobs']['build-base-images']['with']['frameworks'] = (
                "${{ vars.DEFAULT_FRAMEWORKS || '" + json.dumps(self.BATCH) + "' }}")
            result = run_cli('lint', *self.tree(pathlib.Path(temporary), document))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stderr.count('::error::'), 1)
            self.assertIn('`build-base-images`: `frameworks` fora da forma canônica', result.stderr)
            self.assertIn('precisa ser estático', result.stderr)
            self.assertIn('fonte externa', result.stderr)

    def test_lint_fails_when_docs_adr_is_a_symlink_out_of_the_repository(self):
        # End-to-end do finding remanescente: cópia mínima do módulo (ROOT vem
        # de __file__, então a cópia é a raiz) com docs/adr -> diretório externo
        # contendo um arquivo de nome e título válidos.
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            external = base / 'external'
            external.mkdir()
            (external / '0001-example-decision.md').write_text('# ADR-0001 — externo\n')
            copy = base / 'repo'
            for relative in ('scripts/__init__.py', 'scripts/pipeline/__init__.py',
                             'scripts/pipeline/catalog/__init__.py',
                             'scripts/pipeline/catalog/default_batch.py'):
                (copy / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / relative, copy / relative)
            (copy / 'docs').mkdir()
            (copy / 'docs/adr').symlink_to(external)
            result = run_cli('lint', *self.tree(copy, workflow(self.BATCH, self.BATCH, self.BATCH)),
                             cwd=copy)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stderr.count('::error::'), 1)
            self.assertIn('`docs/adr` é link simbólico', result.stderr)

    def test_lint_fails_when_the_adr_is_outside_docs_adr(self):
        # N08: caminhos do reviewer.
        for adr in ('README.md', '/etc/hosts', '../algum-arquivo.md', 'docs/adr/../../README.md'):
            with self.subTest(adr=adr), tempfile.TemporaryDirectory() as temporary:
                policy = {'exceptions': {'sample-runtime': dict(EXCLUSION, adr=adr)}}
                result = run_cli('lint', *self.tree(pathlib.Path(temporary),
                                                    workflow(self.BATCH, self.BATCH, self.BATCH), policy))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr.count('::error::'), 1)
                self.assertIn(f'ADR `{adr}` precisa ser um caminho relativo `docs/adr/NNNN-titulo.md`',
                              result.stderr)


if __name__ == '__main__':
    unittest.main()
