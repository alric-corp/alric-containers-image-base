"""Security contracts for the separately owned Infra and publication identities.

Terraform mock tests exercise evaluated Infra policies; these Python tests also
cover the operator-applied publication policy and bootstrap ownership boundary.
"""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
IAM = ROOT / "infra/iam"
BUILD = json.loads((IAM / "build-publication-policy.json").read_text())


class IamBoundaryTests(unittest.TestCase):
    def test_publication_oidc_trust_allows_only_exact_develop_subject(self):
        trust = json.loads((ROOT / 'policies/aws/github-actions-image-base-trust.json').read_text())
        self.assertEqual(len(trust['Statement']), 1)
        statement = trust['Statement'][0]
        self.assertEqual(statement['Effect'], 'Allow')
        self.assertEqual(statement['Action'], 'sts:AssumeRoleWithWebIdentity')
        self.assertEqual(statement['Principal'], {
            'Federated': 'arn:aws:iam::712107929769:oidc-provider/token.actions.githubusercontent.com',
        })
        self.assertEqual(statement['Condition'], {'StringEquals': {
            'token.actions.githubusercontent.com:sub': (
                'repo:alric-corp@178685987/alric-containers-image-base@1360616627:ref:refs/heads/develop'),
            'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
        }})

    def test_build_publishes_only_to_exact_catalog(self):
        statements = BUILD["Statement"]
        self.assertEqual(BUILD["Version"], "2012-10-17")
        self.assertEqual(len(statements), 2)
        publication = statements[1]
        self.assertEqual(publication["Effect"], "Allow")
        self.assertEqual(set(publication["Resource"]), {
            f"arn:aws:ecr:us-east-1:712107929769:repository/image-base-{path.stem}"
            for path in (ROOT / "frameworks").glob("*.yaml")
        })
        self.assertEqual(set(publication["Action"]), {
            "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload",
            "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
            "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
            "ecr:DescribeRepositories", "ecr:DescribeImages", "ecr:ListImages",
            "ecr:GetRepositoryPolicy", "ecr:GetLifecyclePolicy", "ecr:ListTagsForResource",
        })
        self.assertTrue(all("*" not in arn and "?" not in arn for arn in publication["Resource"]))

    def test_build_global_resource_is_only_ecr_authentication(self):
        self.assertEqual(BUILD["Statement"][0], {
            "Sid": "EcrAuthentication", "Effect": "Allow",
            "Action": ["ecr:GetAuthorizationToken"], "Resource": "*",
            "Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-1"}},
        })
        # Managed IAM policies have a 6,144-character non-whitespace limit.
        self.assertLessEqual(len(json.dumps(BUILD, separators=(",", ":"))), 6144)

    def test_bootstrap_manages_only_new_roles_and_inline_policies(self):
        text = "\n".join(path.read_text() for path in sorted(IAM.glob("*.tf")))
        # The central role and its domain policies are additive; the Infra roles keep their addresses.
        self.assertEqual(re.findall(r'resource\s+"([^"]+)"\s+"([^"]+)"', text), [
            ("aws_iam_role", "factory_distroless_v1"), ("aws_iam_policy", "factory_distroless_v1"),
            ("aws_iam_role_policy_attachment", "factory_distroless_v1"),
            ("aws_iam_role", "infra"), ("aws_iam_role_policy", "infra"),
        ])
        self.assertIn('backend "local" {}', text)
        self.assertNotRegex(text, r'backend\s+"s3"|(?m:^\s*(?:import|moved)\s*\{)')
        self.assertNotRegex(text, r'resource\s+"aws_iam_openid_connect_provider"')
        self.assertIn('allowed_account_ids = [var.aws_account_id]', text)
        self.assertIn('fileset("${path.module}/../../frameworks", "*.yaml")', text)

    def test_infra_has_no_publication_or_permanent_destruction_actions(self):
        text = (IAM / "main.tf").read_text()
        actions = set(re.findall(r'"((?:ecr|s3|iam|sts):[A-Za-z*]+)"', text))
        self.assertFalse(actions & {
            "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
            "ecr:CompleteLayerUpload", "ecr:GetAuthorizationToken",
            "ecr:DeleteRepository", "ecr:BatchDeleteImage", "ecr:DeleteRepositoryPolicy",
            "ecr:DeleteLifecyclePolicy", "s3:DeleteBucket", "iam:PassRole",
        })
        self.assertTrue(all("*" not in action for action in actions))

    def test_oidc_has_exact_environment_and_pull_request_boundaries(self):
        text = (IAM / "main.tf").read_text()
        self.assertIn('plan  = "${var.github_subject_prefix}:pull_request"', text)
        self.assertIn('apply = "${var.github_subject_prefix}:environment:${var.github_apply_environment}"', text)
        self.assertNotIn("StringLike", text)
        self.assertNotIn(":ref:refs/heads/main", text)
        self.assertNotIn(":ref:refs/heads/develop", text)
        for claim in ("aud", "repository_id", "repository_owner_id", "sub"):
            self.assertIn(f'"token.actions.githubusercontent.com:{claim}"', text)
        lab = (IAM / "lab.tfvars").read_text()
        self.assertIn('"repo:alric-corp@178685987/alric-containers-image-base@1360616627"', lab)
        self.assertIn('"lab-image-base-infra"', lab)

    def test_state_is_read_only_for_plan_and_delete_is_lock_only(self):
        text = (IAM / "main.tf").read_text()
        self.assertIn('purpose == "plan" ? ["s3:GetObject"] : ["s3:GetObject", "s3:PutObject"]', text)
        self.assertEqual(text.count('"s3:DeleteObject"'), 1)
        self.assertRegex(text, r'Action\s*=\s*\["s3:GetObject", "s3:PutObject", "s3:DeleteObject"\]\s+Resource\s*=\s*\[local.lock_arn\]')
        self.assertIn('state_key  = "alric-containers-image-base/terraform.tfstate"', text)

    def test_global_infra_inventory_has_one_read_only_action_and_region(self):
        text = (IAM / "main.tf").read_text()
        self.assertEqual(text.count('Resource = ["*"]'), 1)
        self.assertRegex(text, r'Sid\s*=\s*"ReadOnlyRegionalRepositoryInventory"\s+Effect\s*=\s*"Allow"\s+Action\s*=\s*\["ecr:DescribeRepositories"\]\s+Resource\s*=\s*\["\*"\]')
        self.assertIn('StringEquals = { "aws:RequestedRegion" = var.aws_region }', text)

    def analytics(self, name):
        text = (IAM / "main.tf").read_text()
        return re.findall(r'"([a-z0-9]+:[A-Za-z]+)"', text.split(f"{name} = [", 1)[1].split("]", 1)[0])

    def test_analytics_bucket_is_one_exact_arn_in_the_ecr_region(self):
        text = (IAM / "main.tf").read_text()
        self.assertIn('analytics_bucket_arn = "arn:aws:s3:::alric-distroless-sbom-${var.aws_account_id}-${var.aws_region}"', text)
        # Rendered with the LAB values: the exact bucket the shared ECR state creates by default.
        lab = dict(re.findall(r'(?m)^(\w+)\s*=\s*"([^"]*)"', (IAM / "lab.tfvars").read_text()))
        self.assertEqual(f"arn:aws:s3:::alric-distroless-sbom-{lab['aws_account_id']}-{lab['aws_region']}",
                         "arn:aws:s3:::alric-distroless-sbom-712107929769-us-east-1")
        self.assertIn('"alric-distroless-sbom-${var.expected_bucket_owner}-${var.aws_region}"', (ROOT / "infra/ecr/s3.tf").read_text())
        self.assertRegex(text, r'Sid\s*=\s*"ExactSbomAnalyticsBucket"\s+Effect\s*=\s*"Allow"\s+'
                               r'Action\s*=\s*purpose == "plan" \? local.analytics_read_actions : '
                               r'concat\(local.analytics_read_actions, local.analytics_apply_actions\)\s+'
                               r'Resource\s*=\s*\[local.analytics_bucket_arn\]\s+Condition\s*=\s*\{\s*'
                               r'StringEquals\s*=\s*\{ "aws:RequestedRegion" = var.aws_region \}')
        self.assertEqual(text.count("local.analytics_bucket_arn"), 1)

    def test_analytics_plan_reads_and_apply_only_creates_and_configures(self):
        reads, writes = self.analytics("analytics_read_actions"), self.analytics("analytics_apply_actions")
        self.assertEqual(set(reads), {
            "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketAcl", "s3:GetBucketCORS", "s3:GetBucketWebsite",
            "s3:GetBucketVersioning", "s3:GetBucketLogging", "s3:GetBucketTagging", "s3:ListTagsForResource",
            "s3:GetBucketRequestPayment", "s3:GetAccelerateConfiguration", "s3:GetReplicationConfiguration",
            "s3:GetLifecycleConfiguration", "s3:GetEncryptionConfiguration", "s3:GetBucketObjectLockConfiguration",
            "s3:GetBucketPublicAccessBlock", "s3:GetBucketOwnershipControls", "s3:GetBucketPolicy",
        })
        self.assertTrue(all(action.split(":")[1].startswith(("Get", "List")) for action in reads))
        self.assertEqual(set(writes), {
            "s3:CreateBucket", "s3:PutBucketPublicAccessBlock", "s3:PutBucketOwnershipControls",
            "s3:PutEncryptionConfiguration", "s3:PutBucketVersioning", "s3:PutBucketPolicy",
            "s3:TagResource", "s3:PutBucketTagging",
        })
        self.assertEqual(len(reads) + len(writes), len(set(reads) | set(writes)))
        for action in reads + writes:
            # No object data access, deletion or wildcard on the analytics bucket.
            self.assertNotRegex(action, r"^s3:(Get|Put|Delete|Restore)Object|Delete|\*")
        for action in writes:
            # Configuration limited to the reviewed controls: no ACL, lifecycle, Object Lock, replication, untagging.
            self.assertNotRegex(action, r"Acl|Lifecycle|ObjectLock|Replication|Untag|Website|Cors|Logging|Accelerate|RequestPayment")

    def test_existing_statements_keep_their_order_and_the_new_one_is_last(self):
        text = (IAM / "main.tf").read_text()
        sids = re.findall(r'Sid\s*=\s*"([A-Za-z]+)"', text)
        self.assertEqual(sids, ["ExactProductIdentity", "ExactCatalogEcr", "EnsureExactBackendBucket",
                                "ExactDefaultWorkspaceState", "ExactDefaultWorkspaceLock",
                                "ReadOnlyRegionalRepositoryInventory", "ExactSbomAnalyticsBucket"])


class CentralFactoryRoleTests(unittest.TestCase):
    FACTORY = (IAM / "factory.tf").read_text()
    LIFECYCLE = (ROOT / "infra/lifecycle/main.tf").read_text()
    CONFIG = json.loads((ROOT / "policies/pipeline/config.json").read_text())

    def actions(self, text, name):
        return re.findall(r'"([a-z0-9]+:[A-Za-z]+)"', text.split(f"{name} = [", 1)[1].split("]", 1)[0])

    def test_exact_name_and_three_hour_sessions(self):
        variables = (IAM / "variables.tf").read_text()
        self.assertIn('default     = "itau-github-repo-factory-distroless-v1"', variables)
        self.assertIn("name                 = var.factory_role_name", self.FACTORY)
        self.assertIn("max_session_duration = 10800", self.FACTORY)
        self.assertNotIn("factory_role_name", (IAM / "lab.tfvars").read_text())

    def test_trust_accepts_only_two_protected_environments(self):
        self.assertIn('"${var.github_subject_prefix}:environment:${var.github_apply_environment}"', self.FACTORY)
        self.assertIn('"${var.github_subject_prefix}:environment:${var.factory_dev_environment}"', self.FACTORY)
        self.assertIn('default     = "DEV"', (IAM / "variables.tf").read_text())
        for forbidden in ("pull_request", "StringLike = { \"token", "ref:refs/heads", "repo:*", ":*\"", "AssumeRole\""):
            self.assertNotIn(forbidden, self.FACTORY)
        for claim in ("aud", "repository_id", "repository_owner_id", "sub"):
            self.assertIn(f'"token.actions.githubusercontent.com:{claim}"', self.FACTORY)
        self.assertEqual(self.FACTORY.count("sts:AssumeRoleWithWebIdentity"), 1)
        self.assertNotRegex(self.FACTORY, r'resource\s+"aws_iam_(openid_connect_provider|user|access_key)"')

    def test_policies_use_exact_arns(self):
        resources = re.findall(r'Resource\s*=\s*(\[[^\]]*\]|[a-z_.]+)', self.FACTORY)
        self.assertEqual(resources, ['["*"]', 'local.repository_arns', '[local.release_bucket_arn]',
                                     '["${local.release_bucket_arn}/*"]', '[local.sbom_snapshots_arn]',
                                     '[local.analytics_bucket_arn]'])
        self.assertRegex(self.FACTORY, r'Action\s*=\s*\["ecr:GetAuthorizationToken"\]\s+Resource\s*=\s*\["\*"\]\s+'
                                       r'Condition\s*=\s*\{\s*StringEquals = \{ "aws:RequestedRegion" = var.aws_region \}')
        self.assertIn('sbom_snapshots_arn = "${local.analytics_bucket_arn}/sbom-analytics/poc-v1/snapshots/*"', self.FACTORY)
        self.assertIn('release_bucket_arn = "arn:aws:s3:::${local.pipeline.DEV.release_bucket}"', self.FACTORY)
        self.assertEqual(self.CONFIG["DEV"]["release_bucket"], "712107929769-image-base-releases-dev")
        self.assertIn("infra = local.execution_policies[\"apply\"]", self.FACTORY)

    def test_no_new_destructive_or_administrative_actions(self):
        actions = set(re.findall(r'"((?:ecr|s3|iam|sts|athena|glue):[A-Za-z*]+)"', self.FACTORY))
        self.assertFalse({a for a in actions if re.search(r"Delete|\*|^iam:|^athena:|^glue:|PutBucketPolicy|PutBucketVersioning|PutLifecycle|SetRepositoryPolicy", a)})
        self.assertEqual(set(self.actions(self.FACTORY, "publication_push_actions")),
                         {"ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"})
        self.assertNotIn("BatchDeleteImage", self.FACTORY)
        self.assertNotIn("DeleteObjectVersion", self.FACTORY)

    def test_publication_reuses_the_proven_dev_actions(self):
        self.assertEqual(self.actions(self.FACTORY, "publication_read_actions"), re.findall(r'"(ecr:[A-Za-z]+)"', self.LIFECYCLE.split("read_actions = [", 1)[1].split("]", 1)[0]))
        self.assertEqual(self.actions(self.FACTORY, "publication_push_actions"), re.findall(r'"(ecr:[A-Za-z]+)"', self.LIFECYCLE.split("push_actions = [", 1)[1].split("]", 1)[0]))

    def test_backend_state_and_lock_addresses_are_unchanged(self):
        main = (IAM / "main.tf").read_text()
        self.assertIn('state_key  = "alric-containers-image-base/terraform.tfstate"', main)
        self.assertIn('lock_arn   = "${local.state_arn}.tflock"', main)
        self.assertEqual(self.CONFIG["infra"]["backend"], {"bucket": "712107929769-alric-containers-image-base-tfstate",
                                                          "region": "us-east-2", "key": "alric-containers-image-base/terraform.tfstate"})
        self.assertNotIn("backend", self.FACTORY.split("locals {", 1)[0])

    def test_legacy_roles_and_lifecycle_are_untouched(self):
        self.assertEqual(self.CONFIG["DEV"]["role_name"], "alric-image-base-factory-dev")
        self.assertEqual((self.CONFIG["infra"]["plan_role_name"], self.CONFIG["infra"]["apply_role_name"]),
                         ("alric-github-repo-1360616627-infra-plan", "alric-github-repo-1360616627-infra-apply"))
        self.assertIn('name                 = local.dev.role_name', self.LIFECYCLE)
        self.assertIn('resource "aws_iam_role" "dev"', self.LIFECYCLE)
        self.assertIn('name     = "${var.role_name_prefix}-${var.github_repository_id}-infra-${each.key}"'.replace('name     ', 'name                 '),
                      (IAM / "main.tf").read_text())

    def test_pull_request_infra_planning_stays_unprivileged(self):
        self.assertIs(self.CONFIG["infra"]["plan_enabled"], False)
        workflow = (ROOT / ".github/workflows/infra-pr.yml").read_text()
        self.assertIn("--scope INFRA_PLAN", workflow)
        self.assertNotIn("factory-distroless", workflow)
        self.assertNotIn("pull_request", self.FACTORY)

    def test_workflows_and_hom_are_not_switched_yet(self):
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            self.assertNotIn("factory-distroless", path.read_text(), path.name)
        self.assertNotIn("factory-distroless", (ROOT / "scripts/pipeline/governance/configuration.py").read_text())
        self.assertEqual(self.CONFIG["HOM"], {"account_id": "248908662184", "region": "sa-east-1",
                                             "role_name": "alric-image-base-factory-hom",
                                             "release_bucket": "248908662184-image-base-releases-hom"})
        self.assertNotIn("HOM", self.FACTORY)


if __name__ == "__main__":
    unittest.main()
