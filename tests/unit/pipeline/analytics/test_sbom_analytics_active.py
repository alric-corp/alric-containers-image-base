"""Active Distroless SBOM Analytics names, contracts and entry points.

Offline, service-shaped fakes only. The closed historical round stays
replayable through its own fixtures (test_athena_run.historical_profile);
nothing here accepts its names, prefix, bucket or round.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from scripts.pipeline.analytics import athena_run as a, s3_run
from scripts.pipeline.analytics.catalog import catalog_plan, NAMESPACE
from scripts.pipeline.analytics.ingestion_types import IngestionError
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import load_plan, publish_snapshot, read_snapshot, recover_snapshot
from scripts.pipeline.analytics.spdx import canonical, sha256
from tests.unit.pipeline.analytics.s3_support import FakeS3, ServiceError
from tests.unit.pipeline.analytics.test_athena_run import Athena, Glue, HISTORICAL

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / 'tests/fixtures/sbom-analytics'
ACTIVE = ROOT / 'policies/analytics/s3.json'
BUCKET = 'alric-distroless-sbom-analytics-712107929769-us-east-1'
SNAPSHOT = '0b0c4ed7014746c8facdd779debd435e6a3fb160c5619f7d60751dabf5e4ec0b'
AUTH = 'TEST_ONLY owner authorization'


def athena_settings(**changes):
    """Hosted Athena settings with the active names; manifest refs come from the snapshot."""
    value = json.loads((HISTORICAL / 'athena-lab-poc.json').read_text())
    value.update({k: NAMESPACE[k] for k in ('database', 'workgroup', 'table_prefix', 'results_prefix')})
    value.update(changes)
    return value


class ActiveProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.expected = s3_run.config(ACTIVE)
        s3_run.unpack(FIXTURES / 'frozen-plan-v1.zip', FIXTURES / 'frozen-plan-v1.json',
                   Path(cls.tmp.name) / 'plan', cls.expected)
        cls.payload = load_plan(Path(cls.tmp.name) / 'plan')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.s3 = FakeS3('us-east-1')
        self.adapter = S3Adapter(self.s3, self.payload.destination)
        publish_snapshot(self.payload, self.adapter)
        fingerprint = a.snapshot_fingerprint(read_snapshot(self.adapter, SNAPSHOT))
        self.settings = athena_settings(manifest_sha256=fingerprint['manifest_sha256'],
                                        manifest_version_id=fingerprint['manifest_version_id'])
        recover_snapshot(self.adapter, SNAPSHOT, self.root / 'local')
        self.inspection = s3_run.inspect_recovered(self.root / 'local', self.expected)
        self.proposal = catalog_plan(self.adapter, SNAPSHOT, database='sbom_analytics', table_prefix='sbom_snapshot')
        self.raw = a.build_plan(self.proposal, self.inspection, self.root / 'local', self.expected, self.settings,
                                'sbom-analytics-v1-r1')
        self.glue = Glue(self.expected, self.settings)
        self.athena = Athena(self.raw, self.expected, self.settings, self.glue)
        self.session = 'test-oidc-session'
        role, account = self.expected['expected_role_arn'], '712107929769'
        self.sts = SimpleNamespace(get_caller_identity=lambda: dict(
            Account=account, Arn=f'arn:aws:sts::{account}:assumed-role/{role.split("/")[-1]}/{self.session}',
            UserId=self.expected['expected_role_id'] + ':' + self.session))

    def test_active_destination_new_snapshot_and_unchanged_corpus(self):
        historical = s3_run.config(HISTORICAL / 'lab-poc.json')
        self.assertEqual(self.expected['destination'], dict(bucket=BUCKET, prefix='sbom-analytics/v1', region='us-east-1',
                                                            expected_bucket_owner='712107929769'))
        self.assertEqual(self.expected['snapshot_id'], SNAPSHOT)
        self.assertNotEqual(historical['snapshot_id'], SNAPSHOT)
        for key in ('batch_id', 'payload_objects', 'payload_bytes', 'golden', 'expected_role_arn', 'expected_role_id'):
            self.assertEqual(self.expected[key], historical[key], key)
        self.assertNotRegex(ACTIVE.read_text(), 'poc')

    def test_retargeted_plan_keeps_every_frozen_spdx_and_parquet_byte(self):
        historical = s3_run.config(HISTORICAL / 'lab-poc.json')
        s3_run.unpack(FIXTURES / 'lab-frozen-plan.zip', FIXTURES / 'lab-frozen-plan.json', self.root / 'old', historical)
        old = load_plan(self.root / 'old')
        self.assertEqual([(o.path, o.body) for o in old.objects], [(o.path, o.body) for o in self.payload.objects])
        self.assertEqual(old.batch_id, self.payload.batch_id)
        self.assertEqual((old.snapshot_id, self.payload.snapshot_id), (historical['snapshot_id'], SNAPSHOT))
        self.assertEqual(self.payload.destination.bucket, BUCKET)
        self.assertTrue(any(o.path.startswith('raw/') for o in self.payload.objects))
        self.assertEqual(sum(o.path.endswith('.parquet') for o in self.payload.objects), 2)
        descriptor = json.loads((FIXTURES / 'frozen-plan-v1.json').read_text())
        old_descriptor = json.loads((FIXTURES / 'lab-frozen-plan.json').read_text())
        self.assertEqual(descriptor['origin']['derived_from_package_sha256'], old_descriptor['package_sha256'])
        self.assertEqual(descriptor['origin']['derived_from_plan_sha256'], old_descriptor['plan_sha256'])
        self.assertIs(descriptor['origin']['publication_authority'], False)
        self.assertEqual(len(self.payload.objects) + 1, 20)

    def test_hosted_configuration_accepts_only_the_exact_active_names(self):
        path = self.root / 'athena.json'
        path.write_bytes(canonical(self.settings))
        self.assertEqual(a.config(path)['database'], 'sbom_analytics')
        for key, value in (('database', 'poc_distroless_sbom'), ('workgroup', 'poc_distroless_sbom'),
                           ('table_prefix', 'poc_snapshot'), ('results_prefix', 'query-results/poc-v1/'),
                           ('database', 'sbom_analytics2'), ('workgroup', 'primary'), ('table_prefix', 'sbom_snapshot_x')):
            with self.subTest(key=key, value=value):
                path.write_bytes(canonical(dict(self.settings, **{key: value})))
                with self.assertRaises(IngestionError):
                    a.config(path)

    def test_plan_requests_and_session_use_only_the_new_names(self):
        plan = json.loads(self.raw)
        self.assertEqual((plan['database'], plan['workgroup'], plan['catalog']),
                         ('sbom_analytics', 'sbom_analytics', 'AwsDataCatalog'))
        self.assertEqual(plan['result_configuration']['OutputLocation'],
                         's3://' + BUCKET + '/query-results/sbom-analytics-v1/')
        self.assertTrue(all(name.startswith('sbom_analytics.sbom_snapshot_' + SNAPSHOT + '_')
                            for name in plan['table_names'].values()))
        self.assertEqual(len(plan['statements']), 18)
        self.assertNotRegex(self.raw.decode(), r'poc_|poc-v1|alric-distroless-sbom-712107929769')
        for location in self.proposal['locations'].values():
            self.assertTrue(location.startswith('s3://' + BUCKET + '/sbom-analytics/v1/snapshots/' + SNAPSHOT + '/'))

    def test_session_policy_stays_inside_the_versioned_role_policy(self):
        role = {s['Sid']: s for s in json.loads((ROOT / 'policies/aws/factory-distroless-v1.inline-policy.json').read_text())['Statement']}
        session = a.session_policy(self.expected, self.settings, execute=True)
        resources = {r for s in session['Statement'] for r in ([s['Resource']] if type(s['Resource']) is str else s['Resource'])}
        self.assertIn(role['SbomAnalyticsAthenaWorkgroup']['Resource'][0], resources)
        self.assertIn('arn:aws:s3:::' + BUCKET + '/query-results/sbom-analytics-v1/*', resources)
        self.assertEqual(role['SbomAnalyticsQueryResults']['Resource'], ['arn:aws:s3:::' + BUCKET + '/query-results/sbom-analytics-v1/*'])
        tables = [r for r in role['SbomAnalyticsGlueReadAndNewTables']['Resource'] if ':table/' in r]
        self.assertEqual(sorted(t.rsplit('/', 1)[1] for t in tables),
                         sorted(n.split('.', 1)[1] for n in self.proposal['table_names'].values()))
        self.assertFalse(any('poc' in r or 'alric-distroless-sbom-712107929769' in r for r in resources))

    def test_fresh_round_runs_the_18_statements_from_an_empty_journal(self):
        with patch('socket.socket', side_effect=AssertionError('no cloud')):
            result = a.run(self.s3, self.sts, self.athena, self.glue, self.expected, self.settings, self.session,
                           'sbom-analytics-v1-r1', self.root / 'reports', self.root / 'recovered',
                           authorized_sha256=sha256(self.raw), authorization_reference=AUTH)
        self.assertEqual((result['code'], result['query_executions'], result['distinct_query_execution_ids']),
                         ('ATHENA_RESULTS_VERIFIED', 18, 18))
        self.assertTrue(result['snapshot_bytes_and_versions_unchanged'])
        self.assertEqual(sorted(self.glue.tables), sorted(n.split('.', 1)[1] for n in self.proposal['table_names'].values()))

    def test_fresh_round_never_starts_over_an_existing_catalog_name(self):
        name = self.proposal['table_names']['sbom_inventory_v1'].split('.', 1)[1]
        self.glue.tables[name] = dict(Name=name, DatabaseName='sbom_analytics', TableType='VIRTUAL_VIEW')
        with self.assertRaisesRegex(IngestionError, 'ATHENA_CATALOG_NAME_CONFLICT'):
            a.run(self.s3, self.sts, self.athena, self.glue, self.expected, self.settings, self.session,
                  'sbom-analytics-v1-r1', self.root / 'reports', self.root / 'recovered',
                  authorized_sha256=sha256(self.raw), authorization_reference=AUTH)
        self.assertEqual(self.athena.calls, [])

    def test_fresh_round_cli_requires_authorization_and_no_history(self):
        athena = self.root / 'athena.json'; athena.write_bytes(canonical(self.settings))
        base = ['--config', str(ACTIVE), '--athena-config', str(athena), '--output', str(self.root / 'out'),
                '--session-name', self.session, '--round-id', 'sbom-analytics-v1-r1']
        auth = ['--authorized-plan-sha256', sha256(self.raw), '--authorization-reference', AUTH]

        def main(report, *extra):
            with patch.object(a, 'aws_clients', side_effect=ServiceError(403, 'AccessDenied')) as clients, \
                    redirect_stdout(io.StringIO()):
                status = a.main(base + ['--report', str(report)] + list(extra))
            return status, json.loads(report.read_bytes())['code'], clients.called

        self.assertEqual(main(self.root / 'a/result.json', '--fresh-round'), (1, 'ATHENA_PLAN_RESTORE_FORBIDDEN', False))
        receipt = self.root / 'b/resume-receipt.json'; receipt.parent.mkdir(); receipt.write_text('{}')
        self.assertEqual(main(self.root / 'b/result.json', '--fresh-round', '--resume-receipt', str(receipt), *auth),
                         (1, 'ATHENA_FRESH_ROUND_HISTORY_PRESENT', False))
        journal = self.root / 'c/execution-journal.json'; journal.parent.mkdir(); journal.write_text('{}')
        self.assertEqual(main(self.root / 'c/result.json', '--fresh-round', *auth),
                         (1, 'ATHENA_FRESH_ROUND_HISTORY_PRESENT', False))
        self.assertEqual(main(self.root / 'd/result.json', *auth), (1, 'ATHENA_VERIFIED_RESTORE_REQUIRED', False))
        # A valid fresh start reaches only the (failing, fake) credential boundary.
        self.assertEqual(main(self.root / 'e/result.json', '--fresh-round', *auth), (1, 'AccessDenied', True))


class ActiveWorkflowTests(unittest.TestCase):
    def load(self, name):
        return yaml.load((ROOT / '.github/workflows' / name).read_text(), Loader=yaml.BaseLoader)

    def test_active_workflows_are_named_for_the_product_and_never_overlap(self):
        for name, title in (('sbom-analytics-s3.yml', 'Distroless SBOM Analytics - S3 Snapshot'),
                            ('sbom-analytics-athena.yml', 'Distroless SBOM Analytics - Athena')):
            value, text = self.load(name), (ROOT / '.github/workflows' / name).read_text()
            self.assertEqual(value['name'], title)
            self.assertEqual(value['concurrency'], {'group': 'distroless-sbom-analytics', 'cancel-in-progress': 'false'})
            self.assertNotRegex(text, r'lab-poc|sbom-poc-|poc_distroless|poc-v1|lab-frozen-plan')
            self.assertEqual(set(value['on']), {'workflow_dispatch'})
        for old in ('sbom-analytics-lab-poc.yml', 'sbom-analytics-athena-lab-poc.yml'):
            self.assertFalse((ROOT / '.github/workflows' / old).exists())

    def test_athena_round_inputs_bind_the_new_snapshot_and_refuse_the_closed_round(self):
        value = self.load('sbom-analytics-athena.yml')
        inputs = value['on']['workflow_dispatch']['inputs']
        self.assertEqual(inputs['round_id']['default'], 'sbom-analytics-v1-r1')
        self.assertEqual((inputs['fresh_round']['type'], inputs['fresh_round']['default']), ('boolean', 'false'))
        steps = value['jobs']['athena']['steps']
        intent = steps[2]['run']
        self.assertIn("assert os.environ['ROUND_ID'] != 'lab-sbom-athena-v1'", intent)
        self.assertIn("assert not os.environ['RESUME_SOURCE'] and os.environ['FRESH_ROUND'] == 'false'", intent)
        restore = next(s for s in steps if s['name'] == 'Restore exact prior journal before AWS authentication')
        self.assertIn('--snapshot-id ' + SNAPSHOT, restore['run'])
        execution = next(s for s in steps if 'Recover S3 snapshot' in s['name'])['run']
        self.assertIn('--fresh-round)', execution)
        self.assertIn('policies/analytics/athena.json', execution)
        self.assertEqual(json.loads(ACTIVE.read_text())['snapshot_id'], SNAPSHOT)

    def test_no_active_input_names_the_historical_namespace(self):
        # infra/s3-legacy and the LEGACY_* contract constants name the replaced bucket on purpose.
        paths = [*(ROOT / 'policies/analytics').glob('*.json'), *(ROOT / 'infra/s3').glob('*.tf'),
                 *(ROOT / 'docs/examples/sbom-analytics').glob('*.json'), ROOT / 'scripts/pipeline/analytics/catalog.py']
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotRegex(path.read_text(), r'poc_distroless|poc_snapshot|poc-v1')



# A whole word "lab"/"poc" (not "available"), in any case.
MARK = re.compile(r'(?i)(?<![a-z])(lab|poc)(?![a-z])')
# Explicit exceptions: real historical identifiers and the existing deployment identity.
HISTORICAL_ALLOWED = ("'lab-sbom-athena-v1'", '`lab-sbom-athena-v1`')


class ActiveNamingTests(unittest.TestCase):
    """Product identifiers carry no historical mark; history keeps its real names elsewhere."""

    def marks(self, text, allowed=HISTORICAL_ALLOWED):
        return [line for line in text.splitlines() if MARK.search(line) and not any(a in line for a in allowed)]

    def test_workflow_names_groups_steps_and_artifacts(self):
        for name in ('sbom-analytics-s3.yml', 'sbom-analytics-athena.yml'):
            with self.subTest(workflow=name):
                text = (ROOT / '.github/workflows' / name).read_text()
                self.assertEqual(self.marks(text), [])
                self.assertIn('requirements-sbom-analytics.txt', text)
        # The single allowed mark is the refusal of the real closed round.
        athena = (ROOT / '.github/workflows/sbom-analytics-athena.yml').read_text()
        self.assertEqual([l.strip() for l in athena.splitlines() if MARK.search(l)],
                         ["assert os.environ['ROUND_ID'] != 'lab-sbom-athena-v1', 'The closed historical round is never reopened'"])

    def test_aws_creation_examples_and_active_configuration(self):
        examples = sorted((ROOT / 'docs/examples/sbom-analytics').glob('*.json'))
        self.assertEqual([p.name for p in examples], ['athena-policy-delta.json', 'athena-workgroup-proposal.json',
                                                     'glue-database-proposal.json'])
        self.assertFalse((ROOT / 'docs/examples/sbom-lab').exists())
        workgroup = json.loads((ROOT / 'docs/examples/sbom-analytics/athena-workgroup-proposal.json').read_text())
        database = json.loads((ROOT / 'docs/examples/sbom-analytics/glue-database-proposal.json').read_text())
        self.assertTrue(workgroup['Description'].startswith('Distroless SBOM Analytics'))
        self.assertTrue(database['DatabaseInput']['Description'].startswith('Distroless SBOM Analytics'))
        self.assertEqual((workgroup['Name'], database['DatabaseInput']['Name']), (NAMESPACE['workgroup'], NAMESPACE['database']))
        self.assertEqual(workgroup['Configuration']['ResultConfiguration']['OutputLocation'],
                         's3://' + BUCKET + '/' + NAMESPACE['results_prefix'])
        for path in [*examples, *(ROOT / 'policies/analytics').glob('*.json'), ACTIVE,
                     FIXTURES / 'frozen-plan-v1.json', ROOT / 'scripts/pipeline/analytics/catalog.py',
                     *(ROOT / 'infra/s3').glob('*.tf'), ROOT / 'infra/s3/README.md']:
            with self.subTest(path=path.relative_to(ROOT)):
                allowed = HISTORICAL_ALLOWED + (('sbom-analytics/poc-v1', 'query-results/poc-v1/')
                                               if path.name == 'README.md' else ())
                self.assertEqual(self.marks(path.read_text(), allowed), [])

    def test_iam_names_match_the_catalog_and_examples(self):
        policy = json.loads((ROOT / 'policies/aws/factory-distroless-v1.inline-policy.json').read_text())
        self.assertFalse([s['Sid'] for s in policy['Statement'] if MARK.search(s['Sid'])])
        delta = json.loads((ROOT / 'docs/examples/sbom-analytics/athena-policy-delta.json').read_text())
        self.assertEqual(delta['Statement'], policy['Statement'][11:14])
        encoded = json.dumps(delta)
        for name in (NAMESPACE['workgroup'], 'database/' + NAMESPACE['database'], NAMESPACE['table_prefix'] + '_' + SNAPSHOT,
                     BUCKET + '/' + NAMESPACE['results_prefix']):
            self.assertIn(name, encoded)
        self.assertEqual(self.marks(encoded), [])

    def test_entry_documentation_and_module_names(self):
        index = (ROOT / 'docs/README.md').read_text()
        rows = [l for l in index.splitlines() if 'sbom-analytics-' in l]
        self.assertEqual(len(rows), 2)
        self.assertIn('(sbom-analytics-operations.md)', rows[0]); self.assertIn('(sbom-analytics-migration.md)', rows[1])
        self.assertEqual(self.marks('\n'.join(rows)), [])
        operations = (ROOT / 'docs/sbom-analytics-operations.md').read_text()
        self.assertEqual(operations.splitlines()[0], '# Distroless SBOM Analytics — operação')
        # lab-image-base-infra is the existing deployment Environment (OIDC subject), not a product name.
        self.assertEqual(self.marks(operations, HISTORICAL_ALLOWED + ('`lab-image-base-infra`',)), [])
        self.assertFalse((ROOT / 'docs/sbom-analytics-lab-reset.md').exists())
        analytics = ROOT / 'scripts/pipeline/analytics'
        self.assertEqual(sorted(p.name for p in analytics.glob('*.py') if MARK.search(p.stem.replace('_', ' '))), [])
        self.assertFalse(list(ROOT.glob('requirements-*poc*.txt')))
        for module in ('s3_run.py', 'athena_run.py', 'athena_restore.py', 'catalog.py'):
            text = (analytics / module).read_text()
            self.assertNotRegex(text, r"'[A-Z_]*POC[A-Z_]*'|poc-package", module)


if __name__ == '__main__':
    unittest.main()
