"""Fail-closed backend bootstrap contracts; no AWS credentials or network needed."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest


SPEC = importlib.util.spec_from_file_location("backend", Path(__file__).resolve().parents[1] / "backend.py")
backend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backend)

ACCOUNT = "123456789012"
BUCKET = "image-base-lab-tfstate-123456789012"
REGION = "us-east-2"


class FakeAws:
    """Model CLI calls, ownership constraints and persistent S3 configuration."""

    def __init__(self, exists=True, configured=True):
        self.exists = exists
        self.account = ACCOUNT
        self.region = REGION
        self.calls = []
        self.failures = {}
        self.absent_code = "404"
        self.versioning = {"Status": "Enabled"} if configured else {}
        self.encryption = copy.deepcopy(backend.ENCRYPTION) if configured else {}
        self.public_access = backend.PUBLIC_ACCESS_BLOCK.copy() if configured else {}
        self.ownership = copy.deepcopy(backend.OWNERSHIP) if configured else {}

    @property
    def mutations(self):
        return [operation for operation, _ in self.calls if operation.startswith(("create-", "put-", "delete-"))]

    def __call__(self, command, **kwargs):
        self.assert_environment(kwargs)
        service, operation = command[1:3]
        parameters = {}
        index = 3
        while index < len(command):
            option = command[index]
            if option == "--no-cli-pager":
                index += 1
                continue
            parameters[option.removeprefix("--")] = command[index + 1]
            index += 2
        self.calls.append((operation, parameters))
        if operation in self.failures:
            return self.failure(command, operation, self.failures[operation])
        if service == "sts":
            return self.success(command, {"Account": self.account})
        assert parameters["bucket"] == BUCKET
        if operation != "create-bucket":
            assert parameters["expected-bucket-owner"] == ACCOUNT
        if operation == "head-bucket":
            return self.success(command, {}) if self.exists else self.failure(command, operation, self.absent_code)
        if operation == "create-bucket":
            if self.exists:
                return self.failure(command, operation, "BucketAlreadyOwnedByYou")
            self.exists = True
            assert parameters["object-ownership"] == "BucketOwnerEnforced"
            if parameters["region"] == "us-east-1":
                assert "create-bucket-configuration" not in parameters
            else:
                assert json.loads(parameters["create-bucket-configuration"]) == {"LocationConstraint": self.region}
            return self.success(command, {})
        if operation == "get-bucket-location":
            return self.success(command, {"LocationConstraint": None if self.region == "us-east-1" else self.region})
        configuration = {
            "bucket-versioning": ("versioning", "versioning-configuration", None),
            "bucket-encryption": ("encryption", "server-side-encryption-configuration", "ServerSideEncryptionConfiguration"),
            "public-access-block": ("public_access", "public-access-block-configuration", "PublicAccessBlockConfiguration"),
            "bucket-ownership-controls": ("ownership", "ownership-controls", "OwnershipControls"),
        }
        action, key = operation.split("-", 1)
        attribute, option, envelope = configuration[key]
        if action == "put":
            setattr(self, attribute, json.loads(parameters[option]))
            return self.success(command, {})
        body = getattr(self, attribute)
        return self.success(command, {envelope: body} if envelope else body)

    @staticmethod
    def assert_environment(kwargs):
        assert kwargs["timeout"] == 60
        assert kwargs["env"]["AWS_PAGER"] == ""
        assert kwargs["env"]["AWS_CLI_AUTO_PROMPT"] == "off"
        assert kwargs["check"] is False

    @staticmethod
    def success(command, body):
        return subprocess.CompletedProcess(command, 0, json.dumps(body), "")

    @staticmethod
    def failure(command, operation, code):
        api = "".join(part.capitalize() for part in operation.split("-"))
        return subprocess.CompletedProcess(command, 254, "", f"An error occurred ({code}) when calling the {api} operation: unavailable")


class BackendTests(unittest.TestCase):
    def ensure(self, fake, region=REGION):
        return backend.ensure_backend(BUCKET, region, ACCOUNT, backend.AwsCli(region, fake))

    def test_absent_bucket_created_configured_and_read_back(self):
        fake = FakeAws(exists=False, configured=False)
        evidence = self.ensure(fake)
        self.assertEqual(evidence["action"], "created")
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(fake.mutations, ["create-bucket", "put-public-access-block", "put-bucket-ownership-controls", "put-bucket-encryption", "put-bucket-versioning"])
        self.assertTrue(evidence["controls"]["owner_verified"])
        self.assertEqual(evidence["controls"]["versioning"], "Enabled")
        self.assertEqual(fake.calls[-1][0], "get-bucket-ownership-controls")

    def test_no_such_bucket_also_authorizes_creation(self):
        fake = FakeAws(exists=False, configured=False)
        fake.absent_code = "NoSuchBucket"
        self.assertEqual(self.ensure(fake)["action"], "created")

    def test_us_east_1_absent_fails_before_ambiguous_create(self):
        fake = FakeAws(exists=False, configured=False)
        fake.region = "us-east-1"
        with self.assertRaises(backend.BackendError) as caught:
            self.ensure(fake, region="us-east-1")
        self.assertEqual(caught.exception.code, "AMBIGUOUS_CREATE_REGION")
        self.assertEqual(fake.mutations, [])

    def test_us_east_1_existing_safe_bucket_can_be_validated(self):
        fake = FakeAws()
        fake.region = "us-east-1"
        self.assertEqual(self.ensure(fake, region="us-east-1")["action"], "reused")
        self.assertEqual(fake.mutations, [])

    def test_existing_configured_bucket_is_read_only(self):
        fake = FakeAws()
        before = copy.deepcopy((fake.versioning, fake.encryption, fake.public_access, fake.ownership))
        self.assertEqual(self.ensure(fake)["action"], "reused")
        self.assertEqual(fake.mutations, [])
        self.assertEqual(before, (fake.versioning, fake.encryption, fake.public_access, fake.ownership))

    def test_create_then_rerun_is_read_only(self):
        fake = FakeAws(exists=False, configured=False)
        self.ensure(fake)
        fake.calls.clear()
        self.assertEqual(self.ensure(fake)["action"], "reused")
        self.assertEqual(fake.mutations, [])

    def test_each_unsafe_control_fails_without_mutations(self):
        examples = [
            ("versioning", {}, "UNSAFE_VERSIONING"),
            ("versioning", {"Status": "Suspended"}, "UNSAFE_VERSIONING"),
            ("encryption", {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]}, "UNSAFE_ENCRYPTION"),
            ("encryption", {"Rules": ["malformed"]}, "UNSAFE_ENCRYPTION"),
            ("encryption", None, "UNSAFE_ENCRYPTION"),
            ("public_access", {**backend.PUBLIC_ACCESS_BLOCK, "BlockPublicPolicy": False}, "UNSAFE_PUBLIC_ACCESS"),
            ("public_access", {**backend.PUBLIC_ACCESS_BLOCK, "BlockPublicPolicy": "true"}, "UNSAFE_PUBLIC_ACCESS"),
            ("ownership", {"Rules": [{"ObjectOwnership": "ObjectWriter"}]}, "UNSAFE_OWNERSHIP"),
        ]
        for attribute, value, error in examples:
            with self.subTest(attribute=attribute, value=value):
                fake = FakeAws()
                setattr(fake, attribute, value)
                with self.assertRaises(backend.BackendError) as caught:
                    self.ensure(fake)
                self.assertEqual(caught.exception.code, error)
                self.assertEqual(fake.mutations, [])

    def test_region_mismatch_fails_without_mutations(self):
        fake = FakeAws()
        fake.region = "eu-west-1"
        with self.assertRaises(backend.BackendError) as caught:
            self.ensure(fake)
        self.assertEqual(caught.exception.code, "REGION_MISMATCH")
        self.assertEqual(fake.mutations, [])

    def test_wrong_account_stops_before_s3(self):
        fake = FakeAws()
        fake.account = "999999999999"
        with self.assertRaises(backend.BackendError) as caught:
            self.ensure(fake)
        self.assertEqual(caught.exception.code, "ACCOUNT_MISMATCH")
        self.assertEqual([operation for operation, _ in fake.calls], ["get-caller-identity"])

    def test_access_denied_and_ambiguous_head_errors_never_create(self):
        for error in ("403", "AccessDenied", "301", "500", "NotFound", "InvalidToken"):
            with self.subTest(error=error):
                fake = FakeAws(exists=False)
                fake.failures["head-bucket"] = error
                with self.assertRaises(backend.AwsError):
                    self.ensure(fake)
                self.assertEqual(fake.mutations, [])

    def test_creation_collision_fails_without_configuring_bucket(self):
        for error in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou", "OperationAborted"):
            with self.subTest(error=error):
                fake = FakeAws(exists=False)
                fake.failures["create-bucket"] = error
                with self.assertRaises(backend.AwsError) as caught:
                    self.ensure(fake)
                self.assertFalse(caught.exception.created)
                self.assertEqual(fake.mutations, ["create-bucket"])

    def test_partial_bootstrap_never_deletes_or_implicitly_repairs(self):
        fake = FakeAws(exists=False, configured=False)
        fake.failures["put-bucket-encryption"] = "AccessDenied"
        with self.assertRaises(backend.AwsError) as caught:
            self.ensure(fake)
        self.assertTrue(caught.exception.created)
        self.assertTrue(fake.exists)
        self.assertNotIn("delete-bucket", fake.mutations)
        fake.calls.clear()
        fake.failures.clear()
        with self.assertRaises(backend.BackendError) as retry:
            self.ensure(fake)
        self.assertEqual(retry.exception.code, "UNSAFE_VERSIONING")
        self.assertEqual(fake.mutations, [])

    def test_missing_existing_controls_fails_without_mutations(self):
        fake = FakeAws()
        fake.failures["get-public-access-block"] = "NoSuchPublicAccessBlockConfiguration"
        with self.assertRaises(backend.AwsError):
            self.ensure(fake)
        self.assertEqual(fake.mutations, [])

    def test_invalid_inputs_fail_before_aws(self):
        invalid = [
            ("UPPERCASE", REGION, ACCOUNT), ("192.168.0.1", REGION, ACCOUNT),
            ("a..b", REGION, ACCOUNT), ("x--x-s3", REGION, ACCOUNT),
            (BUCKET, "", ACCOUNT), (BUCKET, REGION, "123"),
        ]
        for bucket, region, account in invalid:
            with self.subTest(bucket=bucket, region=region, account=account):
                fake = FakeAws()
                with self.assertRaises(backend.BackendError):
                    backend.ensure_backend(bucket, region, account, backend.AwsCli(region, fake))
                self.assertEqual(fake.calls, [])

    def test_cli_response_must_be_json_object(self):
        for payload in ("[]", "not-json"):
            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, payload, "")
            with self.subTest(payload=payload), self.assertRaises(backend.AwsError) as caught:
                backend.AwsCli(REGION, runner).call("sts", "get-caller-identity")
            self.assertEqual(caught.exception.code, "INVALID_AWS_RESPONSE")

    def test_cli_timeout_fails_closed(self):
        def runner(command, **kwargs):
            raise subprocess.TimeoutExpired(command, 60)
        with self.assertRaises(backend.AwsError) as caught:
            backend.AwsCli(REGION, runner).call("sts", "get-caller-identity")
        self.assertEqual(caught.exception.code, "AWS_EXECUTION_FAILED")


if __name__ == "__main__":
    unittest.main()
