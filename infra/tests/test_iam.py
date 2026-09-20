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
        text = "\n".join(path.read_text() for path in IAM.glob("*.tf"))
        self.assertEqual(re.findall(r'resource\s+"([^"]+)"\s+"([^"]+)"', text), [
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


if __name__ == "__main__":
    unittest.main()
