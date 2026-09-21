"""Consumer certification is manual, isolated, complete, and read-only."""
import json
from pathlib import Path
import re
import unittest

import yaml

from scripts.pipeline.consumer_apps.model import ARCHITECTURES, CATALOG, SCENARIOS
from scripts.pipeline.governance import lint_workflow_hardening, pin_inventory


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / '.github/workflows/app-certification.yml'
READ_ACTIONS = {
    'ecr:GetAuthorizationToken', 'ecr:DescribeImages', 'ecr:DescribeRepositories',
    'ecr:BatchGetImage', 'ecr:GetDownloadUrlForLayer', 'ecr:BatchCheckLayerAvailability',
}


def action_steps(job, action):
    return [step for step in job['steps']
            if step.get('uses', '').split('@')[0] == action]


class AppCertificationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        cls.document = yaml.safe_load(cls.text)
        cls.jobs = cls.document['jobs']

    def test_dispatch_only_has_one_required_run_input_without_default(self):
        self.assertEqual(self.document['name'], 'Distroless - App certification')
        events = self.document.get('on', self.document.get(True))
        self.assertEqual(set(events), {'workflow_dispatch'})
        inputs = events['workflow_dispatch']['inputs']
        self.assertEqual(set(inputs), {'source-run-id'})
        self.assertEqual(inputs['source-run-id']['type'], 'string')
        self.assertIs(inputs['source-run-id']['required'], True)
        self.assertNotIn('default', inputs['source-run-id'])
        self.assertEqual(self.jobs['inventory']['if'],
                         "github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch'")

    def test_exact_eighteen_real_execution_legs_keep_failure_isolation(self):
        job = self.jobs['applications']
        self.assertEqual(job['needs'], 'inventory')
        self.assertIs(job['strategy']['fail-fast'], False)
        matrix = job['strategy']['matrix']
        self.assertEqual(set(matrix), {'framework', 'architecture'})
        self.assertEqual(matrix['framework'], [item['framework'] for item in SCENARIOS])
        self.assertEqual(matrix['architecture'], list(ARCHITECTURES))
        self.assertEqual(len(matrix['framework']) * len(matrix['architecture']), 18)
        execution = [step for step in job['steps']
                     if 'consumer_apps.runner' in step.get('run', '')]
        self.assertEqual(len(execution), 1)
        self.assertEqual(execution[0]['env'], {
            'FRAMEWORK': '${{ matrix.framework }}',
            'ARCHITECTURE': '${{ matrix.architecture }}',
        })
        self.assertIn('--framework "$FRAMEWORK" --architecture "$ARCHITECTURE"',
                      execution[0]['run'])
        self.assertNotIn('continue-on-error', execution[0])

    def test_scenarios_cover_the_complete_catalog_without_silently_skipping_dev(self):
        covered = [item['framework'] for item in SCENARIOS]
        dev = [item['dev_framework'] for item in SCENARIOS if item['dev_framework']]
        self.assertEqual(len(dev), 7)
        self.assertEqual(len(covered), 9)
        self.assertEqual(len(set(covered + dev)), 16)
        self.assertEqual(sorted(covered + dev), sorted(CATALOG))
        self.assertEqual(sorted(CATALOG),
                         sorted(path.stem for path in (ROOT / 'frameworks').glob('*.yaml')))

    def test_resolver_uses_only_explicit_source_run_and_authenticated_registry(self):
        steps = self.jobs['inventory']['steps']
        resolver = [step for step in steps if 'consumer_apps.inventory' in step.get('run', '')]
        self.assertEqual(len(resolver), 1)
        self.assertEqual(resolver[0]['env'], {
            'GH_TOKEN': '${{ github.token }}',
            'SOURCE_RUN_ID': '${{ inputs.source-run-id }}',
            'REPOSITORY': '${{ github.repository }}',
            'REGISTRY': '${{ steps.ecr.outputs.registry }}',
        })
        self.assertIn('inventory "$SOURCE_RUN_ID"', resolver[0]['run'])
        self.assertIn('--output reports/app-certification/candidate-inventory.json',
                      resolver[0]['run'])
        credentials = action_steps(self.jobs['inventory'], 'aws-actions/configure-aws-credentials')[0]
        validation = next(step for step in steps if step.get('name') ==
                          'Validate source run before AWS authentication')
        self.assertLess(steps.index(validation), steps.index(credentials))

    def test_oidc_sessions_cannot_use_publisher_write_capabilities(self):
        self.assertEqual(self.document['permissions'], {'contents': 'read'})
        for name in ('inventory', 'applications'):
            with self.subTest(job=name):
                job = self.jobs[name]
                self.assertEqual(job['permissions'], {
                    'contents': 'read', 'actions': 'read', 'id-token': 'write',
                })
                credentials = action_steps(job, 'aws-actions/configure-aws-credentials')
                self.assertEqual(len(credentials), 1)
                config = credentials[0]['with']
                self.assertEqual(config['role-to-assume'], '${{ vars.AWS_ROLE_ARN }}')
                self.assertEqual(config['allowed-account-ids'], '${{ vars.AWS_ACCOUNT_ID }}')
                self.assertNotIn('aws-access-key-id', config)
                self.assertNotIn('aws-secret-access-key', config)
                policy = json.loads(config['inline-session-policy'])
                self.assertEqual(policy['Version'], '2012-10-17')
                statements = policy['Statement']
                self.assertEqual(len(statements), 2)
                self.assertEqual({action for item in statements for action in item['Action']},
                                 READ_ACTIONS)
                self.assertTrue(all(item['Effect'] == 'Allow' for item in statements))
                for item in statements:
                    self.assertNotIn('NotAction', item)
                    if item['Action'] == ['ecr:GetAuthorizationToken']:
                        self.assertEqual(item['Resource'], '*')
                    else:
                        self.assertEqual(item['Resource'],
                                         'arn:aws:ecr:${{ vars.AWS_REGION }}:'
                                         '${{ vars.AWS_ACCOUNT_ID }}:repository/image-base-*')
        self.assertEqual(self.jobs['summary']['permissions'], {'contents': 'read', 'actions': 'read'})
        self.assertEqual(action_steps(self.jobs['summary'], 'aws-actions/configure-aws-credentials'), [])

    def test_no_publication_release_terraform_or_mutable_candidate_reference(self):
        forbidden = (
            r'\bdocker\s+push\b', r'\b(?:put-image|initiate-layer-upload|upload-layer-part|'
            r'complete-layer-upload|create-repository|delete-repository)\b',
            r'\b(?:PutImage|InitiateLayerUpload|UploadLayerPart|CompleteLayerUpload|'
            r'CreateRepository|DeleteRepository)\b', r'\bterraform\b',
            r'promote-stable\.yml', r'recover-stable\.yml', r'build-base-images\.yml',
            r'STABLE_PROMOTION_AUTHORIZED', r':(?:stable|latest)\b',
            r'validated-oci-',
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.text, pattern)
        for job in self.jobs.values():
            self.assertNotIn('uses', job)

    def test_certification_does_not_hold_publisher_or_stable_mutation_lock(self):
        self.assertEqual(self.document['concurrency'], {
            'group': 'app-certification-${{ github.repository }}-${{ inputs.source-run-id }}',
            'cancel-in-progress': False,
        })
        self.assertNotIn('factory-build-publish-', self.text)
        self.assertNotIn('stable-mutation-', self.text)
        self.assertTrue(all('concurrency' not in job for job in self.jobs.values()))

    def test_immutable_qemu_pattern_executes_only_for_arm64_and_is_managed(self):
        steps = action_steps(self.jobs['applications'], 'docker/setup-qemu-action')
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step['if'], "matrix.architecture == 'arm64'")
        self.assertEqual(step['with']['platforms'], 'arm64')
        self.assertRegex(step['with']['image'],
                         r'^docker\.io/tonistiigi/binfmt:qemu-v[0-9.]+-[0-9]+@sha256:[0-9a-f]{64}$')
        existing = yaml.safe_load((ROOT / '.github/workflows/image-trust.yml').read_text())
        governed = action_steps(existing['jobs']['trust'], 'docker/setup-qemu-action')[0]
        self.assertEqual(step['uses'], governed['uses'])
        paths = [WORKFLOW]
        managed = pin_inventory.coverage(pin_inventory.pins(paths),
                    pin_inventory.renovate_matches(json.loads((ROOT / 'renovate.json').read_text()), paths),
                    {'github-actions'})
        self.assertEqual(pin_inventory.lint(managed), [])

    def test_downloads_bind_current_repository_run_and_artifact_integrity(self):
        found = []
        for job in self.jobs.values():
            for step in action_steps(job, 'actions/download-artifact'):
                config = step['with']
                self.assertEqual(config['repository'], '${{ github.repository }}')
                self.assertEqual(config['run-id'], '${{ github.run_id }}')
                self.assertEqual(config['github-token'], '${{ github.token }}')
                self.assertEqual(config['digest-mismatch'], 'error')
                self.assertIs(config['merge-multiple'], False)
                found.append(step)
        self.assertEqual(len(found), 3)
        self.assertEqual(found[0]['with']['name'],
                         'app-certification-inventory-${{ github.run_attempt }}')

    def test_failed_legs_preserve_evidence_and_summary_still_runs(self):
        policy = json.loads((ROOT / 'policies/operations/health.json').read_text())
        self.assertEqual(policy['retention_days']['app-certification-'], 30)
        for job in self.jobs.values():
            for step in action_steps(job, 'actions/upload-artifact'):
                self.assertEqual(step['with']['retention-days'], 30)
        uploads = action_steps(self.jobs['applications'], 'actions/upload-artifact')
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]['if'], 'always()')
        self.assertEqual(uploads[0]['with']['if-no-files-found'], 'error')
        self.assertIn('${{ matrix.framework }}-${{ matrix.architecture }}',
                      uploads[0]['with']['name'])
        self.assertIn('reports/app-certification/${{ matrix.framework }}-${{ matrix.architecture }}-logs/',
                      uploads[0]['with']['path'].splitlines())
        summary = self.jobs['summary']
        self.assertEqual(summary['needs'], ['inventory', 'applications'])
        self.assertEqual(summary['if'], "always() && needs.inventory.result == 'success'")
        downloads = action_steps(summary, 'actions/download-artifact')
        self.assertEqual(downloads[-1]['with']['pattern'],
                         'app-certification-result-*-${{ github.run_attempt }}')
        checks = [step for step in summary['steps']
                  if 'consumer_apps.summary' in step.get('run', '')]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['if'], 'always()')
        self.assertNotIn('continue-on-error', checks[0])
        self.assertIn('--markdown "$GITHUB_STEP_SUMMARY"', checks[0]['run'])
        self.assertEqual(checks[0]['env']['DOWNLOAD_OUTCOME'], '${{ steps.results.outcome }}')
        self.assertIn('--download-result "$DOWNLOAD_OUTCOME"', checks[0]['run'])
        integrity = next(step for step in summary['steps'] if step.get('name') ==
                         'Reject any result download integrity failure')
        self.assertEqual(integrity['env']['DOWNLOAD_OUTCOME'], '${{ steps.results.outcome }}')
        self.assertEqual(integrity['run'].strip(), 'test "$DOWNLOAD_OUTCOME" = success')

    def test_actions_pins_and_hardening_preserve_repository_governance(self):
        self.assertEqual(lint_workflow_hardening.check(WORKFLOW.name, self.document), [])
        for job in self.jobs.values():
            self.assertEqual(job['runs-on'], 'ubuntu-latest')
            self.assertGreater(job['timeout-minutes'], 0)
            for step in job['steps']:
                if 'uses' in step:
                    self.assertIsNotNone(re.fullmatch(r'[^@]+@[0-9a-f]{40}', step['uses']))


if __name__ == '__main__':
    unittest.main()
