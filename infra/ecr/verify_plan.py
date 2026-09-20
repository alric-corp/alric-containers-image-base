#!/usr/bin/env python3
"""Reject a Terraform plan outside the factory catalog and ECR contract.

Consumes ``terraform show -json``; never calls Terraform or AWS. The resource
addresses correspond to the pinned terraform-aws-modules/ecr/aws 3.2.0 source:
private repository + attached repository policy + enabled lifecycle policy.
Their count is derived from the checked-out catalog, not an expected total.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
RESOURCE_TYPES = (
    "aws_ecr_repository",
    "aws_ecr_repository_policy",
    "aws_ecr_lifecycle_policy",
)
PROVIDER = "registry.terraform.io/hashicorp/aws"
PROVENANCE = {
    "ManagedBy": "Terraform",
    "Source": "alric-corp/alric-containers-image-base",
}


class PlanError(ValueError):
    """The proposed plan does not satisfy the rehearsal boundary."""


def catalog(directory):
    names = sorted(path.stem for path in Path(directory).glob("*.yaml") if path.is_file())
    if not names or any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) for name in names):
        raise PlanError("catalog is empty or contains an invalid framework name")
    return names


def expected_resources(frameworks):
    return {
        f'module.ecr["{framework}"].{kind}.this[0]': (framework, kind)
        for framework in frameworks
        for kind in RESOURCE_TYPES
    }


def managed_resources(module):
    for resource in module.get("resources", []):
        if resource.get("mode") == "managed":
            yield resource
    for child in module.get("child_modules", []):
        yield from managed_resources(child)


def resource_map(resources, expected, label):
    result = {}
    for resource in resources:
        address = resource.get("address")
        if not isinstance(address, str) or address in result:
            raise PlanError(f"{label}: missing or duplicate resource address")
        result[address] = resource
    missing = sorted(set(expected) - set(result))
    extra = sorted(set(result) - set(expected))
    if missing or extra:
        raise PlanError(f"{label}: catalog graph mismatch; missing={missing}, extra={extra}")
    return result


def validate_values(address, framework, kind, values, policies):
    if not isinstance(values, dict):
        raise PlanError(f"{address}: resource values are absent or unknown")
    name_key = "name" if kind == "aws_ecr_repository" else "repository"
    if values.get(name_key) != f"image-base-{framework}":
        raise PlanError(f"{address}: repository name does not match the catalog")
    if kind == "aws_ecr_repository":
        required = {
            "force_delete": False,
            "image_tag_mutability": "IMMUTABLE_WITH_EXCLUSION",
            "image_tag_mutability_exclusion_filter": [
                {"filter": "stable", "filter_type": "WILDCARD"}
            ],
            "image_scanning_configuration": [{"scan_on_push": True}],
        }
        for key, value in required.items():
            if values.get(key) != value:
                raise PlanError(f"{address}: unexpected {key}")
        encryption = values.get("encryption_configuration", [])
        if (len(encryption) != 1 or encryption[0].get("encryption_type") != "AES256"
                or encryption[0].get("kms_key")):
            raise PlanError(f"{address}: expected AES256 encryption without a KMS key")
        tags = values.get("tags") or {}
        if any(tags.get(key) != value for key, value in PROVENANCE.items()):
            raise PlanError(f"{address}: incorrect resource provenance tags")
    else:
        try:
            policy = json.loads(values.get("policy", ""))
        except (TypeError, ValueError) as exc:
            raise PlanError(f"{address}: policy is absent, unknown or invalid JSON") from exc
        if policy != policies[kind]:
            raise PlanError(f"{address}: policy differs from the versioned contract")


def verify(plan, frameworks_dir=ROOT.parent.parent / "frameworks", mode="greenfield"):
    if mode not in {"greenfield", "noop", "create-or-noop"}:
        raise PlanError(f"unsupported verification mode: {mode}")
    if plan.get("errored") or plan.get("complete") is False or plan.get("deferred_changes"):
        raise PlanError("plan is errored, incomplete or contains deferred changes")
    if any(check.get("status") not in {"pass"} for check in plan.get("checks", [])):
        raise PlanError("plan contains an unresolved or failed check")
    frameworks = catalog(frameworks_dir)
    expected = expected_resources(frameworks)
    policies = {
        "aws_ecr_repository_policy": json.loads(
            (ROOT / "policies/ecr-repository-org-pull.json").read_text()
        ),
        "aws_ecr_lifecycle_policy": json.loads(
            (ROOT / "policies/ecr-lifecycle-7-days.json").read_text()
        ),
    }
    changes = resource_map(
        (item for item in plan.get("resource_changes", []) if item.get("mode") == "managed"),
        expected,
        "changes",
    )
    planned = resource_map(
        managed_resources(plan.get("planned_values", {}).get("root_module", {})),
        expected,
        "planned values",
    )
    if mode == "greenfield":
        prior = plan.get("prior_state", {}).get("values", {}).get("root_module", {})
        if list(managed_resources(prior)):
            raise PlanError("greenfield plan must start without managed resources in prior state")
    allowed = {
        "greenfield": {("create",)},
        "noop": {("no-op",)},
        "create-or-noop": {("create",), ("no-op",)},
    }[mode]
    actions = Counter()
    for address, (framework, kind) in expected.items():
        item = changes[address]
        change = item.get("change", {})
        action = tuple(change.get("actions", []))
        if action not in allowed:
            raise PlanError(f"{address}: disallowed actions {action} in {mode} mode")
        if item.get("previous_address") or change.get("importing"):
            raise PlanError(f"{address}: state migration or import is not greenfield")
        if action == ("create",) and change.get("before") is not None:
            raise PlanError(f"{address}: create action has pre-existing resource values")
        for resource, values in ((item, change.get("after")),
                                 (planned[address], planned[address].get("values"))):
            if resource.get("type") != kind or resource.get("provider_name") != PROVIDER:
                raise PlanError(f"{address}: unexpected resource type or provider")
            validate_values(address, framework, kind, values, policies)
        actions[action[0]] += 1
    return {
        "mode": mode,
        "frameworks": frameworks,
        "repository_count": len(frameworks),
        "managed_resource_count": len(expected),
        "resource_types": dict(Counter(kind for _, kind in expected.values())),
        "actions": dict(actions),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="terraform show -json output")
    parser.add_argument("--frameworks-dir", type=Path, default=ROOT.parent.parent / "frameworks")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mode", choices=("greenfield", "noop"), default="greenfield")
    mode.add_argument("--allow-noop", action="store_true", help="allow only creates and no-ops")
    args = parser.parse_args(argv)
    try:
        selected_mode = "create-or-noop" if args.allow_noop else args.mode
        result = verify(json.loads(args.plan.read_text()), args.frameworks_dir, selected_mode)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ECR plan rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
