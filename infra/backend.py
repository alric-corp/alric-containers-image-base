#!/usr/bin/env python3
"""Ensure the S3 backend before Terraform init, independently of Terraform state.

Policy: create and configure an absent bucket; validate an existing bucket without
changing it. Existing unsafe buckets, ambiguous AWS failures, creation races and
partial bootstrap failures require explicit operator remediation. Never delete a
bucket, change an existing bucket's controls, or inspect Terraform state objects.
Creating absent buckets in us-east-1 is rejected because S3's legacy CreateBucket
success semantics cannot distinguish a successful create from an ownership race.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable


PUBLIC_ACCESS_BLOCK = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}
ENCRYPTION = {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}
OWNERSHIP = {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}
AWS_ERROR = re.compile(r"An error occurred \(([^)]+)\) when calling the ([A-Za-z0-9]+) operation")


class BackendError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.created = False


class AwsError(BackendError):
    pass


class AwsCli:
    def __init__(self, region: str, runner: Callable[..., Any] = subprocess.run) -> None:
        self.region = region
        self.runner = runner

    def call(self, service: str, operation: str, **parameters: Any) -> dict[str, Any]:
        command = ["aws", service, operation, "--region", self.region, "--output", "json", "--no-cli-pager"]
        for name, value in parameters.items():
            command.extend(["--" + name.replace("_", "-"), json.dumps(value) if isinstance(value, (dict, list)) else str(value)])
        environment = {**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"}
        try:
            result = self.runner(command, capture_output=True, text=True, check=False, timeout=60, env=environment)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AwsError("AWS_EXECUTION_FAILED", f"AWS {service} {operation} could not complete ({type(exc).__name__})") from exc
        if result.returncode:
            match = AWS_ERROR.search(result.stderr or "")
            code = match.group(1) if match else "AWS_CLI_ERROR"
            # Never emit unfiltered CLI output: it may contain credentials or a URL.
            raise AwsError(code, f"AWS {service} {operation} failed ({code})")
        try:
            body = json.loads(result.stdout) if result.stdout.strip() else {}
        except (TypeError, ValueError) as exc:
            raise AwsError("INVALID_AWS_RESPONSE", f"AWS {service} {operation} returned invalid JSON") from exc
        if not isinstance(body, dict):
            raise AwsError("INVALID_AWS_RESPONSE", f"AWS {service} {operation} did not return an object")
        return body


def validate_inputs(bucket: str, region: str, account_id: str) -> None:
    if not re.fullmatch(r"[0-9]{12}", account_id):
        raise BackendError("INVALID_ACCOUNT", "Expected account ID must contain exactly 12 digits")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-[0-9]+", region):
        raise BackendError("INVALID_REGION", "An explicit AWS region is required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise BackendError("INVALID_BUCKET", "Bucket name must be a valid 3-63 character S3 bucket name")
    if any(part in bucket for part in ("..", ".-", "-.")) or bucket.startswith(("xn--", "sthree-", "amzn-s3-demo-")) or bucket.endswith(("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3")):
        raise BackendError("INVALID_BUCKET", "Bucket name contains a reserved or invalid S3 name component")
    try:
        ipaddress.ip_address(bucket)
    except ValueError:
        pass
    else:
        raise BackendError("INVALID_BUCKET", "An IP address cannot be used as a bucket name")


def validate_controls(aws: AwsCli, bucket: str, region: str, account_id: str) -> dict[str, Any]:
    target = {"bucket": bucket, "expected_bucket_owner": account_id}
    # The owner constraint applies to every bucket access, including read-back.
    aws.call("s3api", "head-bucket", **target)
    location_response = aws.call("s3api", "get-bucket-location", **target)
    if "LocationConstraint" not in location_response:
        raise BackendError("INVALID_AWS_RESPONSE", "S3 did not return the backend bucket's location")
    location = location_response["LocationConstraint"]
    actual_region = "us-east-1" if location is None else "eu-west-1" if location == "EU" else location
    if actual_region != region:
        raise BackendError("REGION_MISMATCH", f"Backend bucket is in {actual_region}, expected {region}")
    versioning = aws.call("s3api", "get-bucket-versioning", **target)
    if versioning.get("Status") != "Enabled":
        raise BackendError("UNSAFE_VERSIONING", "Existing backend must have versioning Enabled; reconciliation is forbidden")
    encryption = aws.call("s3api", "get-bucket-encryption", **target)
    configuration = encryption.get("ServerSideEncryptionConfiguration")
    rules = configuration.get("Rules") if isinstance(configuration, dict) else None
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(rules[0], dict) or rules[0].get("ApplyServerSideEncryptionByDefault") != {"SSEAlgorithm": "AES256"}:
        raise BackendError("UNSAFE_ENCRYPTION", "Existing backend must use default AES256 encryption; reconciliation is forbidden")
    public_access = aws.call("s3api", "get-public-access-block", **target).get("PublicAccessBlockConfiguration", {})
    if not isinstance(public_access, dict) or any(public_access.get(control) is not True for control in PUBLIC_ACCESS_BLOCK):
        raise BackendError("UNSAFE_PUBLIC_ACCESS", "Existing backend must enable all four public access blocks; reconciliation is forbidden")
    ownership = aws.call("s3api", "get-bucket-ownership-controls", **target).get("OwnershipControls")
    if ownership != OWNERSHIP:
        raise BackendError("UNSAFE_OWNERSHIP", "Existing backend must enforce BucketOwnerEnforced; reconciliation is forbidden")
    return {
        "owner_verified": True,
        "region": actual_region,
        "versioning": "Enabled",
        "encryption": "AES256",
        "public_access_block": PUBLIC_ACCESS_BLOCK.copy(),
        "ownership": "BucketOwnerEnforced",
    }


def ensure_backend(bucket: str, region: str, account_id: str, aws: AwsCli | None = None) -> dict[str, Any]:
    validate_inputs(bucket, region, account_id)
    aws = aws or AwsCli(region)
    created = False
    try:
        identity = aws.call("sts", "get-caller-identity")
        if identity.get("Account") != account_id:
            raise BackendError("ACCOUNT_MISMATCH", "AWS caller does not belong to the expected LAB account")
        target = {"bucket": bucket, "expected_bucket_owner": account_id}
        try:
            aws.call("s3api", "head-bucket", **target)
        except AwsError as exc:
            if exc.code not in {"404", "NoSuchBucket"}:
                raise
            if region == "us-east-1":
                # https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateBucket.html
                # In this region S3 may report 200 for a concurrently created,
                # already owned bucket and reset its ACLs. Do not take that risk.
                raise BackendError("AMBIGUOUS_CREATE_REGION", "Absent backends must use a region other than us-east-1 for unambiguous create collision handling") from exc
            create_parameters: dict[str, Any] = {
                "bucket": bucket,
                "object_ownership": "BucketOwnerEnforced",
                "create_bucket_configuration": {"LocationConstraint": region},
            }
            # Any creation error, including BucketAlreadyOwnedByYou, fails closed.
            # A concurrent creator must never cause us to alter an existing bucket.
            aws.call("s3api", "create-bucket", **create_parameters)
            created = True
            aws.call("s3api", "head-bucket", **target)
            aws.call("s3api", "put-public-access-block", **target, public_access_block_configuration=PUBLIC_ACCESS_BLOCK)
            aws.call("s3api", "put-bucket-ownership-controls", **target, ownership_controls=OWNERSHIP)
            aws.call("s3api", "put-bucket-encryption", **target, server_side_encryption_configuration=ENCRYPTION)
            aws.call("s3api", "put-bucket-versioning", **target, versioning_configuration={"Status": "Enabled"})
        controls = validate_controls(aws, bucket, region, account_id)
    except BackendError as exc:
        exc.created = created
        raise
    return {
        "status": "PASS",
        "action": "created" if created else "reused",
        "bucket": bucket,
        "account_id": account_id,
        "region": region,
        "existing_bucket_policy": "validate_only_fail_on_misconfiguration",
        "controls": controls,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    ensure = subparsers.add_parser("ensure", help="Create an absent backend or strictly validate an existing backend")
    ensure.add_argument("--bucket", required=True)
    ensure.add_argument("--region", required=True)
    ensure.add_argument("--account-id", required=True)
    arguments = parser.parse_args(argv)
    try:
        result = ensure_backend(arguments.bucket, arguments.region, arguments.account_id)
    except BackendError as exc:
        print(json.dumps({
            "status": "FAIL", "error": exc.code, "message": str(exc),
            "bucket": arguments.bucket, "region": arguments.region,
            "account_id": arguments.account_id, "created": exc.created,
            "requires_manual_remediation": exc.created,
        }, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
