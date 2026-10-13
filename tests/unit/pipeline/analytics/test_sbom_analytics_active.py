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
BUCKET = 'distroless-sbom-analytics'
SNAPSHOT = '8439add73fe20e08d45292dddc62b360b6ccaa372395818aa0a5cf8a910eb507'
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

    def test_versioned_athena_configuration_binds_the_published_manifest(self):
        # Published by run 38207794810 and read back independently; never inferred.
        settings = a.config(ROOT / 'policies/analytics/athena.json')
        self.assertEqual(settings, athena_settings(
            manifest_sha256='5ff03abfbe76e016a7782851b32c9dedfc377e656e397979e544329feebcb829',
            manifest_version_id='7nr06MlNa4COnXXN1TCunE_lx3p5yEj2'))
        for execute in (False, True):
            self.assertLessEqual(len(json.dumps(a.session_policy(self.expected, settings, execute=execute),
                                                separators=(',', ':'))), 2048)
        self.assertEqual(self.marks_free((ROOT / 'policies/analytics/athena.json').read_text()), True)

    def marks_free(self, text):
        return not MARK.search(text) and not PERSONAL.search(text)

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
        intent = next(s for s in steps if s['name'] == 'Check intent and install pinned isolated dependencies')['run']
        self.assertIn("assert os.environ['ROUND_ID'] != 'lab-sbom-athena-v1'", intent)
        self.assertIn("assert not os.environ['RESUME_SOURCE'] and os.environ['FRESH_ROUND'] == 'false'", intent)
        restore = next(s for s in steps if s['name'] == 'Restore exact prior journal before AWS authentication')
        # Snapshot and repository are explicit inputs: versioned configuration and the running repository.
        self.assertIn("print(s3_run.config('policies/analytics/s3.json')['snapshot_id'])", restore['run'])
        self.assertIn('--snapshot-id "$SNAPSHOT_ID"', restore['run'])
        self.assertIn('--repository "$GITHUB_REPOSITORY" --repository-id "$GITHUB_REPOSITORY_ID"', restore['run'])
        for name in ('sbom-analytics-athena.yml', 'sbom-analytics-s3.yml'):
            self.assertNotRegex((ROOT / '.github/workflows' / name).read_text(), r'[0-9a-f]{64}|[0-9]{12}|us-east-1')
        execution = next(s for s in steps if 'Recover S3 snapshot' in s['name'])['run']
        self.assertIn('--fresh-round)', execution)
        self.assertIn('policies/analytics/athena.json', execution)
        self.assertEqual(json.loads(ACTIVE.read_text())['snapshot_id'], SNAPSHOT)

    IDENTITY_STEP = dict(name='Verify native execution identity before any credential', id='pipeline',
                         run='python3 -B -m scripts.pipeline.governance.configuration --scope DEV '
                             '--authorized-event workflow_dispatch')
    PRIVILEGED = re.compile(r'configure-aws-credentials|GH_TOKEN|gh api|athena_restore|s3_run (publish|recover)|'
                            r'athena_run|aws ')

    def jobs(self):
        for name in ('sbom-analytics-s3.yml', 'sbom-analytics-athena.yml'):
            for job_name, job in self.load(name)['jobs'].items():
                yield f'{name}:{job_name}', job

    def test_identity_is_verified_natively_before_any_privileged_step(self):
        seen = 0
        for label, job in self.jobs():
            with self.subTest(job=label):
                seen += 1
                # Branch and event guards stay; the repository is no longer a literal.
                self.assertEqual(job['if'], "github.ref == 'refs/heads/develop' && github.event_name == 'workflow_dispatch'")
                steps = job['steps']
                self.assertTrue(steps[0]['uses'].startswith('actions/checkout@'))
                self.assertEqual({k: steps[1].get(k) for k in ('name', 'id', 'run')}, self.IDENTITY_STEP)
                self.assertFalse({'if', 'continue-on-error', 'env'} & set(steps[1]))
                self.assertEqual(sum(s.get('id') == 'pipeline' for s in steps), 1)
                for index, step in enumerate(steps):
                    text = json.dumps(step)
                    if not self.PRIVILEGED.search(text):
                        continue
                    # Every privileged step comes after the identity check and only runs on success.
                    self.assertGreater(index, 1, step['name'])
                    self.assertNotRegex(step.get('if', ''), r'always\(\)|failure\(\)|cancelled\(\)', step['name'])
                    self.assertNotIn('continue-on-error', step)
                oidc = [s for s in steps if s.get('uses', '').startswith('aws-actions/configure-aws-credentials@')]
                self.assertEqual(len(oidc), 1)
                self.assertEqual(oidc[0]['with']['role-to-assume'], '${{ steps.pipeline.outputs.AWS_ROLE_ARN }}')
        self.assertEqual(seen, 3)

    def test_identity_failure_never_reaches_aws_authentication(self):
        from scripts.pipeline.governance import configuration
        env = {'GITHUB_REPOSITORY': 'alric-corp/alric-containers-image-base', 'GITHUB_REPOSITORY_OWNER': 'alric-corp',
               'GITHUB_REPOSITORY_ID': '1', 'GITHUB_REPOSITORY_OWNER_ID': '178685987',
               'GITHUB_REF': 'refs/heads/develop', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'output'
            env['GITHUB_OUTPUT'] = str(output)
            with patch.dict('os.environ', env, clear=True), patch('socket.socket', side_effect=AssertionError('network')), \
                    patch.object(a, 'aws_clients') as athena_clients, patch.object(s3_run, 'aws_clients') as s3_clients, \
                    self.assertRaises(ValueError):
                configuration.main(self.IDENTITY_STEP['run'].split()[4:])
            # The step fails: no AWS_ROLE_ARN output exists for the OIDC step, and no client was built.
            self.assertFalse(output.exists())
            athena_clients.assert_not_called(); s3_clients.assert_not_called()

    def test_no_repository_variables_secrets_or_dynamic_action_references(self):
        for name in ('sbom-analytics-s3.yml', 'sbom-analytics-athena.yml'):
            text = (ROOT / '.github/workflows' / name).read_text()
            with self.subTest(workflow=name):
                self.assertNotIn('vars.', text)
                self.assertNotIn('secrets.', text)
                for ref in re.findall(r'uses:\s*(\S+)', text):
                    self.assertRegex(ref, r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$')

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
# Personal/organization names never identify the product. The workflows learn
# their repository from the native github.* contexts and compare it with
# policies/pipeline/config.json; no repository literal remains in them.
PERSONAL = re.compile(r'(?i)alric')


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

    def test_product_identity_carries_no_personal_or_organization_name(self):
        config = json.loads((ROOT / 'policies/pipeline/config.json').read_text())
        self.assertEqual(config['analytics'], {'bucket': BUCKET})
        self.assertEqual(json.loads(ACTIVE.read_text())['destination']['bucket'], config['analytics']['bucket'])
        analytics = ROOT / 'scripts/pipeline/analytics'
        paths = [*analytics.glob('*.py'), *(ROOT / 'sql/sbom-analytics').rglob('*.sql'), ACTIVE,
                 *(ROOT / 'docs/examples/sbom-analytics').glob('*.json'), FIXTURES / 'frozen-plan-v1.json',
                 *(ROOT / 'infra/s3').glob('*.tf'), ROOT / 'docs/sbom-analytics-operations.md',
                 ROOT / 'requirements-sbom-analytics.txt']
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual([l for l in path.read_text().splitlines() if PERSONAL.search(l)], [])
        for name in ('sbom-analytics-s3.yml', 'sbom-analytics-athena.yml'):
            text = (ROOT / '.github/workflows' / name).read_text()
            self.assertEqual([l for l in text.splitlines() if PERSONAL.search(l)], [], name)
            self.assertNotRegex(text, r"github\.repository(_owner|_id|_owner_id)?\s*==|1360616627|178685987")
        policy = json.loads((ROOT / 'policies/aws/factory-distroless-v1.inline-policy.json').read_text())
        product = [s for s in policy['Statement'] if s['Sid'].startswith(('SbomSnapshot', 'SbomAnalytics'))]
        self.assertEqual(len(product), 5)
        self.assertFalse(PERSONAL.search(json.dumps(product)))
        bucket = next(s for s in policy['Statement'] if s['Sid'] == 'ExactSbomAnalyticsBucket')
        self.assertEqual(bucket['Resource'], ['arn:aws:s3:::' + BUCKET])

    def test_entry_documentation_and_module_names(self):
        # The index is organized by domain: the active operation document is the
        # canonical SBOM Analytics entry, and the closed LAB POC documents may
        # appear only in the dated history section.
        index = (ROOT / 'docs/README.md').read_text()
        sections = {block.split('\n', 1)[0]: block for block in index.split('\n## ')[1:]}
        rows = [l for l in sections['SBOM Analytics'].splitlines() if l.startswith('| ') and '](' in l]
        self.assertIn('(sbom-analytics-operations.md)', rows[0])
        self.assertTrue(any('(sbom-analytics-migration.md)' in l for l in rows))
        self.assertEqual(self.marks('\n'.join(rows)), [])
        current = [l for l in sections['Estado atual'].splitlines() if 'sbom-analytics-' in l]
        self.assertTrue(current)
        self.assertEqual(self.marks('\n'.join(current)), [])
        for name, block in sections.items():
            for document in ('sbom-analytics-lab-poc.md', 'sbom-analytics-athena-lab-poc.md'):
                if name != 'Histórico':
                    self.assertNotIn(document, block, name)
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
