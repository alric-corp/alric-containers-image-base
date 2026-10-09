"""Exercise the apply boundary with unsafe and incomplete Terraform plans."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ecr_verify_plan", ROOT / "infra/ecr/verify_plan.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


ACCOUNT = "123456789012"
REGION = "us-east-1"
BUCKET = f"alric-distroless-sbom-{ACCOUNT}-{REGION}"


def verify(plan, **kwargs):
    return verifier.verify(plan, account_id=ACCOUNT, region=REGION, **kwargs)


def valid_plan(action="create"):
    """Minimal Terraform JSON for a complete catalog, independently assembled."""
    changes, children = [], []
    for framework in sorted(path.stem for path in (ROOT / "frameworks").glob("*.yaml")):
        module = f'module.ecr["{framework}"]'
        resources = []
        values_by_type = {
            "aws_ecr_repository": {
                "name": f"image-base-{framework}",
                "force_delete": False,
                "image_tag_mutability": "IMMUTABLE_WITH_EXCLUSION",
                "image_tag_mutability_exclusion_filter": [
                    {"filter": "stable", "filter_type": "WILDCARD"}
                ],
                "image_scanning_configuration": [{"scan_on_push": True}],
                "encryption_configuration": [{"encryption_type": "AES256", "kms_key": None}],
                "tags": {"ManagedBy": "Terraform", "Source": "alric-corp/alric-containers-image-base"},
            },
            "aws_ecr_repository_policy": {
                "repository": f"image-base-{framework}",
                "policy": (ROOT / "infra/ecr/policies/ecr-repository-org-pull.json").read_text(),
            },
            "aws_ecr_lifecycle_policy": {
                "repository": f"image-base-{framework}",
                "policy": (ROOT / "infra/ecr/policies/ecr-lifecycle-7-days.json").read_text(),
            },
        }
        for kind, values in values_by_type.items():
            resource = {
                "address": f"{module}.{kind}.this[0]", "mode": "managed", "type": kind,
                "provider_name": "registry.terraform.io/hashicorp/aws",
            }
            changes.append({**resource, "change": {
                "actions": ["no-op"], "before": copy.deepcopy(values),
                "after": copy.deepcopy(values),
            }})
            resources.append({**resource, "values": copy.deepcopy(values)})
        children.append({"address": module, "resources": resources})
    ecr_prior = copy.deepcopy(children)
    from infra.s3.contract import bucket_policy
    values_by_type = {
        "aws_s3_bucket": {"bucket": BUCKET, "region": REGION, "force_destroy": False, "object_lock_enabled": False, "tags": dict(verifier.PROVENANCE)},
        "aws_s3_bucket_public_access_block": {"block_public_acls": True, "ignore_public_acls": True, "block_public_policy": True, "restrict_public_buckets": True},
        "aws_s3_bucket_ownership_controls": {"rule": [{"object_ownership": "BucketOwnerEnforced"}]},
        "aws_s3_bucket_versioning": {"versioning_configuration": [{"status": "Enabled"}], "expected_bucket_owner": ACCOUNT},
        "aws_s3_bucket_server_side_encryption_configuration": {"rule": [{"apply_server_side_encryption_by_default": [{"sse_algorithm": "AES256"}]}], "expected_bucket_owner": ACCOUNT},
        "aws_s3_bucket_policy": {"policy": json.dumps(bucket_policy(BUCKET))},
    }
    resources, configuration = [], []
    for kind, values in values_by_type.items():
        values.update(region=REGION, bucket=BUCKET)
        address = f"module.sbom.{kind}.sbom"
        resource = {"address": address, "mode": "managed", "type": kind, "provider_name": verifier.PROVIDER}
        changes.append({**resource, "change": {"actions": [action], "before": copy.deepcopy(values) if action == "no-op" else None, "after": copy.deepcopy(values)}})
        resources.append({**resource, "values": copy.deepcopy(values)})
        config = {"address": kind + ".sbom", "mode": "managed", "expressions": {"bucket": {"references": ["aws_s3_bucket.sbom.id", "aws_s3_bucket.sbom"]}}}
        if kind == "aws_s3_bucket_policy":
            config["depends_on"] = [k + ".sbom" for k in values_by_type if k not in ("aws_s3_bucket", "aws_s3_bucket_policy")]
        configuration.append(config)
    children.append({"address": "module.sbom", "resources": resources})
    return {
        "variables": {"aws_region": {"value": REGION}, "expected_bucket_owner": {"value": ACCOUNT}},
        "configuration": {"root_module": {"module_calls": {"ecr": {"source": "terraform-aws-modules/ecr/aws", "version_constraint": "3.2.0"}, "sbom": {"source": "../s3", "module": {"resources": configuration}}}}},
        "prior_state": {"values": {"root_module": {"child_modules": copy.deepcopy(children) if action == "no-op" else ecr_prior}}},
        "format_version": "1.2", "complete": True, "errored": False,
        "resource_changes": changes, "planned_values": {"root_module": {"child_modules": children}},
    }


class PlanBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.plan = valid_plan()

    def test_adoption_preserves_catalog_and_adds_exactly_six_s3_resources(self):
        result = verify(self.plan)
        self.assertEqual(result["repository_count"], 16)
        self.assertEqual(result["managed_resource_count"], 54)
        self.assertEqual(result["actions"], {"no-op": 48, "create": 6})
        self.assertEqual(set(result["resource_types"].values()), {16, 1})

    def test_accepts_only_noop_in_idempotence_mode(self):
        self.assertEqual(verify(valid_plan("no-op"), mode="noop")["actions"], {"no-op": 54})
        with self.assertRaisesRegex(verifier.PlanError, "prior state"):
            verify(self.plan, mode="noop")

    def test_repeated_dispatch_accepts_creation_and_noop_but_not_update(self):
        item = self.plan["resource_changes"][-1]["change"]
        item.update(actions=["no-op"], before=copy.deepcopy(item["after"]))
        verify(self.plan, mode="sbom-adoption")
        item["actions"] = ["update"]
        with self.assertRaisesRegex(verifier.PlanError, "disallowed actions"):
            verify(self.plan, mode="sbom-adoption")

    def test_rejects_delete_update_and_both_replacement_orders(self):
        for actions in (["delete"], ["update"], ["delete", "create"], ["create", "delete"]):
            with self.subTest(actions=actions):
                self.plan["resource_changes"][0]["change"]["actions"] = actions
                with self.assertRaisesRegex(verifier.PlanError, "disallowed actions"):
                    verify(self.plan)

    def test_rejects_unrelated_managed_resource_even_when_noop(self):
        self.plan["resource_changes"].append({
            "address": "aws_s3_bucket.backend", "mode": "managed", "type": "aws_s3_bucket",
            "change": {"actions": ["no-op"]},
        })
        with self.assertRaisesRegex(verifier.PlanError, "graph mismatch"):
            verify(self.plan, mode="sbom-adoption")

    def test_rejects_missing_policy_and_duplicate_repository(self):
        self.plan["resource_changes"].pop()
        with self.assertRaisesRegex(verifier.PlanError, "graph mismatch"):
            verify(self.plan)
        self.plan = valid_plan()
        self.plan["resource_changes"].append(self.plan["resource_changes"][0])
        with self.assertRaisesRegex(verifier.PlanError, "duplicate"):
            verify(self.plan)

    def test_rejects_inconsistent_planned_graph(self):
        self.plan["planned_values"]["root_module"]["child_modules"].pop()
        with self.assertRaisesRegex(verifier.PlanError, "planned values: catalog graph mismatch"):
            verify(self.plan)

    def test_rejects_renamed_repository_in_after_or_planned_values(self):
        for source in ("after", "values"):
            with self.subTest(source=source):
                plan = valid_plan()
                values = (plan["resource_changes"][0]["change"]["after"] if source == "after"
                          else plan["planned_values"]["root_module"]["child_modules"][0]["resources"][0]["values"])
                values["name"] = "outside-the-catalog"
                with self.assertRaisesRegex(verifier.PlanError, "repository name"):
                    verify(plan)

    def test_rejects_mutability_scanning_force_delete_encryption_or_source_drift(self):
        mutations = {
            "force_delete": True,
            "image_tag_mutability": "MUTABLE",
            "image_tag_mutability_exclusion_filter": [{"filter": "*", "filter_type": "WILDCARD"}],
            "image_scanning_configuration": [{"scan_on_push": False}],
            "encryption_configuration": [{"encryption_type": "KMS"}],
            "tags": {"ManagedBy": "Terraform", "Source": "alric-corp/alric-containers-registry"},
        }
        for key, value in mutations.items():
            with self.subTest(key=key):
                plan = valid_plan()
                plan["resource_changes"][0]["change"]["after"][key] = value
                with self.assertRaises(verifier.PlanError):
                    verify(plan)

    def test_rejects_unknown_policy_or_broader_repository_grant(self):
        policy = self.plan["resource_changes"][1]["change"]["after"]
        policy["policy"] = None
        with self.assertRaisesRegex(verifier.PlanError, "policy is absent"):
            verify(self.plan)
        self.plan = valid_plan()
        after = self.plan["resource_changes"][1]["change"]["after"]
        document = json.loads(after["policy"])
        document["Statement"][0]["Action"].append("ecr:PutImage")
        after["policy"] = json.dumps(document)
        with self.assertRaisesRegex(verifier.PlanError, "versioned contract"):
            verify(self.plan)

    def test_rejects_import_moved_and_existing_state(self):
        for mutation in ("import", "moved", "prior"):
            with self.subTest(mutation=mutation):
                plan = valid_plan()
                if mutation == "import":
                    plan["resource_changes"][0]["change"]["importing"] = {"id": "existing"}
                elif mutation == "moved":
                    plan["resource_changes"][0]["previous_address"] = "module.old.aws_ecr_repository.this[0]"
                else:
                    plan["prior_state"] = {"values": {"root_module": {}}}
                with self.assertRaises(verifier.PlanError):
                    verify(plan)

    def test_rejects_partial_or_failed_plans(self):
        for key, value in (("complete", False), ("errored", True), ("deferred_changes", [{}]),
                           ("checks", [{"status": "unknown"}])):
            with self.subTest(key=key):
                plan = valid_plan()
                plan[key] = value
                with self.assertRaises(verifier.PlanError):
                    verify(plan)


if __name__ == "__main__":
    unittest.main()
