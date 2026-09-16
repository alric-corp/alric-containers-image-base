"""Validate the corporate-like target ECR/trust policies for the Containers
role (target name alric-github-repo-1360616627; legacy live name
github-actions-image-base).

Pure data validation: reads the JSON files, asserts on their exact action
set, resource scoping and trust conditions. Never calls AWS. Never asserts
anything about the policy actually attached to the role in AWS today (that
was read once, in a prior session, and is only referenced here as a
documented historical constant for the diff in
policies/aws/corporate-like/README.md).
"""
from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[4]
TARGET_POLICY = ROOT / 'policies/aws/corporate-like/image-base-ecr-target.json'
TARGET_TRUST = ROOT / 'policies/aws/corporate-like/image-base-trust-target.json'
LIVE_TRUST = ROOT / 'policies/aws/github-actions-image-base-trust.json'
WORKFLOW = ROOT / '.github/workflows/build-base-images.yml'
PREFLIGHT = ROOT / 'scripts/pipeline/release/validate_ecr_repository.py'

# Real, read-only-discovered GitHub repository IDs (gh api repos/<owner>/<repo>
# --jq '.id'), never invented.
IMAGE_BASE_GITHUB_REPOSITORY_ID = '1360616627'
REGISTRY_GITHUB_REPOSITORY_ID = '1371995836'
ALRIC_CORP_OWNER_ID = '178685987'

EXPECTED_TARGET_ACTIONS = {
    'ecr:GetAuthorizationToken',
    'ecr:BatchCheckLayerAvailability',
    'ecr:BatchGetImage',
    'ecr:GetDownloadUrlForLayer',
    'ecr:InitiateLayerUpload',
    'ecr:UploadLayerPart',
    'ecr:CompleteLayerUpload',
    'ecr:PutImage',
    'ecr:CreateRepository',
    'ecr:DescribeRepositories',
    'ecr:ListImages',
    'ecr:DescribeImages',
    'ecr:GetRepositoryPolicy',
    'ecr:SetRepositoryPolicy',
    'ecr:DeleteRepositoryPolicy',
    'ecr:StartImageScan',
    'ecr:DescribeImageScanFindings',
    'ecr:PutImageScanningConfiguration',
    'ecr:TagResource',
    'ecr:UntagResource',
    'ecr:ListTagsForResource',
}

FORBIDDEN_FROM_TARGET = {
    'ecr:PutImageTagMutability',
    'ecr:GetLifecyclePolicy',
    'ecr:PutLifecyclePolicy',
    'ecr:BatchDeleteImage',
    'ecr:DeleteRepository',
}

LAB_ECR_PREFIX = 'arn:aws:ecr:us-east-1:712107929769:repository/'


def load(path):
    return json.loads(path.read_text())


def all_actions(document):
    actions = set()
    for statement in document['Statement']:
        action = statement['Action']
        actions.update(action if isinstance(action, list) else [action])
    return actions


class CorporateLikeTargetPolicyTests(unittest.TestCase):
    def setUp(self):
        self.document = load(TARGET_POLICY)

    def test_contains_exactly_the_decided_corporate_like_action_set(self):
        self.assertEqual(all_actions(self.document), EXPECTED_TARGET_ACTIONS)

    def test_does_not_contain_forbidden_actions(self):
        actions = all_actions(self.document)
        for forbidden in FORBIDDEN_FROM_TARGET:
            with self.subTest(action=forbidden):
                self.assertNotIn(forbidden, actions)

    def test_only_authorization_token_uses_wildcard_resource(self):
        wildcard = [s for s in self.document['Statement'] if s['Resource'] == '*']
        self.assertEqual(len(wildcard), 1)
        self.assertEqual(wildcard[0]['Sid'], 'EcrAuthorizationToken')

    def test_every_other_statement_scoped_to_image_base_namespace(self):
        for statement in self.document['Statement']:
            if statement['Sid'] == 'EcrAuthorizationToken':
                continue
            self.assertEqual(statement['Resource'], f'{LAB_ECR_PREFIX}image-base-*')

    def test_target_grants_more_than_the_publisher_uses(self):
        """Sanity check for the 'available != exercised' principle: the
        target intentionally includes provisioning actions the publisher
        must never call — both facts must hold at once."""
        actions = all_actions(self.document)
        provisioning_actions_present_in_target = {
            'ecr:CreateRepository', 'ecr:SetRepositoryPolicy',
            'ecr:PutImageScanningConfiguration',
        }
        self.assertTrue(provisioning_actions_present_in_target.issubset(actions))

    def test_publisher_still_never_calls_those_provisioning_actions(self):
        """Cross-check against the PREPROVISIONED_ONLY guard: adding these
        actions to the role's ceiling must never be read as license for the
        workflow to start using them."""
        normalized = (WORKFLOW.read_text() + PREFLIGHT.read_text()).lower()
        normalized = ''.join(ch for ch in normalized if ch.isalnum())
        for operation in ('createrepository', 'putimagetagmutability',
                          'putimagescanningconfiguration', 'setrepositorypolicy',
                          'putlifecyclepolicy'):
            with self.subTest(operation=operation):
                self.assertNotIn(operation, normalized)


class CorporateLikeTrustTargetTests(unittest.TestCase):
    def setUp(self):
        self.document = load(TARGET_TRUST)

    def test_single_statement_assume_role_with_web_identity(self):
        self.assertEqual(len(self.document['Statement']), 1)
        statement = self.document['Statement'][0]
        self.assertEqual(statement['Action'], 'sts:AssumeRoleWithWebIdentity')
        self.assertEqual(statement['Effect'], 'Allow')

    def test_federated_principal_is_the_existing_github_oidc_provider(self):
        statement = self.document['Statement'][0]
        self.assertEqual(
            statement['Principal']['Federated'],
            'arn:aws:iam::712107929769:oidc-provider/token.actions.githubusercontent.com')

    def test_subject_matches_the_live_immutable_format_unchanged(self):
        """The target does not relax or alter the subject the live trust
        already uses — it only adds independent conditions alongside it."""
        target_sub = self.document['Statement'][0]['Condition']['StringEquals']['token.actions.githubusercontent.com:sub']
        live = load(LIVE_TRUST)
        live_sub = live['Statement'][0]['Condition']['StringEquals']['token.actions.githubusercontent.com:sub']
        self.assertEqual(target_sub, live_sub)

    def test_repository_id_claim_is_present_and_correct(self):
        """AWS documents token.actions.githubusercontent.com:repository_id
        as a real STS condition key for this identity provider (IAM User
        Guide, "Available keys for AWS OIDC federation" -> GitHub tab) —
        confirmed against that page, not assumed."""
        statement = self.document['Statement'][0]
        self.assertEqual(
            statement['Condition']['StringEquals']['token.actions.githubusercontent.com:repository_id'],
            IMAGE_BASE_GITHUB_REPOSITORY_ID)

    def test_repository_owner_id_claim_is_present_and_correct(self):
        statement = self.document['Statement'][0]
        self.assertEqual(
            statement['Condition']['StringEquals']['token.actions.githubusercontent.com:repository_owner_id'],
            ALRIC_CORP_OWNER_ID)

    def test_does_not_accept_the_infra_repository(self):
        """Identity binding: the Containers trust must never accept the
        Infra repository's identity, by name or by id."""
        statement = self.document['Statement'][0]
        self.assertNotEqual(
            statement['Condition']['StringEquals']['token.actions.githubusercontent.com:repository_id'],
            REGISTRY_GITHUB_REPOSITORY_ID)
        self.assertNotIn('alric-containers-registry',
                         statement['Condition']['StringEquals']['token.actions.githubusercontent.com:sub'])


class LiveTrustUntouchedTests(unittest.TestCase):
    """This round reconciles naming/identity documents; it must not modify
    the trust actually applied in AWS today."""

    def test_live_trust_still_has_a_single_name_based_subject_no_repository_id_condition(self):
        live = load(LIVE_TRUST)
        statement = live['Statement'][0]
        self.assertEqual(
            statement['Condition']['StringEquals']['token.actions.githubusercontent.com:sub'],
            'repo:alric-corp@178685987/alric-containers-image-base@1360616627:ref:refs/heads/main')
        self.assertNotIn('token.actions.githubusercontent.com:repository_id',
                         statement['Condition']['StringEquals'])


if __name__ == '__main__':
    unittest.main()
