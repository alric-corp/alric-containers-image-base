"""Real Glue views and six-entry journal of lab-sbom-athena-v1; all clients fake.

Positive cases use the selected REAL GetTable and journal bytes. Every mutation,
the SELECT terminal response and every query result page are SYNTHETIC.
"""
import base64
from collections import Counter
import copy
from datetime import datetime, timezone
import json
import re
import unittest
from unittest.mock import patch

from scripts.pipeline.analytics import athena_poc as a, athena_restore as r
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics import test_athena_poc as support, test_athena_terminator as six
from tests.unit.pipeline.analytics.s3_support import ServiceError
from tests.unit.pipeline.analytics.test_athena_restore import archive, GitHub

ROOT = support.ROOT
FIXTURE = ROOT / 'tests/fixtures/sbom-analytics/athena-view-reconciliation'
PLAN = ROOT / 'tests/fixtures/sbom-analytics/athena-reconciliation/sql-plan.json'
ANCESTOR = ROOT / 'tests/fixtures/sbom-analytics/athena-six-entry-resume/execution-journal.json'
PLAN_HASH, AUTH, SELECT_ID = six.PLAN_HASH, six.AUTH, six.QUERY_ID
JOURNAL_HASH = 'e621e60802bd9e7017460a012ec783ea17478cf0df0c26892c99624d03906101'
PREFIX = 'poc_snapshot_6ae0d5a463a20961e4431cb86d7d969ff2157bf25428a22dd08aa119632548b6_'
# Candidate source: latest inspected evidence, not an automatic "latest" selection.
SOURCE = dict(run_id=38097506220, attempt=1, artifact_id=11686421115,
              source_sha='dcdbf3151fc85fe2385f059c2d9bc75586a56134',
              zip_sha256='d43567eb8fb2293a37b754cb110fe8bc73213d6a7db374596439c1415c93418a', zip_bytes=213530,
              journal_sha256=JOURNAL_HASH, journal_bytes=36155, sql_plan_sha256=PLAN_HASH, sql_plan_bytes=257893)
# statement -> (catalog key, authorized SELECT sha256, REAL Glue originalSql sha256)
VIEWS = {'view-0': ('sbom_observations_v1', '78e1c2f9acffb9cf1ac90e58ff5eee1219d1308357102c3058049a84d8f25a91',
                    'a725ca32817d1beb55ebe7b4343d785358073655cb118798edd79ecf0d09bd2e'),
         'view-1': ('sbom_packages_v1', '442fe8704d6b794e46348347d579b3794e4c338fe78eff8d30899b76469c9d35',
                    '099ef49239c71337f9d7791528b6205542e751e7787228756f7cffb552733f47'),
         'view-2': ('sbom_inventory_v1', '8572bae2628d635b09501a760c0bb04cb98a66290f198183f6b79a7eafca55a8',
                    '589973a7f6aaa6c671af4ed8d88a7c199240a946f90a868d96371b0df1ac9a2d')}
PRESTO = re.compile(r'/\* Presto View: ([A-Za-z0-9+/=]+) \*/')


def real_tables():
    return json.loads((FIXTURE / 'glue-tables.json').read_bytes())


def presto(table):
    return json.loads(base64.b64decode(PRESTO.fullmatch(table['ViewOriginalText'])[1]))


def with_view(table, **fields):
    """SYNTHETIC: the real Presto envelope with only the given fields replaced."""
    view = dict(presto(table), **fields)
    return dict(table, ViewOriginalText='/* Presto View: ' + base64.b64encode(canonical(view)).decode() + ' */')


def mutated(key, old, new):
    tables = real_tables()
    sql = presto(tables[key])['originalSql']
    assert sql.count(old) == 1, old
    tables[key] = with_view(tables[key], originalSql=sql.replace(old, new))
    return tables


def authorized(statement_id):
    statement = next(s for s in json.loads(PLAN.read_bytes())['statements'] if s['id'] == statement_id)
    return statement['sql'].partition(' AS\n')[2]


class AthenaViewStructureTests(unittest.TestCase):
    def real(self, key):
        return presto(real_tables()[key])['originalSql']

    def rejected(self, sql, reason, statement_id='view-2'):
        wanted = a.view_structure(authorized(statement_id))
        if reason is None:
            # Consumed completely by the grammar, and a structural field differs.
            self.assertNotEqual(a.view_structure(sql), wanted)
            return
        with self.assertRaises(IngestionError) as caught:
            a.view_structure(sql)
        self.assertEqual(caught.exception.code, 'GLUE_VIEW_SQL_UNSUPPORTED')
        self.assertEqual(caught.exception.observed['reason'], reason)
        self.assertEqual(caught.exception.observed['sql_sha256'], sha256(sql.encode()))

    def test_real_responses_match_authorized_selects_only_structurally(self):
        for statement_id, (key, wanted_hash, real_hash) in VIEWS.items():
            wanted, real = authorized(statement_id), self.real(key)
            with self.subTest(view=key):
                self.assertEqual(sha256(wanted.encode()), wanted_hash)
                self.assertEqual(sha256(real.encode()), real_hash)
                self.assertNotEqual(wanted, real)  # Athena stores its own formatting.
                self.assertEqual(a.view_structure(real), a.view_structure(wanted))

    def test_real_inventory_grouped_inner_join_keeps_relations_aliases_and_filters(self):
        real = self.real('sbom_inventory_v1')
        self.assertIn('FROM\n  (poc_distroless_sbom.' + PREFIX + 'sbom_observations_v1 o\nINNER JOIN ', real)
        self.assertNotIn('INNER', authorized('view-2'))
        structure = a.view_structure(real)
        self.assertEqual(structure['source'], dict(
            join='INNER', left=dict(database='poc_distroless_sbom', table=PREFIX + 'sbom_observations_v1', alias='o'),
            right=dict(database='poc_distroless_sbom', table=PREFIX + 'sbom_packages_v1', alias='p'),
            on={'=': [{'column': ['o', 'sbom_sha256']}, {'column': ['p', 'sbom_sha256']}]}))
        self.assertEqual(structure['where'], {'and': [
            {'=': [{'column': ['o', 'sbom_scope']}, {'string': "'platform'"}]},
            {'=': [{'column': ['p', 'is_document_subject']}, {'boolean': False}]}]})
        self.assertFalse(structure['distinct'])
        self.assertEqual([q for q, _ in structure['columns']], ['o'] * 43 + ['p'] * 11)
        self.assertEqual(structure['columns'][:2], [['o', 'observation_id'], ['o', 'sbom_sha256']])

    def test_real_distinct_views_keep_distinct_projection_order_and_relation(self):
        for statement_id, key, rows in (('view-0', 'sbom_observations_v1', 'sbom_observation_rows_v1'),
                                        ('view-1', 'sbom_packages_v1', 'sbom_package_rows_v1')):
            structure = a.view_structure(self.real(key))
            names = authorized(statement_id).split('\n')[0][len('SELECT DISTINCT '):].split(', ')
            with self.subTest(view=key):
                self.assertTrue(structure['distinct'])
                self.assertIsNone(structure['where'])
                self.assertEqual(structure['columns'], [[None, n] for n in names])
                self.assertEqual(structure['source'], dict(database='poc_distroless_sbom', table=PREFIX + rows, alias=None))
                self.rejected(self.real(key).replace('SELECT DISTINCT', 'SELECT'), None, statement_id)

    def test_synthetic_mutations_of_real_inventory_are_rejected(self):
        real = self.real('sbom_inventory_v1')
        join = '\nINNER JOIN poc_distroless_sbom.' + PREFIX + 'sbom_packages_v1 p ON (o.sbom_sha256 = p.sbom_sha256)'
        left = 'poc_distroless_sbom.' + PREFIX + 'sbom_observations_v1 o'
        where = "((o.sbom_scope = 'platform') AND (p.is_document_subject = false))"
        cases = [
            # Join type, presence and condition.
            ({'INNER JOIN': 'LEFT JOIN'}, 'JOIN_TYPE'), ({'INNER JOIN': 'RIGHT JOIN'}, 'JOIN_TYPE'),
            ({'INNER JOIN': 'FULL JOIN'}, 'JOIN_TYPE'), ({'INNER JOIN': 'LEFT OUTER JOIN'}, 'JOIN_TYPE'),
            ({'INNER JOIN': 'CROSS JOIN'}, 'JOIN_TYPE'), ({'INNER JOIN': 'NATURAL JOIN'}, 'JOIN_TYPE'),
            ({'INNER JOIN': 'INNER'}, 'JOIN_TYPE'), ({join + ')': ')'}, 'GROUPED_RELATION'),
            ({'(' + left + join + ')': left}, 'ALIAS_BINDING'),
            ({'= p.sbom_sha256)': '= p.package_spdx_id)'}, None),
            ({'(o.sbom_sha256 = p.sbom_sha256)': '(p.sbom_sha256 = o.sbom_sha256)'}, None),
            ({'= p.sbom_sha256)': '= p.sbom_sha256 AND o.sbom_scope = p.sbom_scope)'}, None),
            # Filters, operators and literals.
            ({') AND (': ') OR ('}, 'UNEXPECTED_TOKEN'), ({where: "(o.sbom_scope = 'platform')"}, None),
            ({where: '(p.is_document_subject = false)'}, None), ({'\nWHERE ' + where: ''}, None),
            ({where: "((p.is_document_subject = false) AND (o.sbom_scope = 'platform'))"}, None),
            ({"'platform'": "'index'"}, None), ({"'platform'": "'Platform'"}, None),
            ({"'platform'": "'platform) OR (o.sbom_scope = ''index'''"}, None), ({"'platform'": "'inner'"}, None),
            ({'= false)': '= true)'}, None), ({'= false)': "= 'false')"}, None), ({'= false)': '= 0)'}, 'CHARACTER'),
            ({"(o.sbom_scope = 'platform')": "(p.sbom_scope = 'platform')"}, None),
            ({"o.sbom_scope = 'platform'": "o.sbom_scope <> 'platform'"}, 'CHARACTER'),
            ({"(o.sbom_scope = 'platform')": "(NOT o.sbom_scope = 'platform')"}, 'UNEXPECTED_TOKEN'),
            ({'(p.is_document_subject = false)': '(p.is_document_subject IS false)'}, 'OPERATOR'),
            ({"'platform'": "'platform"}, 'UNTERMINATED_STRING'),
            # Projection: DISTINCT, columns, order, qualifiers, functions, aliases.
            ({'SELECT\n': 'SELECT DISTINCT\n'}, None), ({'\n, o.predicate_digest': ''}, None),
            ({'\n, o.predicate_digest': '\n, o.predicate_digest\n, o.predicate_digest'}, None),
            ({'o.observation_id\n, o.sbom_sha256': 'o.sbom_sha256\n, o.observation_id'}, None),
            ({'\n, p.package_name': '\n, o.package_name'}, None),
            ({'o.observation_id': 'lower(o.observation_id)'}, 'FUNCTION'),
            ({'o.observation_id': 'CAST(o.observation_id AS varchar)'}, 'UNEXPECTED_TOKEN'),
            ({'o.observation_id': 'o.observation_id AS id'}, 'UNEXPECTED_TOKEN'),
            ({'o.observation_id': 'o.OBSERVATION_ID'}, 'IDENTIFIER_CASE'),
            ({'o.observation_id': 'o."observation_id"'}, 'DELIMITED_IDENTIFIER'),
            ({'o.observation_id': 'o.*'}, 'CHARACTER'),
            # Relations, database, snapshot and aliases.
            ({'_sbom_packages_v1 p ON': '_sbom_packages_v1 o ON'}, 'ALIAS_DECLARATION'),
            ({'_sbom_observations_v1 o\n': '_sbom_observations_v1\n'}, 'ALIAS_DECLARATION'),
            ({'_sbom_observations_v1 o\n': '_sbom_observations_v1 p\n', '_sbom_packages_v1 p ON': '_sbom_packages_v1 o ON'}, None),
            ({'_sbom_packages_v1 p ON': '_sbom_packages_v1 inner ON'}, 'JOIN_CONDITION'),
            ({'_sbom_packages_v1 p ON': '_sbom_packages_v1 "inner" ON'}, 'DELIMITED_IDENTIFIER'),
            ({'_sbom_packages_v1 p ON': '_sbom_packages_v1 AS ON'}, 'ALIAS'),
            ({'JOIN poc_distroless_sbom.': 'JOIN other_db.'}, None),
            ({'_sbom_packages_v1 p': '_sbom_package_rows_v1 p'}, None),
            ({'JOIN poc_distroless_sbom.' + PREFIX: 'JOIN poc_distroless_sbom.' + PREFIX.replace('6ae0d5a4', 'aaaaaaaa')}, None),
            ({'(poc_distroless_sbom.': '(awsdatacatalog.poc_distroless_sbom.'}, 'CATALOG_QUALIFIED_RELATION'),
            ({'(poc_distroless_sbom.': '(SELECT o.observation_id FROM poc_distroless_sbom.'}, 'SUBQUERY'),
            ({'p.sbom_sha256))\nWHERE': 'p.sbom_sha256)) q\nWHERE'}, 'TRAILING_INPUT'),  # alias = new scope
            # Grouping, delimiters, comments, extra instructions and characters.
            ({'false))\n': 'false)\n'}, 'UNBALANCED_PARENTHESES'), ({'false))\n': 'false)))\n'}, 'UNBALANCED_PARENTHESES'),
            ({"(o.sbom_scope = 'platform')": "((((o.sbom_scope = 'platform'))))"}, 'DEPTH_LIMIT'),
            ({'false))\n': 'false));\n'}, 'STATEMENT_DELIMITER'),
            ({'false))\n': 'false))\nSELECT o.observation_id FROM poc_distroless_sbom.t o\n'}, 'TRAILING_INPUT'),
            ({'\nINNER JOIN': ' /* INNER */\nINNER JOIN'}, 'COMMENT'), ({'\nWHERE': '\n-- (\nWHERE'}, 'COMMENT'),
            ({'\nINNER JOIN': ' INNER JOIN'}, 'CHARACTER'),
        ]
        for changes, reason in cases:
            sql = real
            for old, new in changes.items():
                self.assertEqual(sql.count(old), 1, old)
                sql = sql.replace(old, new)
            with self.subTest(changes=changes):
                self.rejected(sql, reason)

    def test_only_reviewed_formatting_is_equivalent(self):
        real = self.real('sbom_inventory_v1')
        wanted = a.view_structure(authorized('view-2'))
        aliased = real.replace('_v1 o\nINNER', '_v1 AS o\nINNER').replace('_v1 p ON', '_v1 AS p ON')
        self.assertEqual(a.view_structure(aliased), wanted)
        self.assertEqual(a.view_structure(authorized('view-1').replace('SELECT DISTINCT', 'select distinct')),
                         a.view_structure(authorized('view-1')))
        # Grouping is not flattened: (a AND b) AND c differs from a AND b AND c.
        base = "SELECT o.a FROM d.t o JOIN d.u p ON o.k = p.k WHERE o.a = 'x' AND p.b = false AND o.c = 'y'"
        self.assertNotEqual(a.view_structure(base), a.view_structure(base.replace("WHERE o.a = 'x' AND p.b = false",
                                                                                  "WHERE (o.a = 'x' AND p.b = false)")))
        self.assertEqual(a.view_structure(base), a.view_structure(base.replace('WHERE ', 'WHERE (') + ')'))
        self.assertEqual(a.view_structure('SELECT a FROM d.t'), a.view_structure('SELECT\ta\r\nFROM d . t'))

    def test_limits_and_non_text_fail_closed(self):
        for sql in (None, '', b'SELECT a FROM d.t', 'SELECT a FROM d.t' + ' ' * a.VIEW_SQL_LIMIT):
            with self.subTest(sql=type(sql)), self.assertRaisesRegex(IngestionError, 'GLUE_VIEW_SQL_LIMIT'):
                a.view_structure(sql)
        many = 'SELECT ' + ', '.join(['a'] * 3000) + ' FROM d.t'
        with self.assertRaises(IngestionError) as caught:
            a.view_structure(many)
        self.assertEqual(caught.exception.observed['reason'], 'TOKEN_LIMIT')


class AthenaViewReadbackTests(unittest.TestCase):
    setUpClass = classmethod(support.AthenaPocTests.setUpClass.__func__)
    setUp = support.AthenaPocTests.setUp

    def catalog(self, tables=None):
        """REAL plan/journal/catalog and saved DDL responses; Athena fake only replays them."""
        self.raw, original = PLAN.read_bytes(), (FIXTURE / 'execution-journal.json').read_bytes()
        self.journal.write_bytes(original)
        known, self.gets = json.loads(original)['executions'], []
        for table in (tables or real_tables()).values():
            self.glue.tables[table['Name']] = table

        def get(**kwargs):
            self.gets.append(kwargs['QueryExecutionId'])
            saved = next(e for e in known.values() if e['query_id'] == kwargs['QueryExecutionId'])
            return {'QueryExecution': copy.deepcopy(saved['execution'])}
        self.athena.get_query_execution = get
        return json.loads(original)

    def readback(self, journal, **kwargs):
        return a.resource_readback(self.athena, self.glue, self.expected, self.settings, self.proposal, journal,
                                   journal_path=self.journal, plan_raw=self.raw, authorization_reference=AUTH, **kwargs)

    def test_real_five_object_catalog_matrix_in_complete_readback(self):
        journal, observations = self.catalog(), {}
        resource = self.readback(journal, require_complete=True, observations=observations)
        self.assertEqual(len(resource['existing_objects']), 5)
        for statement_id, (key, wanted_hash, real_hash) in VIEWS.items():
            record = observations['objects'][key]
            view = resource['existing_objects'][record['name']]['view_comparison']
            with self.subTest(view=key):
                self.assertEqual((record['statement_id'], record['query_id']),
                                 (statement_id, journal['executions'][statement_id]['query_id']))
                self.assertEqual(record['identity'], dict(Name=PREFIX + key, DatabaseName='poc_distroless_sbom',
                                                          CatalogId='712107929769', TableType='VIRTUAL_VIEW'))
                self.assertEqual((view['status'], view['rule'], view['authorized_sql_sha256'], view['original_sql_sha256']),
                                 ('EQUIVALENT', 'RESTRICTED_V1_VIEW_STRUCTURE', wanted_hash, real_hash))
                self.assertEqual(view['authorized_structure_sha256'], view['observed_structure_sha256'])
                self.assertEqual((view['catalog'], view['schema']), ('awsdatacatalog', 'poc_distroless_sbom'))
                self.assertEqual(record['view'], view)
        for key in ('sbom_observation_rows_v1', 'sbom_package_rows_v1'):
            comparison = resource['existing_objects'][observations['objects'][key]['name']]['location_comparison']
            self.assertEqual(comparison['rule'], 'EXACT_OR_ONE_FINAL_SLASH_OMITTED')
            self.assertEqual(comparison['observed'], comparison['expected'][:-1])
        self.assertEqual(sorted(self.gets), sorted(journal['executions'][k]['query_id'] for k in
                                                   ('table-0', 'table-1', 'view-0', 'view-1', 'view-2')))
        self.assertEqual(self.athena.calls, [])

    def test_rejected_real_view_keeps_safe_definition_and_comparison_identity(self):
        journal, observations = self.catalog(mutated('sbom_inventory_v1', 'INNER JOIN', 'LEFT JOIN')), {}
        with self.assertRaises(IngestionError) as caught:
            self.readback(journal, observations=observations)
        error, record = caught.exception, observations['objects']['sbom_inventory_v1']
        self.assertEqual((error.code, error.stage, error.key), ('GLUE_VIEW_SQL_UNSUPPORTED', 'CATALOG', PREFIX + 'sbom_inventory_v1'))
        self.assertIs(error.observed, record)
        self.assertEqual((record['statement_id'], record['query_id']), ('view-2', '1ee338cc-8e8a-40a7-8bd1-2bd787b10918'))
        self.assertEqual(record['view']['status'], 'UNSUPPORTED')
        self.assertEqual(record['view']['failure']['reason'], 'JOIN_TYPE')
        self.assertEqual(record['view']['failure']['sql_sha256'], record['view']['original_sql_sha256'])
        self.assertIn('LEFT JOIN', record['view']['original_sql'])
        self.assertEqual(record['view']['authorized_sql_sha256'], VIEWS['view-2'][1])
        self.assertEqual([observations['objects'][k]['view']['status'] for k in ('sbom_observations_v1', 'sbom_packages_v1')],
                         ['EQUIVALENT', 'EQUIVALENT'])
        text = canonical(error.diagnostic()).decode()
        for forbidden in ('CreatedBy', 'ResponseMetadata', 'SECRET', 'Credentials'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(self.athena.calls, [])

    def test_identity_catalog_schema_type_and_envelope_still_required(self):
        def view(change):
            tables = real_tables()
            tables['sbom_inventory_v1'] = change(copy.deepcopy(tables['sbom_inventory_v1']))
            return tables
        cases = [(lambda t: dict(t, TableType='EXTERNAL_TABLE'), 'GLUE_VIEW_CONFLICT'),
                 (lambda t: dict(t, ViewOriginalText='/* Hive View */'), 'GLUE_VIEW_REPRESENTATION_UNSUPPORTED'),
                 (lambda t: with_view(t, catalog='other'), 'GLUE_VIEW_CONFLICT'),
                 (lambda t: with_view(t, schema='other'), 'GLUE_VIEW_CONFLICT'),
                 (lambda t: dict(t, DatabaseName='other'), 'GLUE_TABLE_IDENTITY_DIFFERS'),
                 (lambda t: dict(t, CatalogId='000000000000'), 'GLUE_TABLE_IDENTITY_DIFFERS')]
        for change, code in cases:
            journal = self.catalog(view(change))
            with self.subTest(code=code), self.assertRaisesRegex(IngestionError, code):
                self.readback(journal)
        # Same name and CreatedBy without this round's journal entry are not ownership.
        self.catalog()
        with self.assertRaisesRegex(IngestionError, 'CATALOG_NAME_CONFLICT'):
            a.resource_readback(self.athena, self.glue, self.expected, self.settings, self.proposal)
        self.assertEqual(self.athena.calls, [])

    def test_unread_objects_stay_not_observed(self):
        journal, observations = self.catalog(), {}
        original = self.athena.get_work_group
        self.athena.get_work_group = lambda **kw: dict(original(**kw), WorkGroup=dict(
            original(**kw)['WorkGroup'], State='DISABLED'))
        with self.assertRaisesRegex(IngestionError, 'WORKGROUP_DIFFERS'):
            self.readback(journal, observations=observations)
        self.assertEqual(observations['objects'], {k: 'NOT_OBSERVED' for k in a.TABLE_NAMES})


class AthenaRunFinalReadbackTests(unittest.TestCase):
    """run() with the synthetic test round; only the five catalog objects are REAL."""
    setUpClass = classmethod(support.AthenaPocTests.setUpClass.__func__)

    def setUp(self):
        support.AthenaPocTests.setUp(self)
        self.reports = self.root / 'reports'
        self.run_poc()  # Complete SYNTHETIC round: journal and fake catalog exist.
        self.starts = len(self.athena.calls)
        for name in ('resources-before.json', 'resources-after.json', 'snapshot-after.json'):
            (self.reports / name).unlink()

    def run_poc(self):
        self.runs = getattr(self, 'runs', 0) + 1  # Each hosted attempt recovers into a fresh directory.
        return a.run(self.s3, self.sts, self.athena, self.glue, self.expected, self.settings, self.session, 'test-round',
                     self.reports, self.root / ('recovered-' + str(self.runs)), authorized_sha256=sha256(self.raw),
                     authorization_reference='TEST_ONLY owner ref')

    def install(self, tables):
        for table in tables.values():
            self.glue.tables[table['Name']] = table

    def failure(self):
        return json.loads((self.reports / 'execution-failure.json').read_bytes())

    def test_real_catalog_accepted_before_and_after_complete_simulated_pass(self):
        self.install(real_tables())
        result = self.run_poc()
        self.assertEqual(result['code'], 'ATHENA_RESULTS_VERIFIED')
        self.assertEqual(len(self.athena.calls), self.starts)
        for phase in ('before', 'after'):
            objects = json.loads((self.reports / ('resources-' + phase + '.json')).read_bytes())['existing_objects']
            self.assertEqual(sorted(v['view_comparison']['status'] for v in objects.values() if 'view_comparison' in v),
                             ['EQUIVALENT'] * 3)
        self.assertEqual((self.reports / 'snapshot-after.json').read_bytes(), (self.reports / 'snapshot-before.json').read_bytes())
        self.assertFalse((self.reports / 'execution-failure.json').exists())

    def test_catalog_failure_still_records_final_readback_and_not_fabricated_resources(self):
        self.install(mutated('sbom_inventory_v1', 'INNER JOIN', 'LEFT JOIN'))
        with self.assertRaisesRegex(IngestionError, 'GLUE_VIEW_SQL_UNSUPPORTED'):
            self.run_poc()
        failure = self.failure()
        self.assertEqual((failure['code'], failure['stage'], failure['object']),
                         ('GLUE_VIEW_SQL_UNSUPPORTED', 'CATALOG', PREFIX + 'sbom_inventory_v1'))
        self.assertEqual(failure['observed']['view']['failure']['reason'], 'JOIN_TYPE')
        self.assertEqual(failure['catalog_readback']['phase'], 'BEFORE')
        self.assertEqual(failure['catalog_readback']['objects']['sbom_inventory_v1'], failure['observed'])
        self.assertEqual(failure['final_readback']['status'], 'UNCHANGED')
        self.assertEqual((self.reports / 'snapshot-after.json').read_bytes(), (self.reports / 'snapshot-before.json').read_bytes())
        self.assertFalse((self.reports / 'resources-before.json').exists())
        self.assertEqual(len(self.athena.calls), self.starts)

    def test_simultaneous_final_readback_failure_keeps_both_errors(self):
        self.install(mutated('sbom_inventory_v1', 'INNER JOIN', 'LEFT JOIN'))
        real, calls = a.read_snapshot, []

        def flaky(*args, **kwargs):
            calls.append(args)
            if len(calls) > 1:
                raise ServiceError(503, 'SlowDown')
            return real(*args, **kwargs)
        with patch.object(a, 'read_snapshot', side_effect=flaky), self.assertRaises(IngestionError) as caught:
            self.run_poc()
        self.assertEqual(caught.exception.code, 'GLUE_VIEW_SQL_UNSUPPORTED')
        failure = self.failure()
        self.assertEqual(failure['code'], 'GLUE_VIEW_SQL_UNSUPPORTED')
        self.assertEqual(failure['final_readback'], dict(status='NOT_OBSERVED', failure=dict(status='ERROR', code='SlowDown')))
        self.assertFalse((self.reports / 'snapshot-after.json').exists())
        self.assertNotIn('SECRET', (self.reports / 'execution-failure.json').read_text())

    def test_changed_snapshot_is_recorded_beside_error_and_still_fails_success(self):
        real, calls = a.snapshot_fingerprint, []

        def changed(verified):
            calls.append(verified)
            value = real(verified)
            return dict(value, manifest_version_id='changed') if len(calls) % 2 == 0 else value
        self.install(mutated('sbom_inventory_v1', 'INNER JOIN', 'LEFT JOIN'))
        with patch.object(a, 'snapshot_fingerprint', side_effect=changed), self.assertRaisesRegex(IngestionError, 'GLUE_VIEW_SQL'):
            self.run_poc()
        self.assertEqual(self.failure()['final_readback']['status'], 'CHANGED')
        self.install(real_tables())
        with patch.object(a, 'snapshot_fingerprint', side_effect=changed), self.assertRaises(IngestionError) as caught:
            self.run_poc()
        self.assertEqual((caught.exception.code, caught.exception.stage), ('ATHENA_SNAPSHOT_CHANGED', 'FINAL_READBACK'))

    def test_unread_catalog_is_not_observed_and_snapshot_after_is_still_attempted(self):
        original = self.athena.get_work_group
        self.athena.get_work_group = lambda **kw: dict(original(**kw), WorkGroup=dict(
            original(**kw)['WorkGroup'], State='DISABLED'))
        with self.assertRaisesRegex(IngestionError, 'WORKGROUP_DIFFERS'):
            self.run_poc()
        failure = self.failure()
        self.assertEqual(failure['catalog_readback']['objects'], {k: 'NOT_OBSERVED' for k in a.TABLE_NAMES})
        self.assertEqual(failure['final_readback']['status'], 'UNCHANGED')
        self.assertFalse((self.reports / 'resources-before.json').exists())
        self.assertTrue((self.reports / 'snapshot-after.json').exists())


class RealJournalGitHub(GitHub):
    """Selected REAL run 38097506220 metadata; SYNTHETIC transport ZIP with its own hash."""
    def __init__(self, raw):
        self.metadata = json.loads((FIXTURE / 'github-metadata.json').read_bytes())
        self.metadata['artifact'].update(size_in_bytes=len(raw), digest='sha256:' + sha256(raw))
        self.raw, self.calls = raw, []


class AthenaRealSourceResumeTests(unittest.TestCase):
    setUpClass = classmethod(support.AthenaPocTests.setUpClass.__func__)
    seed_known = six.AthenaSixEntryResumeTests.seed_known
    restore = six.AthenaSixEntryResumeTests.restore
    execute = six.AthenaSixEntryResumeTests.execute

    def setUp(self):
        support.AthenaPocTests.setUp(self)
        self.raw, self.ancestor = PLAN.read_bytes(), ANCESTOR.read_bytes()
        self.original = (FIXTURE / 'execution-journal.json').read_bytes()
        # Ancestor first: selection is by exact member path and hashes, never order/basename.
        self.members = [('athena-resume-source/execution-journal.json', self.ancestor),
                        ('athena-resume-source/sql-plan.json', self.raw),
                        ('athena-reports/authentication.json', (FIXTURE / 'authentication.json').read_bytes()),
                        ('athena-reports/execution-journal.json', self.original),
                        ('athena-reports/sql-plan.json', self.raw)]
        self.zipped = archive(self.members)  # SYNTHETIC transport, not the original 213530-byte ZIP.
        self.resume = r.ResumeSource(**dict(SOURCE, zip_sha256=sha256(self.zipped), zip_bytes=len(self.zipped)))
        self.github = RealJournalGitHub(self.zipped)
        self.executor_sha = 'b' * 40
        self.fresh('first')

    def fresh(self, name):
        self.reports, self.originals = self.root / ('reports-' + name), self.root / ('originals-' + name)
        self.journal = self.reports / 'execution-journal.json'
        self.settings = dict(type(self).settings)
        self.glue = support.Glue(self.expected, self.settings)
        self.athena = support.Athena(self.raw, self.expected, self.settings, self.glue)
        self.events = []

    def seed(self, tables=None):
        """Real saved DDL responses (journal), SYNTHETIC SELECT terminal/results, REAL catalog."""
        self.seed_known()
        for table in (tables or real_tables()).values():
            self.glue.tables[table['Name']] = table

    def readback(self, **kwargs):
        return a.resource_readback(self.athena, self.glue, self.expected, self.settings, self.proposal,
                                   json.loads(self.journal.read_bytes()), journal_path=self.journal,
                                   plan_raw=self.raw, authorization_reference=AUTH, **kwargs)

    def test_candidate_source_restores_exact_member_and_preserves_ancestor(self):
        self.assertEqual(r.source_document(canonical(SOURCE)), r.ResumeSource(**SOURCE))
        self.assertEqual((sha256(self.original), len(self.original)), (JOURNAL_HASH, 36155))
        self.assertEqual((sha256(self.ancestor), len(self.ancestor)), (six.JOURNAL_HASH, 35270))
        self.assertEqual(sha256(self.raw), PLAN_HASH)
        receipt = self.restore()
        self.assertEqual((receipt['restored_executions'], receipt['total_round_budget'],
                          receipt['remaining_unreserved_executions']), (6, 18, 12))
        self.assertEqual((receipt['source']['source_sha'], receipt['executor_source_sha']),
                         (SOURCE['source_sha'], self.executor_sha))
        self.assertEqual(self.journal.read_bytes(), self.original)
        self.assertEqual((self.originals / 'execution-journal.json').read_bytes(), self.original)
        self.assertEqual((self.originals / 'source-artifact.zip').read_bytes(), self.zipped)
        self.assertIn(dict(path='athena-resume-source/execution-journal.json', size=35270, sha256=six.JOURNAL_HASH),
                      r.archive_members(self.zipped)[1])
        ancestor, current = (json.loads(v)['executions'] for v in (self.ancestor, self.original))
        self.assertEqual({k: (e['query_id'], e['request']) for k, e in ancestor.items()},
                         {k: (e['query_id'], e['request']) for k, e in current.items()})
        self.assertEqual({k: sorted(f for f in set(ancestor[k]) | set(current[k]) if ancestor[k].get(f) != current[k].get(f))
                          for k in current},
                         dict({k: ['identity_comparison', 'recorded_get_attempts'] for k in
                               ('table-0', 'table-1', 'view-0', 'view-1', 'view-2')}, **{'01_find_images': []}))

    def test_real_catalog_gate_known_select_then_exactly_12_starts_and_second_pass_zero(self):
        self.restore()
        self.seed()
        observations = {}
        before = self.readback(observations=observations)
        self.assertEqual(len(before['existing_objects']), 5)
        self.assertEqual([observations['objects'][VIEWS[k][0]]['view']['status'] for k in VIEWS], ['EQUIVALENT'] * 3)
        self.assertEqual(before['api_calls']['idempotent_retransmissions'], 0)
        self.assertFalse([e for e in self.events if e[0] != 'GET'])
        result = self.execute()
        plan = json.loads(self.raw)
        planned = {a.request(s, plan)['ClientRequestToken']: s['kind'] for s in plan['statements']}
        self.assertEqual(Counter(planned[v['ClientRequestToken']] for v in self.athena.calls), {'SELECT': 10, 'DESCRIBE': 2})
        self.assertEqual((result['historically_reserved_requests'], result['api_calls']['new_starts'],
                          result['api_calls']['idempotent_retransmissions'], result['distinct_query_execution_ids'],
                          result['authorized_round_budget'], result['remaining_unreserved_executions']), (6, 12, 0, 18, 18, 0))
        known = json.loads(self.original)['executions']
        self.assertFalse({v['request']['ClientRequestToken'] for v in known.values()} &
                         {v['ClientRequestToken'] for v in self.athena.calls})
        first = next(i for i, event in enumerate(self.events) if event[0] == 'START')
        self.assertIn(('RESULTS', SELECT_ID), self.events[:first])
        self.assertTrue({('GET', v['query_id']) for v in known.values()} <= set(self.events[:first]))
        after = {}
        self.readback(require_complete=True, observations=after)
        self.assertEqual([after['objects'][VIEWS[k][0]]['view']['status'] for k in VIEWS], ['EQUIVALENT'] * 3)
        saved = json.loads(self.journal.read_bytes())['executions']
        pins = json.loads((six.FIXTURE / 'request-fingerprints.json').read_bytes())
        for statement, pin in zip(plan['statements'], pins):
            request = saved[statement['id']]['request']
            with self.subTest(statement=statement['id']):
                self.assertEqual(saved[statement['id']]['state'], 'VERIFIED')
                self.assertEqual((sha256(canonical(request)), request['ClientRequestToken'], request.get('ExecutionParameters', [])),
                                 (pin['request_sha256'], pin['client_request_token'], pin['parameters']))
        for key, entry in known.items():
            self.assertEqual((saved[key]['query_id'], saved[key]['request']), (entry['query_id'], entry['request']))
        comparison = saved['01_find_images']['identity_comparison']
        self.assertEqual((comparison['sql_rule'], comparison['execution_parameters']), ('TRAILING_TERMINATOR_OMITTED', 'NOT_RETURNED'))
        self.assertEqual(self.execute()['api_calls']['start_query_execution'], 0)
        self.assertEqual(len(self.athena.calls), 12)
        self.assertEqual(sha256((self.reports / 'sql-plan.json').read_bytes()), PLAN_HASH)
        self.assertEqual((self.originals / 'execution-journal.json').read_bytes(), self.original)
        self.assertEqual(sha256((FIXTURE / 'execution-journal.json').read_bytes()), JOURNAL_HASH)

    def test_real_view_divergence_blocks_known_select_and_new_starts(self):
        for number, (tables, code) in enumerate([
                (mutated('sbom_inventory_v1', 'INNER JOIN', 'LEFT JOIN'), 'GLUE_VIEW_SQL_UNSUPPORTED'),
                (mutated('sbom_inventory_v1', "'platform'", "'index'"), 'GLUE_VIEW_CONFLICT'),
                (mutated('sbom_packages_v1', 'SELECT DISTINCT', 'SELECT'), 'GLUE_VIEW_CONFLICT')]):
            self.fresh(str(number))
            self.restore()
            self.seed(tables)
            with self.subTest(code=code), self.assertRaisesRegex(IngestionError, code):
                self.readback()
            self.assertEqual(self.athena.calls, [])
            self.assertFalse([e for e in self.events if e[0] in ('START', 'RESULTS')])
            self.assertEqual({k: e['request'] for k, e in json.loads(self.journal.read_bytes())['executions'].items()},
                             {k: e['request'] for k, e in json.loads(self.original)['executions'].items()})

    def test_known_select_divergence_blocks_all_new_starts(self):
        def results(test):
            original = test.athena.get_query_results

            def changed(**kwargs):
                value = original(**kwargs)
                if kwargs['QueryExecutionId'] == SELECT_ID:
                    value['ResultSet']['Rows'][1]['Data'][0] = {'VarCharValue': 'changed-result'}
                return value
            test.athena.get_query_results = changed

        def state(name):
            return lambda test: test.synthetic_select['Status'].update(State=name)

        def overrun(test):
            submitted = json.loads(test.original)['executions']['01_find_images']['submitted_at']
            test.synthetic_select['Status'].update(CompletionDateTime=datetime.fromtimestamp(submitted + 121, timezone.utc),
                                                   SubmissionDateTime=datetime.fromtimestamp(submitted, timezone.utc))
            test.synthetic_select['Statistics']['TotalExecutionTimeInMillis'] = 121000
        for number, (change, code) in enumerate([(results, 'RESULTS_DIFFER'), (state('FAILED'), 'QUERY_FAILED'),
                                                 (state('CANCELLED'), 'QUERY_FAILED'), (overrun, 'QUERY_TIMEOUT')]):
            self.fresh('select-' + str(number))
            self.restore()
            self.seed()
            self.readback()
            change(self)
            with self.subTest(code=code), self.assertRaisesRegex(IngestionError, code):
                self.execute()
            self.assertEqual(self.athena.calls, [])
            saved = json.loads(self.journal.read_bytes())['executions']['01_find_images']
            self.assertEqual((saved['query_id'], saved['request']['ClientRequestToken']), (SELECT_ID, six.TOKEN))


if __name__ == '__main__':
    unittest.main()
