"""Exercise the apply boundary with unsafe and incomplete Terraform plans."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ecr_verify_plan", ROOT / "infra/ecr/verify_plan.py")
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


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
                "actions": [action], "before": copy.deepcopy(values) if action == "no-op" else None,
                "after": copy.deepcopy(values),
            }})
            resources.append({**resource, "values": copy.deepcopy(values)})
        children.append({"address": module, "resources": resources})
    return {
        "format_version": "1.2", "complete": True, "errored": False,
        "resource_changes": changes, "planned_values": {"root_module": {"child_modules": children}},
    }


class PlanBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.plan = valid_plan()

    def test_complete_greenfield_plan_has_three_resources_per_actual_framework(self):
        result = verifier.verify(self.plan)
        self.assertEqual(result["repository_count"], 16)
        self.assertEqual(result["managed_resource_count"], 48)
        self.assertEqual(result["actions"], {"create": 48})
        self.assertEqual(set(result["resource_types"].values()), {16})

    def test_accepts_only_noop_in_idempotence_mode(self):
        self.assertEqual(verifier.verify(valid_plan("no-op"), mode="noop")["actions"], {"no-op": 48})
        with self.assertRaisesRegex(verifier.PlanError, "disallowed actions"):
            verifier.verify(self.plan, mode="noop")

    def test_repeated_dispatch_accepts_creation_and_noop_but_not_update(self):
        item = self.plan["resource_changes"][0]["change"]
        item.update(actions=["no-op"], before=copy.deepcopy(item["after"]))
        verifier.verify(self.plan, mode="create-or-noop")
        item["actions"] = ["update"]
        with self.assertRaisesRegex(verifier.PlanError, "disallowed actions"):
            verifier.verify(self.plan, mode="create-or-noop")

    def test_rejects_delete_update_and_both_replacement_orders(self):
        for actions in (["delete"], ["update"], ["delete", "create"], ["create", "delete"]):
            with self.subTest(actions=actions):
                self.plan["resource_changes"][0]["change"]["actions"] = actions
                with self.assertRaisesRegex(verifier.PlanError, "disallowed actions"):
                    verifier.verify(self.plan)

    def test_rejects_unrelated_managed_resource_even_when_noop(self):
        self.plan["resource_changes"].append({
            "address": "aws_s3_bucket.backend", "mode": "managed", "type": "aws_s3_bucket",
            "change": {"actions": ["no-op"]},
        })
        with self.assertRaisesRegex(verifier.PlanError, "graph mismatch"):
            verifier.verify(self.plan, mode="create-or-noop")

    def test_rejects_missing_policy_and_duplicate_repository(self):
        self.plan["resource_changes"].pop()
        with self.assertRaisesRegex(verifier.PlanError, "graph mismatch"):
            verifier.verify(self.plan)
        self.plan = valid_plan()
        self.plan["resource_changes"].append(self.plan["resource_changes"][0])
        with self.assertRaisesRegex(verifier.PlanError, "duplicate"):
            verifier.verify(self.plan)

    def test_rejects_inconsistent_planned_graph(self):
        self.plan["planned_values"]["root_module"]["child_modules"].pop()
        with self.assertRaisesRegex(verifier.PlanError, "planned values: catalog graph mismatch"):
            verifier.verify(self.plan)

    def test_rejects_renamed_repository_in_after_or_planned_values(self):
        for source in ("after", "values"):
            with self.subTest(source=source):
                plan = valid_plan()
                values = (plan["resource_changes"][0]["change"]["after"] if source == "after"
                          else plan["planned_values"]["root_module"]["child_modules"][0]["resources"][0]["values"])
                values["name"] = "outside-the-catalog"
                with self.assertRaisesRegex(verifier.PlanError, "repository name"):
                    verifier.verify(plan)

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
                    verifier.verify(plan)

    def test_rejects_unknown_policy_or_broader_repository_grant(self):
        policy = self.plan["resource_changes"][1]["change"]["after"]
        policy["policy"] = None
        with self.assertRaisesRegex(verifier.PlanError, "policy is absent"):
            verifier.verify(self.plan)
        self.plan = valid_plan()
        after = self.plan["resource_changes"][1]["change"]["after"]
        document = json.loads(after["policy"])
        document["Statement"][0]["Action"].append("ecr:PutImage")
        after["policy"] = json.dumps(document)
        with self.assertRaisesRegex(verifier.PlanError, "versioned contract"):
            verifier.verify(self.plan)

    def test_rejects_import_moved_and_existing_state(self):
        for mutation in ("import", "moved", "prior"):
            with self.subTest(mutation=mutation):
                plan = valid_plan()
                if mutation == "import":
                    plan["resource_changes"][0]["change"]["importing"] = {"id": "existing"}
                elif mutation == "moved":
                    plan["resource_changes"][0]["previous_address"] = "module.old.aws_ecr_repository.this[0]"
                else:
                    plan["prior_state"] = {"values": copy.deepcopy(plan["planned_values"])}
                with self.assertRaises(verifier.PlanError):
                    verifier.verify(plan)

    def test_rejects_partial_or_failed_plans(self):
        for key, value in (("complete", False), ("errored", True), ("deferred_changes", [{}]),
                           ("checks", [{"status": "unknown"}])):
            with self.subTest(key=key):
                plan = valid_plan()
                plan[key] = value
                with self.assertRaises(verifier.PlanError):
                    verifier.verify(plan)


if __name__ == "__main__":
    unittest.main()
