"""Lock the reviewed rehearsal catalog and inherited ECR policy contract."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
ECR = ROOT / "infra/ecr"
EXPECTED_FRAMEWORKS = {
    "dotnet10", "dotnet10-dev",
    "go1-25", "go1-25-dev", "go1-26", "go1-26-dev",
    "java21", "java21-dev", "java25", "java25-dev",
    "nodejs22", "nodejs22-dev", "nodejs24", "nodejs24-dev",
    "python3-13", "python3-14",
}


class CatalogTests(unittest.TestCase):
    def test_catalog_matches_the_sixteen_reviewed_frameworks(self):
        self.assertEqual({path.stem for path in (ROOT / "frameworks").glob("*.yaml")}, EXPECTED_FRAMEWORKS)

    def test_terraform_reads_the_factory_catalog_without_a_second_list(self):
        text = (ECR / "locals.tf").read_text()
        self.assertIn('fileset("${path.module}/../../frameworks", "*.yaml")', text)
        self.assertIn('trimsuffix(definition, ".yaml")', text)
        self.assertIn("repositories = toset([", text)
        self.assertNotIn('"go1-26"', text)

    def test_managed_backend_and_migration_blocks_are_absent(self):
        text = "\n".join(path.read_text() for path in ECR.glob("*.tf"))
        self.assertNotRegex(text, r"(?m)^\s*(moved|import)\s*\{")
        self.assertNotRegex(text, r'resource\s+"aws_(s3|dynamodb|iam)_')
        backend = (ECR / "backend.tf").read_text()
        self.assertRegex(backend, r"use_lockfile\s*=\s*true")
        self.assertNotRegex(backend, r"(?m)^\s*(bucket|key|region)\s*=")

    def test_module_keeps_safety_and_provenance_contract(self):
        main = (ECR / "main.tf").read_text()
        self.assertRegex(main, r'repository_force_delete\s*=\s*false')
        self.assertRegex(main, r'version\s*=\s*"3\.2\.0"')
        local = (ECR / "locals.tf").read_text()
        self.assertIn('"alric-corp/alric-containers-image-base"', local)
        self.assertIn("merge(var.additional_tags, local.base_tags)", local)


class PolicyTests(unittest.TestCase):
    def test_lifecycle_protects_stable_then_expires_tagged_builds_after_seven_days(self):
        rules = json.loads((ECR / "policies/ecr-lifecycle-7-days.json").read_text())["rules"]
        self.assertEqual([rule["rulePriority"] for rule in rules], [1, 2])
        self.assertEqual(rules[0]["selection"], {
            "tagStatus": "tagged", "tagPatternList": ["stable"],
            "countType": "imageCountMoreThan", "countNumber": 999999,
        })
        self.assertEqual(rules[1]["selection"], {
            "tagStatus": "tagged", "tagPatternList": ["*"],
            "countType": "sinceImagePushed", "countUnit": "days", "countNumber": 7,
        })
        self.assertTrue(all(rule["action"] == {"type": "expire"} for rule in rules))

    def test_repository_policy_keeps_the_same_organization_and_two_pull_actions(self):
        policy = json.loads((ECR / "policies/ecr-repository-org-pull.json").read_text())
        self.assertEqual(policy["Version"], "2012-10-17")
        self.assertEqual(policy["Statement"], [{
            "Sid": "AllowCrossAccountPull", "Effect": "Allow", "Principal": {"AWS": "*"},
            "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
            "Condition": {"StringEquals": {"aws:PrincipalOrgID": ["o-5gqr9v3h2q"]}},
        }])


if __name__ == "__main__":
    unittest.main()
