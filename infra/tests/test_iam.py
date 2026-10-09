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
FIXTURE = IAM / "tests/fixtures/factory-distroless-v1.policy.json"
# AWS caps all inline policies of one role together, excluding whitespace.
IAM_INLINE_LIMIT = 10240


def grants(document):
    """Expand a policy into {(effect, resource, condition): actions}: the permissions it grants."""
    result = {}
    for statement in document["Statement"]:
        condition = json.dumps(statement.get("Condition"), sort_keys=True)
        for resource in statement["Resource"]:
            result.setdefault((statement["Effect"], resource, condition), set()).update(statement["Action"])
    return {key: frozenset(value) for key, value in result.items()}


def authorized_union(account, region, backend_bucket, backend_region, release_bucket, catalog):
    """Union of the four customer-managed policies of the previous review (PR head 6e16710), spelled out.

    Infra (Terraform), ECR, DEV release store and SBOM snapshots, grouped by resource and condition.
    """
    in_region = json.dumps({"StringEquals": {"aws:RequestedRegion": region}}, sort_keys=True)
    state = f"arn:aws:s3:::{backend_bucket}/alric-containers-image-base/terraform.tfstate"
    analytics = f"arn:aws:s3:::alric-distroless-sbom-{account}-{region}"
    terraform_ecr = {
        "ecr:DescribeRepositories", "ecr:GetRepositoryPolicy", "ecr:GetLifecyclePolicy", "ecr:ListTagsForResource",
        "ecr:DescribeImages", "ecr:CreateRepository", "ecr:PutLifecyclePolicy", "ecr:SetRepositoryPolicy",
        "ecr:TagResource", "ecr:UntagResource", "ecr:PutImageScanningConfiguration", "ecr:PutImageTagMutability",
    }
    publication_ecr = {
        "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability", "ecr:DescribeImages",
        "ecr:DescribeRepositories", "ecr:ListImages", "ecr:ListImageReferrers", "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
    }
    analytics_reads = {
        "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketAcl", "s3:GetBucketCORS", "s3:GetBucketWebsite",
        "s3:GetBucketVersioning", "s3:GetBucketLogging", "s3:GetBucketTagging", "s3:ListTagsForResource",
        "s3:GetBucketRequestPayment", "s3:GetAccelerateConfiguration", "s3:GetReplicationConfiguration",
        "s3:GetLifecycleConfiguration", "s3:GetEncryptionConfiguration", "s3:GetBucketObjectLockConfiguration",
        "s3:GetBucketPublicAccessBlock", "s3:GetBucketOwnershipControls", "s3:GetBucketPolicy",
    }
    analytics_writes = {
        "s3:CreateBucket", "s3:PutBucketPublicAccessBlock", "s3:PutBucketOwnershipControls",
        "s3:PutEncryptionConfiguration", "s3:PutBucketVersioning", "s3:PutBucketPolicy", "s3:TagResource",
        "s3:PutBucketTagging",
    }
    grants_by_scope = {
        ("Allow", f"arn:aws:ecr:{region}:{account}:repository/image-base-{name}", "null"): terraform_ecr | publication_ecr
        for name in catalog
    }
    grants_by_scope.update({
        ("Allow", "*", in_region): {"ecr:DescribeRepositories", "ecr:GetAuthorizationToken"},
        ("Allow", f"arn:aws:s3:::{backend_bucket}", json.dumps({"StringEquals": {"aws:RequestedRegion": backend_region}}, sort_keys=True)): {
            "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketVersioning", "s3:GetEncryptionConfiguration",
            "s3:GetBucketPublicAccessBlock", "s3:GetBucketOwnershipControls", "s3:CreateBucket",
            "s3:PutBucketPublicAccessBlock", "s3:PutBucketOwnershipControls", "s3:PutEncryptionConfiguration",
            "s3:PutBucketVersioning"},
        ("Allow", state, "null"): {"s3:GetObject", "s3:PutObject"},
        ("Allow", state + ".tflock", "null"): {"s3:GetObject", "s3:PutObject", "s3:DeleteObject"},
        ("Allow", analytics, in_region): analytics_reads | analytics_writes,
        ("Allow", analytics, json.dumps({"StringEquals": {"aws:RequestedRegion": region},
                                         "StringLike": {"s3:prefix": ["sbom-analytics/poc-v1/snapshots/*"]}}, sort_keys=True)): {"s3:ListBucket"},
        ("Allow", analytics + "/sbom-analytics/poc-v1/snapshots/*", in_region): {"s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"},
        ("Allow", f"arn:aws:s3:::{release_bucket}", "null"): {"s3:ListBucket"},
        ("Allow", f"arn:aws:s3:::{release_bucket}/*", "null"): {"s3:GetObject", "s3:PutObject"},
    })
    return {key: frozenset(value) for key, value in grants_by_scope.items()}


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
        # The central role and its single inline policy are additive; the Infra roles keep their addresses.
        self.assertEqual(re.findall(r'resource\s+"([^"]+)"\s+"([^"]+)"', text), [
            ("aws_iam_role", "factory_distroless_v1"), ("aws_iam_role_policy", "factory_distroless_v1"),
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
    MAIN = (IAM / "main.tf").read_text()
    VARIABLES = (IAM / "variables.tf").read_text()
    LIFECYCLE = (ROOT / "infra/lifecycle/main.tf").read_text()
    CONFIG = json.loads((ROOT / "policies/pipeline/config.json").read_text())
    LAB = dict(re.findall(r'(?m)^(\w+)\s*=\s*"([^"]*)"', (IAM / "lab.tfvars").read_text()))
    POLICY = json.loads(FIXTURE.read_text())
    CATALOG = sorted(path.stem for path in (ROOT / "frameworks").glob("*.yaml"))
    # Statements by responsibility: Terraform, ECR, DEV release store, SBOM snapshots.
    SIDS = ["EnsureExactBackendBucket", "ExactDefaultWorkspaceState", "ExactDefaultWorkspaceLock",
            "ReadOnlyRegionalRepositoryInventory", "ExactSbomAnalyticsBucket",
            "ExactCatalogEcr", "RegistryAuthentication",
            "DevReleaseInventory", "DevReleaseRecords",
            "SbomSnapshotObjects", "SbomSnapshotListing"]

    def actions(self, text, name):
        return re.findall(r'"([a-z0-9]+:[A-Za-z]+)"', text.split(f"{name} = [", 1)[1].split("]", 1)[0])

    def statement(self, sid):
        return next(item for item in self.POLICY["Statement"] if item["Sid"] == sid)

    def test_exact_name_and_three_hour_sessions(self):
        self.assertIn('default     = "itau-github-repo-factory-distroless-v1"', self.VARIABLES)
        self.assertIn("name                 = var.factory_role_name", self.FACTORY)
        self.assertIn("max_session_duration = 10800", self.FACTORY)
        self.assertNotIn("factory_role_name", (IAM / "lab.tfvars").read_text())

    def test_trust_accepts_only_two_protected_environments(self):
        self.assertIn('"${var.github_subject_prefix}:environment:${var.github_apply_environment}"', self.FACTORY)
        self.assertIn('"${var.github_subject_prefix}:environment:${var.factory_dev_environment}"', self.FACTORY)
        self.assertIn('default     = "DEV"', self.VARIABLES)
        for forbidden in ("pull_request", "StringLike = { \"token", "ref:refs/heads", "repo:*", ":*\"", "AssumeRole\""):
            self.assertNotIn(forbidden, self.FACTORY)
        for claim in ("aud", "repository_id", "repository_owner_id", "sub"):
            self.assertIn(f'"token.actions.githubusercontent.com:{claim}"', self.FACTORY)
        self.assertEqual(self.FACTORY.count("sts:AssumeRoleWithWebIdentity"), 1)
        self.assertNotRegex(self.FACTORY, r'resource\s+"aws_iam_(openid_connect_provider|user|access_key)"')

    def test_one_role_one_inline_policy_and_no_managed_policies_or_attachments(self):
        text = "\n".join(path.read_text() for path in sorted(IAM.glob("*.tf")))
        resources = re.findall(r'resource\s+"([^"]+)"\s+"([^"]+)"', text)
        self.assertEqual([item for item in resources if item[1] == "factory_distroless_v1"],
                         [("aws_iam_role", "factory_distroless_v1"), ("aws_iam_role_policy", "factory_distroless_v1")])
        self.assertFalse([item for item in resources if item[0] in (
            "aws_iam_policy", "aws_iam_role_policy_attachment", "aws_iam_policy_attachment", "aws_iam_group_policy",
            "aws_iam_user_policy", "aws_iam_role_policies_exclusive", "aws_iam_role_policy_attachments_exclusive")])
        self.assertIn('  name   = "factory-distroless-v1"', self.FACTORY)
        self.assertIn("  role   = aws_iam_role.factory_distroless_v1.name", self.FACTORY)
        self.assertIn("  policy = jsonencode(local.factory_policy)", self.FACTORY)
        self.assertRegex((IAM / "outputs.tf").read_text(), r'output "factory_policy" \{[^}]*value\s*=\s*local.factory_policy')
        self.assertNotIn("factory_policies", text)

    def test_statements_are_grouped_by_responsibility(self):
        self.assertEqual([item["Sid"] for item in self.POLICY["Statement"]], self.SIDS)
        self.assertEqual(len(self.POLICY["Statement"]), 11)
        # The five Terraform statements are the Infra apply ones, referenced by Sid and in this order.
        self.assertEqual(re.findall(r'local\.infra_apply_statements\["([A-Za-z]+)"\]', self.FACTORY), self.SIDS[:5])
        for sid in self.SIDS[:5]:
            self.assertEqual(len(re.findall(rf'Sid\s*=\s*"{sid}"', self.MAIN)), 1, sid)
        for sid in self.SIDS[5:]:
            self.assertEqual(len(re.findall(rf'Sid\s*=\s*"{sid}"', self.FACTORY)), 1, sid)

    def test_inline_policy_fits_the_iam_limit(self):
        compact = json.dumps(self.POLICY, separators=(",", ":"))
        size = len(re.sub(r"\s", "", compact))
        self.assertLessEqual(size, IAM_INLINE_LIMIT, f"{size} characters excluding whitespace; the IAM limit is {IAM_INLINE_LIMIT}")
        self.assertEqual(len(re.sub(r"\s", "", json.dumps(self.POLICY, indent=2))), size)
        # This is the only inline policy of the role, so it is the whole aggregate.
        self.assertEqual(len(re.findall(r'role\s*=\s*aws_iam_role\.factory_distroless_v1\.name', self.FACTORY)), 1)
        # The plan refuses an over-budget policy, and the budget can never exceed the AWS quota.
        self.assertIn(r'length(replace(jsonencode(local.factory_policy), "/\\s/", "")) <= var.factory_policy_max_characters', self.FACTORY)
        self.assertIn("default     = 10240", self.VARIABLES)
        self.assertIn("var.factory_policy_max_characters > 0 && var.factory_policy_max_characters <= 10240", self.VARIABLES)
        tftest = (IAM / "tests/factory.tftest.hcl").read_text()
        self.assertIn('"/\\\\s/", "")) <= 10240', tftest)
        self.assertIn("expect_failures = [aws_iam_role_policy.factory_distroless_v1]", tftest)

    def test_effective_permissions_equal_the_authorized_union(self):
        expected = authorized_union(self.LAB["aws_account_id"], self.LAB["aws_region"], self.LAB["backend_bucket"],
                                    self.LAB["backend_region"], self.CONFIG["DEV"]["release_bucket"], self.CATALOG)
        effective = grants(self.POLICY)
        self.assertEqual(sorted(effective), sorted(expected))
        for scope, actions in expected.items():
            self.assertEqual(effective[scope], actions, scope)

    def test_ecr_is_one_duplicate_free_statement_on_the_exact_catalog(self):
        statement = self.statement("ExactCatalogEcr")
        previous = (set(self.actions(self.MAIN, "ecr_read_actions")) | set(self.actions(self.MAIN, "ecr_apply_actions"))
                    | set(self.actions(self.FACTORY, "publication_read_actions"))
                    | set(self.actions(self.FACTORY, "publication_push_actions")))
        self.assertEqual(statement["Action"], sorted(previous))
        self.assertEqual(len(statement["Action"]), 21)  # 12 Terraform + 11 publication - 2 shared
        self.assertEqual(statement["Resource"], [
            f"arn:aws:ecr:{self.LAB['aws_region']}:{self.LAB['aws_account_id']}:repository/image-base-{name}" for name in self.CATALOG])
        self.assertEqual(len(statement["Resource"]), 16)
        self.assertNotIn("Condition", statement)
        self.assertEqual([item["Sid"] for item in self.POLICY["Statement"] if any("repository/" in arn for arn in item["Resource"])],
                         ["ExactCatalogEcr"])
        self.assertEqual(self.FACTORY.count("local.repository_arns"), 1)

    def test_policy_has_no_unauthorized_actions_or_resources(self):
        for item in self.POLICY["Statement"]:
            self.assertEqual(item["Effect"], "Allow")
            self.assertLessEqual(set(item), {"Sid", "Effect", "Action", "Resource", "Condition"})  # no NotAction/NotResource/Principal
        pairs = {(action, resource) for item in self.POLICY["Statement"] for action in item["Action"] for resource in item["Resource"]}
        self.assertFalse({action for action, _ in pairs if "*" in action})
        self.assertEqual({action.split(":")[0] for action, _ in pairs}, {"ecr", "s3"})  # no iam, sts, athena, glue, kms
        lock = f"arn:aws:s3:::{self.LAB['backend_bucket']}/alric-containers-image-base/terraform.tfstate.tflock"
        self.assertEqual({pair for pair in pairs if "Delete" in pair[0]}, {("s3:DeleteObject", lock)})
        analytics = f"arn:aws:s3:::alric-distroless-sbom-{self.LAB['aws_account_id']}-{self.LAB['aws_region']}"
        release = "arn:aws:s3:::" + self.CONFIG["DEV"]["release_bucket"]
        self.assertEqual({resource for _, resource in pairs if "*" in resource},
                         {"*", release + "/*", analytics + "/sbom-analytics/poc-v1/snapshots/*"})
        self.assertEqual({action for action, resource in pairs if resource == "*"}, {"ecr:GetAuthorizationToken", "ecr:DescribeRepositories"})
        self.assertEqual({item["Sid"] for item in self.POLICY["Statement"] if "*" in item["Resource"]},
                         {"ReadOnlyRegionalRepositoryInventory", "RegistryAuthentication"})
        self.assertEqual(self.FACTORY.count('Resource = ["*"]'), 1)

    def test_sbom_snapshots_have_no_deletion_and_athena_is_not_attached(self):
        objects = self.statement("SbomSnapshotObjects")
        self.assertEqual(set(objects["Action"]), {"s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"})
        self.assertEqual(objects["Resource"], [f"arn:aws:s3:::alric-distroless-sbom-{self.LAB['aws_account_id']}-{self.LAB['aws_region']}"
                                               "/sbom-analytics/poc-v1/snapshots/*"])
        self.assertEqual(self.statement("SbomSnapshotListing")["Action"], ["s3:ListBucket"])
        self.assertNotRegex(json.dumps(self.POLICY), r"athena|glue|query-results")

    def test_policy_document_is_bound_to_the_terraform_source(self):
        analytics = self.statement("ExactSbomAnalyticsBucket")["Action"]
        self.assertEqual(analytics, self.actions(self.MAIN, "analytics_read_actions") + self.actions(self.MAIN, "analytics_apply_actions"))
        # Text-level binding of every statement to the reviewed document (the evaluated policy is checked by `terraform test`).
        self.assertIn("sort(distinct(concat(local.ecr_read_actions, local.ecr_apply_actions, "
                      "local.publication_read_actions, local.publication_push_actions)))", self.FACTORY)
        self.assertIn("Resource = local.repository_arns", self.FACTORY)
        literal = {"RegistryAuthentication": '["*"]', "DevReleaseInventory": "[local.release_bucket_arn]",
                   "DevReleaseRecords": '["${local.release_bucket_arn}/*"]', "SbomSnapshotObjects": "[local.sbom_snapshots_arn]",
                   "SbomSnapshotListing": "[local.analytics_bucket_arn]"}
        for sid, resource in literal.items():
            block = re.search(rf'Sid\s*=\s*"{sid}"(.*?)\n    \}},', self.FACTORY, re.S).group(1)
            self.assertEqual(re.findall(r'"([a-z0-9]+:[A-Za-z]+)"', re.search(r'Action\s*=\s*(\[[^\]]*\])', block).group(1)),
                             self.statement(sid)["Action"], sid)
            self.assertRegex(block, rf'Resource\s*=\s*{re.escape(resource)}')
            has_condition = "Condition" in self.statement(sid)
            self.assertEqual("Condition" in block, has_condition, sid)
            if has_condition:
                self.assertIn('StringEquals = { "aws:RequestedRegion" = var.aws_region }', block)
        self.assertIn('StringLike   = { "s3:prefix" = ["sbom-analytics/poc-v1/snapshots/*"] }', self.FACTORY)
        backend = re.search(r'Sid\s*=\s*"EnsureExactBackendBucket"\s*Effect\s*=\s*"Allow"\s*Action\s*=\s*(\[[^\]]*\])', self.MAIN).group(1)
        self.assertEqual(re.findall(r'"([a-z0-9]+:[A-Za-z]+)"', backend), self.statement("EnsureExactBackendBucket")["Action"])
        self.assertIn('Action   = purpose == "plan" ? ["s3:GetObject"] : ["s3:GetObject", "s3:PutObject"]', self.MAIN)
        self.assertEqual(self.statement("ExactDefaultWorkspaceState")["Action"], ["s3:GetObject", "s3:PutObject"])
        self.assertEqual(self.statement("ExactDefaultWorkspaceLock")["Action"], ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"])
        tftest = (IAM / "tests/factory.tftest.hcl").read_text()
        self.assertIn('file("${path.module}/tests/fixtures/factory-distroless-v1.policy.json")', tftest)
        self.assertIn("jsondecode(aws_iam_role_policy.infra[\"apply\"].policy).Statement, 1, 6", tftest)
        self.assertEqual(self.statement("RegistryAuthentication"), {
            "Sid": "RegistryAuthentication", "Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": ["*"],
            "Condition": {"StringEquals": {"aws:RequestedRegion": self.LAB["aws_region"]}}})

    def test_source_derives_arns_from_configuration(self):
        for literal in (self.LAB["aws_account_id"], self.CONFIG["DEV"]["release_bucket"], self.LAB["backend_bucket"], "arn:aws:ecr"):
            self.assertNotIn(literal, self.FACTORY)
        self.assertIn('release_bucket_arn = "arn:aws:s3:::${local.pipeline.DEV.release_bucket}"', self.FACTORY)
        self.assertIn('sbom_snapshots_arn = "${local.analytics_bucket_arn}/sbom-analytics/poc-v1/snapshots/*"', self.FACTORY)

    def test_publication_reuses_the_proven_dev_actions(self):
        self.assertEqual(self.actions(self.FACTORY, "publication_read_actions"), re.findall(r'"(ecr:[A-Za-z]+)"', self.LIFECYCLE.split("read_actions = [", 1)[1].split("]", 1)[0]))
        self.assertEqual(self.actions(self.FACTORY, "publication_push_actions"), re.findall(r'"(ecr:[A-Za-z]+)"', self.LIFECYCLE.split("push_actions = [", 1)[1].split("]", 1)[0]))

    def test_backend_state_and_lock_addresses_are_unchanged(self):
        self.assertIn('state_key  = "alric-containers-image-base/terraform.tfstate"', self.MAIN)
        self.assertIn('lock_arn   = "${local.state_arn}.tflock"', self.MAIN)
        self.assertEqual(self.CONFIG["infra"]["backend"], {"bucket": "712107929769-alric-containers-image-base-tfstate",
                                                          "region": "us-east-2", "key": "alric-containers-image-base/terraform.tfstate"})
        self.assertNotIn("backend", self.FACTORY.split("locals {", 1)[0])

    def test_legacy_roles_and_lifecycle_are_untouched(self):
        self.assertEqual(self.CONFIG["DEV"]["role_name"], "alric-image-base-factory-dev")
        self.assertEqual((self.CONFIG["infra"]["plan_role_name"], self.CONFIG["infra"]["apply_role_name"]),
                         ("alric-github-repo-1360616627-infra-plan", "alric-github-repo-1360616627-infra-apply"))
        self.assertIn("name                 = local.dev.role_name", self.LIFECYCLE)
        self.assertIn('resource "aws_iam_role" "dev"', self.LIFECYCLE)
        self.assertIn("name                 = \"${var.role_name_prefix}-${var.github_repository_id}-infra-${each.key}\"", self.MAIN)

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
