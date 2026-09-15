"""Offline structure checks for the P1-02 lab IAM/ECR proposal.

Static checks only; never assumes the role, never calls AWS, never asserts
effective AWS authorization. This proposal has no renderer (values are
already concrete for a fixed two-repository sandbox lab, unlike the
parameterized catalog-wide policies/aws/proposals/factory-permissions/),
so this test reads the JSON files directly instead of exercising
tools/render_iam_proposal.py, which remains exclusive to that other
proposal (see test_iam_proposal.py).
"""
import fnmatch
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

from tools.check_ai_context import link_targets

ROOT = Path(__file__).resolve().parents[4]
PROPOSAL = ROOT / 'policies/aws/proposals/p102-lab-permissions'
ACCOUNT_ID = '712107929769'
REGION = 'us-east-1'
ROLE_NAME = 'github-actions-image-base-p102-lab'
LAB_REPOSITORIES = ('p102-lab-go1-26', 'p102-lab-go1-26-dev')
LAB_ARNS = {f'arn:aws:ecr:{REGION}:{ACCOUNT_ID}:repository/{name}' for name in LAB_REPOSITORIES}
GITHUB_REPOSITORY = 'alric-corp/alric-containers-image-base'
GITHUB_REPOSITORY_ID = '1360616627'
GITHUB_OWNER_ID = '178685987'
GITHUB_SUB = f'repo:alric-corp@{GITHUB_OWNER_ID}/alric-containers-image-base@{GITHUB_REPOSITORY_ID}:ref:refs/heads/main'
JOB_WORKFLOW_REF = f'{GITHUB_REPOSITORY}/.github/workflows/partial-retry-lab.yml@refs/heads/main'
FORBIDDEN_EXECUTION_ACTIONS = {
    'ecr:CreateRepository', 'ecr:PutImageTagMutability',
    'ecr:PutImageScanningConfiguration', 'ecr:TagResource', 'ecr:ListTagsForResource',
}


def strict_load(path):
    """Load JSON while raising on duplicate keys, unlike json.load's silent last-wins."""
    def reject_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError(f'duplicate key {key!r} in {path.name}')
            seen[key] = value
        return seen
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def all_actions(statement):
    action = statement['Action']
    return set(action) if isinstance(action, list) else {action}


def all_resources(statement):
    resource = statement.get('Resource')
    if resource is None:
        return []
    return resource if isinstance(resource, list) else [resource]


class ProposalFilesTests(unittest.TestCase):
    def setUp(self):
        self.execution = strict_load(PROPOSAL / 'execution.identity.template.json')
        self.provisioning = strict_load(PROPOSAL / 'provisioning.identity.template.json')
        self.trust_primary = strict_load(PROPOSAL / 'trust.template.json')
        self.trust_fallback = strict_load(PROPOSAL / 'trust.template.fallback-no-job-workflow-ref.json')

    def test_all_proposal_json_files_parse_without_duplicate_keys(self):
        for path in sorted(PROPOSAL.glob('*.json')):
            with self.subTest(path=path.name):
                document = strict_load(path)
                self.assertEqual(document['Version'], '2012-10-17')
                self.assertTrue(document['Statement'])

    def test_lab_repository_names_fall_outside_the_operational_wildcard(self):
        # Guards against a future rename silently recreating the original finding.
        for name in LAB_REPOSITORIES:
            with self.subTest(name=name):
                self.assertFalse(name.startswith('image-base-'))
                self.assertFalse(fnmatch.fnmatchcase(name, 'image-base-*'))

    def test_execution_and_provisioning_use_only_exact_lab_arns(self):
        for policy_name, policy in (('execution', self.execution), ('provisioning', self.provisioning)):
            for statement in policy['Statement']:
                with self.subTest(policy=policy_name, sid=statement['Sid']):
                    resources = all_resources(statement)
                    if resources == ['*']:
                        self.assertEqual(all_actions(statement), {'ecr:GetAuthorizationToken'})
                        continue
                    for arn in resources:
                        self.assertNotIn('*', arn)
                        self.assertNotIn('?', arn)
                        self.assertIn(arn, LAB_ARNS)
                        self.assertNotIn('repository/image-base-', arn)

    def test_only_authorization_token_uses_the_global_resource(self):
        wildcard_statements = []
        for policy in (self.execution, self.provisioning):
            for statement in policy['Statement']:
                if all_resources(statement) == ['*']:
                    wildcard_statements.append(statement)
        self.assertEqual(len(wildcard_statements), 1)
        self.assertEqual(all_actions(wildcard_statements[0]), {'ecr:GetAuthorizationToken'})

    def test_no_ecr_wildcard_action_and_no_other_service_grants(self):
        for policy in (self.execution, self.provisioning):
            for statement in policy['Statement']:
                for action in all_actions(statement):
                    self.assertNotEqual(action, 'ecr:*')
                    self.assertTrue(action.startswith('ecr:'), action)
                    for other_service in ('s3:', 'kms:', 'secretsmanager:', 'iam:', 'sts:'):
                        self.assertFalse(action.startswith(other_service), action)

    def test_execution_profile_excludes_provisioning_and_operational_actions(self):
        execution_actions = {action for statement in self.execution['Statement']
                             for action in all_actions(statement)}
        self.assertFalse(execution_actions & FORBIDDEN_EXECUTION_ACTIONS,
                         execution_actions & FORBIDDEN_EXECUTION_ACTIONS)

    def test_provisioning_is_create_repository_only_without_put_image_tag_mutability(self):
        provisioning_actions = {action for statement in self.provisioning['Statement']
                                for action in all_actions(statement)}
        self.assertEqual(provisioning_actions, {'ecr:CreateRepository'})

    def test_execution_and_provisioning_actions_are_disjoint(self):
        execution_actions = {action for statement in self.execution['Statement']
                             for action in all_actions(statement)}
        provisioning_actions = {action for statement in self.provisioning['Statement']
                                for action in all_actions(statement)}
        self.assertFalse(execution_actions & provisioning_actions)

    def test_trust_primary_binds_repository_ids_ref_and_job_workflow_ref_with_string_equals_only(self):
        statement = self.trust_primary['Statement'][0]
        self.assertEqual(len(self.trust_primary['Statement']), 1)
        self.assertEqual(statement['Effect'], 'Allow')
        self.assertEqual(statement['Action'], 'sts:AssumeRoleWithWebIdentity')
        self.assertEqual(statement['Principal'], {
            'Federated': f'arn:aws:iam::{ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com'})
        self.assertEqual(set(statement['Condition']), {'StringEquals'})
        expected = {
            'aud': 'sts.amazonaws.com', 'sub': GITHUB_SUB, 'repository': GITHUB_REPOSITORY,
            'repository_id': GITHUB_REPOSITORY_ID, 'repository_owner_id': GITHUB_OWNER_ID,
            'ref': 'refs/heads/main', 'job_workflow_ref': JOB_WORKFLOW_REF,
        }
        self.assertEqual(statement['Condition']['StringEquals'], {
            'token.actions.githubusercontent.com:' + key: value for key, value in expected.items()})
        # Equality above also rejects StringLike and any wildcarded claim value.
        self.assertNotIn('*', json.dumps(statement))

    def test_trust_fallback_keeps_exact_conditions_but_omits_job_workflow_ref(self):
        statement = self.trust_fallback['Statement'][0]
        self.assertEqual(set(statement['Condition']), {'StringEquals'})
        conditions = statement['Condition']['StringEquals']
        self.assertNotIn('token.actions.githubusercontent.com:job_workflow_ref', conditions)
        expected = {
            'aud': 'sts.amazonaws.com', 'sub': GITHUB_SUB, 'repository': GITHUB_REPOSITORY,
            'repository_id': GITHUB_REPOSITORY_ID, 'repository_owner_id': GITHUB_OWNER_ID,
            'ref': 'refs/heads/main',
        }
        self.assertEqual(conditions, {
            'token.actions.githubusercontent.com:' + key: value for key, value in expected.items()})
        self.assertNotIn('*', json.dumps(statement))

    def test_trust_documents_are_reviewably_small(self):
        for name, document in (('trust.template.json', self.trust_primary),
                              ('trust.template.fallback-no-job-workflow-ref.json', self.trust_fallback)):
            with self.subTest(name=name):
                self.assertLessEqual(len(json.dumps(document, separators=(',', ':'))), 2048)
        for name, document in (('execution.identity.template.json', self.execution),
                              ('provisioning.identity.template.json', self.provisioning)):
            with self.subTest(name=name):
                self.assertLessEqual(len(json.dumps(document, separators=(',', ':'))), 6144)


class ReadmeConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.text = (PROPOSAL / 'README.md').read_text()

    def test_readme_names_the_proposed_role_and_both_lab_repositories(self):
        self.assertIn(ROLE_NAME, self.text)
        for name in LAB_REPOSITORIES:
            self.assertIn(name, self.text)

    def test_readme_scope_block_uses_only_the_corrected_lab_arns(self):
        # "Por que os repos NÃO se chamam" legitimately mentions the discarded
        # image-base-p102-lab-* name as history; the actual scope block must not.
        match = re.search(r'## Escopo exato\n\n```text\n(.*?)\n```', self.text, re.DOTALL)
        self.assertIsNotNone(match, 'expected a fenced scope block')
        block = match.group(1)
        self.assertNotIn('image-base-p102-lab', block)
        for name in LAB_REPOSITORIES:
            self.assertIn(f'repository/{name}', block)

    def test_readme_preserves_not_applied_state_markers(self):
        for marker in ('PUBLICATION_INFRA_DESIGN = PROPOSED',
                      'PUBLICATION_INFRA_APPLIED = NO', 'AWS_EXECUTION = NOT RUN'):
            self.assertIn(marker, self.text)

    def test_readme_recommends_plain_immutable_without_stable_exclusion(self):
        match = re.search(r'## ECR:.*?\n```text\n(.*?)\n```', self.text, re.DOTALL)
        self.assertIsNotNone(match, 'expected a fenced ECR configuration block')
        block = match.group(1)
        self.assertIn('IMMUTABLE', block)
        self.assertNotIn('EXCLUSION', block.upper())
        self.assertNotIn('stable', block.lower())

    def test_readme_marks_job_workflow_ref_trust_as_primary_and_the_other_as_fallback(self):
        self.assertIn('trust.template.json](trust.template.json) | **Primária.**', self.text)
        fallback_line = next(line for line in self.text.splitlines() if 'fallback-no-job-workflow-ref.json' in line and '|' in line)
        self.assertIn('Fallback', fallback_line)

    def test_readme_states_stable_isolation_guard_is_not_yet_implemented(self):
        self.assertIn('ainda não existe', self.text)

    def test_proposal_directory_has_no_stray_files_from_earlier_revision(self):
        self.assertFalse((PROPOSAL / 'trust.template.tightened-optional.json').exists())


class ProposalIsolationTests(unittest.TestCase):
    def test_proposal_is_not_referenced_by_active_workflows_or_pipeline_code(self):
        for directory in (ROOT / '.github/workflows', ROOT / 'scripts/pipeline'):
            for path in directory.rglob('*'):
                if path.suffix not in ('.py', '.yml', '.yaml'):
                    continue
                with self.subTest(path=path.relative_to(ROOT)):
                    text = path.read_text()
                    self.assertNotIn('proposals/p102-lab-permissions', text)

    def test_operational_role_and_repositories_are_not_the_chosen_target(self):
        readme = (PROPOSAL / 'README.md').read_text()
        # The operational ARN only appears in the "why not reuse" explanation;
        # it must never be the Resource of a Statement in the new templates.
        for path in PROPOSAL.glob('*.json'):
            with self.subTest(path=path.name):
                self.assertNotIn('image-base-go1-26', path.read_text())
        self.assertIn('image-base-go1-26', readme)  # explained as the reason for isolation, not applied

    def test_document_links_resolve(self):
        for document in (PROPOSAL / 'README.md',):
            for target in link_targets(document.read_text()):
                parsed = urlsplit(target)
                if parsed.scheme in ('http', 'https', 'mailto') or not parsed.path:
                    continue
                with self.subTest(document=document.relative_to(ROOT), target=target):
                    self.assertFalse(parsed.scheme or parsed.netloc)
                    destination = (document.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(destination.is_relative_to(ROOT))
                    self.assertTrue(destination.exists())


if __name__ == '__main__':
    unittest.main()
