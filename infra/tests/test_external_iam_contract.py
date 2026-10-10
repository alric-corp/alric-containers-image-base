"""Offline contract for the operator/IAM-team-owned Factory identity.

This suite reads reference documents; it never initializes an AWS client or
provisions IAM. Expected grants are independent of the JSON under test.
"""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
IAM = ROOT / "infra/iam"
POLICIES = ROOT / "policies/aws"
ROLE_NAME = "itau-github-repo-factory-distroless-v1"
INLINE_POLICY_NAME = "factory-distroless-v1"
INLINE_LIMIT = 10240


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_contract(name):
    return json.loads((POLICIES / name).read_text(), object_pairs_hook=unique_object)


# Explicit action allowlists from the reviewed Infra, ECR, release and snapshot
# scopes. ListImageReferrers is an API operation authorized by BatchGetImage,
# not an IAM action. No other reviewed action is removed or added here.
BACKEND_ACTIONS = {
    "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketVersioning",
    "s3:GetEncryptionConfiguration", "s3:GetBucketPublicAccessBlock",
    "s3:GetBucketOwnershipControls", "s3:CreateBucket",
    "s3:PutBucketPublicAccessBlock", "s3:PutBucketOwnershipControls",
    "s3:PutEncryptionConfiguration", "s3:PutBucketVersioning",
}
ANALYTICS_BUCKET_ACTIONS = {
    "s3:ListBucket", "s3:GetBucketLocation", "s3:GetBucketAcl",
    "s3:GetBucketCORS", "s3:GetBucketWebsite", "s3:GetBucketVersioning",
    "s3:GetBucketLogging", "s3:GetBucketTagging", "s3:ListTagsForResource",
    "s3:GetBucketRequestPayment", "s3:GetAccelerateConfiguration",
    "s3:GetReplicationConfiguration", "s3:GetLifecycleConfiguration",
    "s3:GetEncryptionConfiguration", "s3:GetBucketObjectLockConfiguration",
    "s3:GetBucketPublicAccessBlock", "s3:GetBucketOwnershipControls",
    "s3:GetBucketPolicy", "s3:CreateBucket", "s3:PutBucketPublicAccessBlock",
    "s3:PutBucketOwnershipControls", "s3:PutEncryptionConfiguration",
    "s3:PutBucketVersioning", "s3:PutBucketPolicy", "s3:TagResource",
    "s3:PutBucketTagging",
}
ECR_ACTIONS = {
    "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage",
    "ecr:CompleteLayerUpload", "ecr:CreateRepository", "ecr:DescribeImages",
    "ecr:DescribeRepositories", "ecr:GetDownloadUrlForLayer",
    "ecr:GetLifecyclePolicy", "ecr:GetRepositoryPolicy", "ecr:InitiateLayerUpload",
    "ecr:ListImages", "ecr:ListTagsForResource", "ecr:PutImage",
    "ecr:PutImageScanningConfiguration", "ecr:PutImageTagMutability",
    "ecr:PutLifecyclePolicy", "ecr:SetRepositoryPolicy", "ecr:TagResource",
    "ecr:UntagResource", "ecr:UploadLayerPart",
}
ATHENA_ACTIONS = {
    "athena:GetWorkGroup", "athena:StartQueryExecution", "athena:GetQueryExecution",
    "athena:GetQueryResults", "athena:StopQueryExecution",
}
GLUE_ACTIONS = {"glue:GetDatabase", "glue:GetTable", "glue:GetPartitions", "glue:CreateTable"}


class ExternalFactoryIamContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trust = load_contract("factory-distroless-v1.trust.json")
        cls.policy = load_contract("factory-distroless-v1.inline-policy.json")
        cls.config = json.loads((ROOT / "policies/pipeline/config.json").read_text())
        cls.lab = dict(re.findall(r'(?m)^(\w+)\s*=\s*"([^"]*)"', (IAM / "lab.tfvars").read_text()))
        cls.catalog = sorted(path.stem for path in (ROOT / "frameworks").glob("*.yaml"))
        cls.runbook = (ROOT / "docs/factory-distroless-v1-iam-runbook.md").read_text()
        cls.statements = {item["Sid"]: item for item in cls.policy["Statement"]}
        cls.backend = "arn:aws:s3:::" + cls.config["infra"]["backend"]["bucket"]
        cls.state = cls.backend + "/" + cls.config["infra"]["backend"]["key"]
        cls.analytics = f"arn:aws:s3:::alric-distroless-sbom-{cls.lab['aws_account_id']}-{cls.lab['aws_region']}"
        cls.release = "arn:aws:s3:::" + cls.config["DEV"]["release_bucket"]

    def assert_statement(self, sid, actions, resources, condition=None):
        statement = self.statements[sid]
        expected_keys = {"Sid", "Effect", "Action", "Resource"}
        if condition is not None:
            expected_keys.add("Condition")
        self.assertEqual(set(statement), expected_keys, sid)
        self.assertEqual(statement["Effect"], "Allow", sid)
        self.assertIsInstance(statement["Action"], list, sid)
        self.assertEqual(set(statement["Action"]), set(actions), sid)
        self.assertEqual(len(statement["Action"]), len(set(actions)), sid)
        self.assertEqual(statement["Resource"], resources, sid)
        self.assertEqual(statement.get("Condition"), condition, sid)

    def test_exact_external_identity_names_and_session_duration(self):
        self.assertIn(f'factory_role_name="{ROLE_NAME}"', self.runbook)
        self.assertIn(f'factory_inline_policy_name="{INLINE_POLICY_NAME}"', self.runbook)
        self.assertIn("--max-session-duration 10800", self.runbook)
        self.assertIn(f"arn:aws:iam::712107929769:role/{ROLE_NAME}", self.runbook)
        self.assertIn('"factory-distroless-v1"', self.runbook)

    def test_json_grammar_and_exact_statement_inventory(self):
        self.assertEqual(set(self.policy), {"Version", "Statement"})
        self.assertEqual(self.policy["Version"], "2012-10-17")
        self.assertEqual([item["Sid"] for item in self.policy["Statement"]], [
            "EnsureExactBackendBucket", "ExactDefaultWorkspaceState", "ExactDefaultWorkspaceLock",
            "ReadOnlyRegionalRepositoryInventory", "ExactSbomAnalyticsBucket",
            "ExactCatalogEcr", "RegistryAuthentication", "DevReleaseInventory",
            "DevReleaseRecords", "SbomSnapshotObjects", "SbomSnapshotListing",
            "PocAthenaExactWorkgroup", "PocGlueReadAndNewTables", "PocAthenaQueryResults",
        ])
        self.assertEqual(len(self.statements), len(self.policy["Statement"]))

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            json.loads('{"Version":"2012-10-17","Version":"other"}', object_pairs_hook=unique_object)

    def test_exact_two_environment_trust_with_immutable_ids(self):
        self.assertEqual(self.trust, {"Version": "2012-10-17", "Statement": [{
            "Sid": "FactoryProtectedEnvironments", "Effect": "Allow",
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Principal": {"Federated": "arn:aws:iam::712107929769:oidc-provider/token.actions.githubusercontent.com"},
            "Condition": {"StringEquals": {
                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                "token.actions.githubusercontent.com:repository_id": "1360616627",
                "token.actions.githubusercontent.com:repository_owner_id": "178685987",
                "token.actions.githubusercontent.com:sub": [
                    "repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:lab-image-base-infra",
                    "repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:DEV",
                ],
            }},
        }]})

    def test_trust_has_no_pr_branch_wildcard_or_alternate_principal(self):
        encoded = json.dumps(self.trust)
        for forbidden in ("pull_request", "refs/", "StringLike", "*", "sts:AssumeRole\""):
            self.assertNotIn(forbidden, encoded)

    def test_lab_contract_matches_configuration_without_changing_it(self):
        self.assertEqual(self.lab["aws_account_id"], "712107929769")
        self.assertEqual(self.lab["aws_region"], "us-east-1")
        self.assertEqual(self.lab["backend_region"], "us-east-2")
        self.assertEqual(self.config["DEV"]["account_id"], self.lab["aws_account_id"])
        self.assertEqual(self.config["DEV"]["region"], self.lab["aws_region"])
        self.assertEqual(self.config["subject_prefix"], self.lab["github_subject_prefix"])
        self.assertEqual(self.config["infra"]["backend"], {
            "bucket": self.lab["backend_bucket"], "region": self.lab["backend_region"],
            "key": "alric-containers-image-base/terraform.tfstate",
        })

    def test_backend_state_and_lock_scope(self):
        self.assert_statement("EnsureExactBackendBucket", BACKEND_ACTIONS, [self.backend],
                              {"StringEquals": {"aws:RequestedRegion": "us-east-2"}})
        self.assert_statement("ExactDefaultWorkspaceState", {"s3:GetObject", "s3:PutObject"}, [self.state])
        self.assert_statement("ExactDefaultWorkspaceLock", {"s3:GetObject", "s3:PutObject", "s3:DeleteObject"},
                              [self.state + ".tflock"])

    def test_ecr_exact_catalog_and_reviewed_actions(self):
        self.assert_statement("ExactCatalogEcr", ECR_ACTIONS, [
            f"arn:aws:ecr:{self.lab['aws_region']}:{self.lab['aws_account_id']}:repository/image-base-{name}"
            for name in self.catalog
        ])
        self.assertIn("ecr:BatchGetImage", self.statements["ExactCatalogEcr"]["Action"])

    def test_only_regional_inventory_and_authentication_use_global_resources(self):
        region = {"StringEquals": {"aws:RequestedRegion": "us-east-1"}}
        self.assert_statement("ReadOnlyRegionalRepositoryInventory", {"ecr:DescribeRepositories"}, ["*"], region)
        self.assert_statement("RegistryAuthentication", {"ecr:GetAuthorizationToken"}, ["*"], region)
        self.assertEqual({item["Sid"] for item in self.policy["Statement"] if "*" in item["Resource"]},
                         {"ReadOnlyRegionalRepositoryInventory", "RegistryAuthentication"})

    def test_exact_sbom_bucket_administration_preserves_reviewed_scope(self):
        self.assert_statement("ExactSbomAnalyticsBucket", ANALYTICS_BUCKET_ACTIONS, [self.analytics],
                              {"StringEquals": {"aws:RequestedRegion": "us-east-1"}})

    def test_dev_release_store_scope(self):
        self.assert_statement("DevReleaseInventory", {"s3:ListBucket"}, [self.release])
        self.assert_statement("DevReleaseRecords", {"s3:GetObject", "s3:PutObject"}, [self.release + "/*"])

    def test_snapshot_objects_and_listing_scope(self):
        self.assert_statement("SbomSnapshotObjects", {"s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"},
                              [self.analytics + "/sbom-analytics/poc-v1/snapshots/*"],
                              {"StringEquals": {"aws:RequestedRegion": "us-east-1"}})
        self.assert_statement("SbomSnapshotListing", {"s3:ListBucket"}, [self.analytics], {
            "StringEquals": {"aws:RequestedRegion": "us-east-1"},
            "StringLike": {"s3:prefix": ["sbom-analytics/poc-v1/snapshots/*"]},
        })

    def test_no_invalid_or_unapproved_actions_and_no_data_deletion(self):
        approved = BACKEND_ACTIONS | ANALYTICS_BUCKET_ACTIONS | ECR_ACTIONS | ATHENA_ACTIONS | GLUE_ACTIONS | {
            "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:GetObjectVersion", "ecr:GetAuthorizationToken",
        }
        actions = {action for item in self.policy["Statement"] for action in item["Action"]}
        self.assertEqual(actions, approved)
        self.assertNotIn("ecr:ListImageReferrers", actions)
        self.assertEqual({action.split(":")[0] for action in actions}, {"ecr", "s3", "athena", "glue"})
        self.assertFalse(any("*" in action for action in actions))
        deletion = {(action, resource) for item in self.policy["Statement"]
                    for action in item["Action"] for resource in item["Resource"] if "Delete" in action}
        self.assertEqual(deletion, {("s3:DeleteObject", self.state + ".tflock")})
        self.assertNotIn("query-results", json.dumps(self.policy["Statement"][:11]))

    def test_athena_complement_keeps_exact_workgroup_catalog_and_five_objects(self):
        snapshot = "6ae0d5a463a20961e4431cb86d7d969ff2157bf25428a22dd08aa119632548b6"
        glue = "arn:aws:glue:us-east-1:712107929769:"
        self.assert_statement("PocAthenaExactWorkgroup", ATHENA_ACTIONS,
                              ["arn:aws:athena:us-east-1:712107929769:workgroup/poc_distroless_sbom"])
        self.assert_statement("PocGlueReadAndNewTables", GLUE_ACTIONS, [
            glue + "catalog", glue + "database/poc_distroless_sbom",
            *[glue + "table/poc_distroless_sbom/poc_snapshot_" + snapshot + "_" + name for name in (
                "sbom_observation_rows_v1", "sbom_package_rows_v1", "sbom_observations_v1",
                "sbom_packages_v1", "sbom_inventory_v1")],
        ])
        self.assert_statement("PocAthenaQueryResults", {"s3:GetObject", "s3:PutObject"},
                              [self.analytics + "/query-results/poc-v1/*"])
        delta = json.loads((ROOT / "docs/examples/sbom-lab/athena-policy-delta.json").read_text())
        self.assertEqual(self.policy["Statement"][11:], delta["Statement"])
        self.assertFalse({"athena:CreateWorkGroup", "glue:CreateDatabase", "glue:UpdateTable"} & {
            a for s in self.policy["Statement"] for a in s["Action"]})
        self.assertEqual(len(json.dumps(self.policy, separators=(",", ":"))), 6277)

    def test_single_inline_policy_size_excludes_formatting_only(self):
        compact = json.dumps(self.policy, separators=(",", ":"))
        self.assertTrue(compact.isascii())
        self.assertNotRegex(compact, r"\s")
        self.assertLess(len(compact), INLINE_LIMIT)
        self.assertIn("10.240", self.runbook)
        self.assertIn("list-role-policies", self.runbook)
        self.assertIn("list-attached-role-policies", self.runbook)

    def test_central_identity_has_no_terraform_resource_variable_output_or_state_reference(self):
        forbidden = (ROLE_NAME, "factory_distroless_v1", "factory_role_name", "factory_dev_environment",
                     "factory_policy", "factory-distroless-v1.trust.json", "factory-distroless-v1.inline-policy.json")
        for path in (ROOT / "infra").rglob("*.tf"):
            if ".terraform" in path.parts:
                continue
            for token in forbidden:
                self.assertNotIn(token, path.read_text(), str(path.relative_to(ROOT)))
        self.assertFalse((IAM / "factory.tf").exists())
        self.assertFalse((IAM / "tests/factory.tftest.hcl").exists())

    def test_legacy_roles_keep_their_names_and_managed_addresses(self):
        main = (IAM / "main.tf").read_text()
        self.assertIn('resource "aws_iam_role" "infra"', main)
        self.assertIn('resource "aws_iam_role_policy" "infra"', main)
        self.assertIn('name                 = "${var.role_name_prefix}-${var.github_repository_id}-infra-${each.key}"', main)
        lifecycle = (ROOT / "infra/lifecycle/main.tf").read_text()
        self.assertIn('resource "aws_iam_role" "dev"', lifecycle)
        self.assertIn("name                 = local.dev.role_name", lifecycle)
        self.assertEqual(self.config["DEV"]["role_name"], "alric-image-base-factory-dev")
        self.assertEqual((self.config["infra"]["plan_role_name"], self.config["infra"]["apply_role_name"]),
                         ("alric-github-repo-1360616627-infra-plan", "alric-github-repo-1360616627-infra-apply"))

    def test_workflows_use_resolver_without_applying_external_iam_contract(self):
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            # Only the identity preflight pins the ARN directly; operational
            # workflows keep using the versioned resolver interface.
            # Its full guards/session/identity contract is tested in governance.
            if path.name == "factory-central-role-preflight.yml":
                self.assertIn("inline-session-policy:", path.read_text())
                self.assertIn('"Action":"sts:GetCallerIdentity"', path.read_text())
                continue
            self.assertNotIn("factory-distroless", path.read_text(), path.name)
        for path in (ROOT / "scripts").rglob("*.py"):
            self.assertNotIn("factory-distroless-v1", path.read_text(), str(path.relative_to(ROOT)))
        self.assertEqual(self.config["factory"]["operational_role_name"], ROLE_NAME)
        self.assertIs(self.config["infra"]["plan_enabled"], False)
        self.assertEqual(self.config["HOM"], {
            "account_id": "248908662184", "region": "sa-east-1", "role_name": "alric-image-base-factory-hom",
            "release_bucket": "248908662184-image-base-releases-hom",
        })


if __name__ == "__main__":
    unittest.main()
