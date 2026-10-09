#!/usr/bin/env python3
"""Reject a plan outside the existing ECR catalog and six SBOM S3 resources.

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
sys.path.insert(0, str(ROOT.parent))
from s3.contract import ADDRESSES as S3_ADDRESSES, bucket_policy, unique_json
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
    """The proposed plan does not satisfy the operational Infra boundary."""


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


def validate_s3(address, kind, values, change, configuration, bucket, account, region):
    if not isinstance(values, dict):
        raise PlanError(f"{address}: absent S3 values")
    if values.get('region') != region:
        raise PlanError(f"{address}: unexpected S3 region")
    def unknown(value):
        if isinstance(value, dict):
            return any(unknown(item) for item in value.values())
        if isinstance(value, list):
            return any(unknown(item) for item in value)
        return value is True
    required_known = {
        'aws_s3_bucket': ('bucket', 'region', 'tags', 'force_destroy', 'object_lock_enabled'),
        'aws_s3_bucket_public_access_block': ('region', 'block_public_acls', 'ignore_public_acls', 'block_public_policy', 'restrict_public_buckets'),
        'aws_s3_bucket_ownership_controls': ('region', 'rule'),
        'aws_s3_bucket_versioning': ('region', 'expected_bucket_owner'),
        'aws_s3_bucket_server_side_encryption_configuration': ('region', 'expected_bucket_owner'),
        'aws_s3_bucket_policy': ('region', 'policy'),
    }[kind]
    if any(unknown(change.get('after_unknown', {}).get(key)) for key in required_known):
        raise PlanError(f"{address}: security or identity value is unknown")
    if kind == 'aws_s3_bucket':
        if values.get('bucket') != bucket or values.get('force_destroy') is not False:
            raise PlanError(f"{address}: incorrect bucket identity or force_destroy")
        tags = values.get('tags')
        if not isinstance(tags, dict) or any(tags.get(k) != v for k, v in PROVENANCE.items()):
            raise PlanError(f"{address}: incorrect S3 provenance tags")
        # Computed provider compatibility fields are not proof of configured ACLs.
        for field in ('acl', 'grant', 'lifecycle_rule', 'logging', 'replication_configuration',
                      'object_lock_configuration', 'website'):
            if (field in configuration.get('expressions', {})
                    or field == 'acl' and values.get(field) not in (None, 'private')
                    or field not in ('acl', 'grant') and values.get(field)):
                raise PlanError(f"{address}: forbidden S3 {field}")
        if values.get('object_lock_enabled') is not False:
            raise PlanError(f"{address}: Object Lock is outside this contract")
        return
    # A new bucket's ID is computed. Validate both its unknown marker and the
    # exact configuration reference; unknown values alone never approve a link.
    refs = configuration.get('expressions', {}).get('bucket', {}).get('references', [])
    if (set(refs) - {'aws_s3_bucket.sbom', 'aws_s3_bucket.sbom.id'}
            or 'aws_s3_bucket.sbom.id' not in refs):
        raise PlanError(f"{address}: bucket dependency differs")
    if values.get('bucket') != bucket:
        if (change.get('actions') != ['create'] or values.get('bucket') is not None
                or change.get('after_unknown', {}).get('bucket') is not True):
            raise PlanError(f"{address}: unknown or incorrect bucket binding")
    if kind == 'aws_s3_bucket_public_access_block':
        if any(values.get(key) is not True for key in (
                'block_public_acls', 'ignore_public_acls', 'block_public_policy', 'restrict_public_buckets')):
            raise PlanError(f"{address}: public access block must enable all four controls")
    elif kind == 'aws_s3_bucket_ownership_controls':
        if values.get('rule') != [{'object_ownership': 'BucketOwnerEnforced'}]:
            raise PlanError(f"{address}: ownership must disable ACLs")
    elif kind == 'aws_s3_bucket_versioning':
        rules = values.get('versioning_configuration', [])
        flags = change.get('after_unknown', {}).get('versioning_configuration', [])
        if (len(rules) != 1 or rules[0].get('status') != 'Enabled'
                or flags is True or isinstance(flags, list) and any(r.get('status') is True for r in flags)
                or rules[0].get('mfa_delete') not in (None, 'Disabled')
                or values.get('expected_bucket_owner') != account):
            raise PlanError(f"{address}: versioning or owner differs")
    elif kind == 'aws_s3_bucket_server_side_encryption_configuration':
        rules = values.get('rule', [])
        encryption = rules[0].get('apply_server_side_encryption_by_default', []) if len(rules) == 1 else []
        flags = change.get('after_unknown', {}).get('rule', [])
        # blocked_encryption_types is an optional provider observation, not a
        # required control. Required algorithm/key inputs must remain known.
        if flags is True:
            raise PlanError(f"{address}: encryption rule is unknown")
        for flag in flags:
            key_flags = flag.get('apply_server_side_encryption_by_default', [])
            if (flag.get('bucket_key_enabled') is True or key_flags is True
                    or any(k.get('sse_algorithm') is True for k in key_flags)):
                raise PlanError(f"{address}: encryption algorithm/key is unknown")
            if any(k.get('kms_master_key_id') is True for k in key_flags):
                configured = configuration.get('expressions', {}).get('rule', [])
                default = configured[0].get('apply_server_side_encryption_by_default', []) if len(configured) == 1 else []
                # The SDK marks the empty optional KMS response as computed.
                # Approve the *input* only when this exact create configuration
                # explicitly supplies no key and the required AES256 algorithm.
                if (change.get('actions') != ['create'] or len(default) != 1
                        or default[0].get('kms_master_key_id') != {'constant_value': ''}
                        or default[0].get('sse_algorithm') != {'constant_value': 'AES256'}):
                    raise PlanError(f"{address}: computed KMS field lacks a proven empty configuration")
        if (len(encryption) != 1 or encryption[0].get('sse_algorithm') != 'AES256'
                or encryption[0].get('kms_master_key_id') or values.get('expected_bucket_owner') != account
                or rules[0].get('bucket_key_enabled') is True):
            raise PlanError(f"{address}: explicit SSE-S3 or owner differs")
    elif kind == 'aws_s3_bucket_policy':
        try:
            actual = json.loads(values.get('policy', ''), object_pairs_hook=unique_json)
        except (TypeError, ValueError) as exc:
            raise PlanError(f"{address}: policy is unknown or invalid") from exc
        if actual != bucket_policy(bucket):
            raise PlanError(f"{address}: S3 policy differs from the exact contract")
        required = {f'{kind}.sbom' for kind in S3_ADDRESSES.values() if kind not in ('aws_s3_bucket', 'aws_s3_bucket_policy')}
        if set(configuration.get('depends_on', [])) != required:
            raise PlanError(f"{address}: policy must depend on all four security controls")


def verify(plan, frameworks_dir=ROOT.parent.parent / "frameworks", mode="sbom-adoption", *,
           account_id, region, bucket_name=None):
    if mode not in {"sbom-adoption", "noop"}:
        raise PlanError(f"unsupported verification mode: {mode}")
    if plan.get("errored") or plan.get("complete") is False or plan.get("deferred_changes"):
        raise PlanError("plan is errored, incomplete or contains deferred changes")
    if any(check.get("status") not in {"pass"} for check in plan.get("checks", [])):
        raise PlanError("plan contains an unresolved or failed check")
    frameworks = catalog(frameworks_dir)
    expected = expected_resources(frameworks)
    expected.update({address: (None, kind) for address, kind in S3_ADDRESSES.items()})
    if not re.fullmatch(r'[0-9]{12}', account_id) or not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-[0-9]+', region):
        raise PlanError('external account and region are required')
    bucket = bucket_name or f'alric-distroless-sbom-{account_id}-{region}'
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', bucket):
        raise PlanError('invalid expected bucket name')
    variables = plan.get('variables', {})
    if (variables.get('aws_region', {}).get('value') != region
            or variables.get('expected_bucket_owner', {}).get('value') != account_id
            or variables.get('sbom_bucket_name', {}).get('value') not in (None, bucket)):
        raise PlanError('plan variables differ from external identity')
    calls = plan.get('configuration', {}).get('root_module', {}).get('module_calls', {})
    if set(calls) != {'ecr', 'sbom'} or calls['sbom'].get('source') != '../s3':
        raise PlanError('execution root/module source differs from infra/ecr -> ../s3')
    if (calls['ecr'].get('source') != 'terraform-aws-modules/ecr/aws'
            or calls['ecr'].get('version_constraint') != '3.2.0'):
        raise PlanError('existing ECR module source/version must remain pinned')
    configuration = resource_map(
        ({**item, 'address': 'module.sbom.' + item['address']} for item in
         calls['sbom'].get('module', {}).get('resources', []) if item.get('mode') == 'managed'),
        S3_ADDRESSES, 'S3 configuration')
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
    prior = list(managed_resources(plan.get('prior_state', {}).get('values', {}).get('root_module', {})))
    prior_addresses = [resource.get('address') for resource in prior]
    if (len(set(prior_addresses)) != len(prior_addresses)
            or set(prior_addresses) - set(expected)
            or set(expected_resources(frameworks)) - set(prior_addresses)
            or mode == 'noop' and set(prior_addresses) != set(expected)):
        raise PlanError('prior state must retain every ECR address and no unexpected resources')
    actions = Counter()
    for address, (framework, kind) in expected.items():
        item = changes[address]
        change = item.get("change", {})
        action = tuple(change.get("actions", []))
        allowed = {('no-op',)} if framework is not None or mode == 'noop' else {('create',), ('no-op',)}
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
            if framework is None:
                validate_s3(address, kind, values, change, configuration[address], bucket, account_id, region)
            else:
                validate_values(address, framework, kind, values, policies)
        if action == ('no-op',) and change.get('before') != change.get('after'):
            raise PlanError(f"{address}: no-op before and after must be identical")
        actions[action[0]] += 1
    return {
        "mode": mode,
        "frameworks": frameworks,
        "repository_count": len(frameworks),
        "managed_resource_count": len(expected),
        "resource_types": dict(Counter(kind for _, kind in expected.values())),
        "actions": dict(actions),
        "bucket_name": bucket,
        "account_id": account_id,
        "region": region,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="terraform show -json output")
    parser.add_argument("--frameworks-dir", type=Path, default=ROOT.parent.parent / "frameworks")
    parser.add_argument('--mode', choices=('sbom-adoption', 'noop'), default='sbom-adoption')
    parser.add_argument('--account-id', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--bucket-name')
    args = parser.parse_args(argv)
    try:
        result = verify(json.loads(args.plan.read_text(), object_pairs_hook=unique_json),
                        args.frameworks_dir, args.mode, account_id=args.account_id,
                        region=args.region, bucket_name=args.bucket_name)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ECR plan rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
