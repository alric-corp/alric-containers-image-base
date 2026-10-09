# Native child-module tests run from infra/ecr. No second init/backend/state.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
}

run "private_bucket_contract" {
  command = plan
  module {
    source = "../s3"
  }
  variables {
    bucket_name           = "example-distroless-sbom-test"
    bucket_region         = "us-east-1"
    expected_bucket_owner = "123456789012"
    tags                  = { ManagedBy = "Terraform", Source = "alric-corp/alric-containers-image-base" }
  }
  assert {
    condition     = aws_s3_bucket.sbom.force_destroy == false && aws_s3_bucket.sbom.object_lock_enabled == false
    error_message = "Force destroy and Object Lock must stay disabled."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.sbom.block_public_acls && aws_s3_bucket_public_access_block.sbom.ignore_public_acls && aws_s3_bucket_public_access_block.sbom.block_public_policy && aws_s3_bucket_public_access_block.sbom.restrict_public_buckets
    error_message = "All four public access blocks are required."
  }
  assert {
    condition     = one(aws_s3_bucket_ownership_controls.sbom.rule).object_ownership == "BucketOwnerEnforced" && one(aws_s3_bucket_versioning.sbom.versioning_configuration).status == "Enabled"
    error_message = "ACLs must be disabled and versioning enabled."
  }
  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.sbom.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    error_message = "Explicit SSE-S3 is required."
  }
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.sbom.policy).Statement[1].Resource == "arn:aws:s3:::example-distroless-sbom-test/sbom-analytics/poc-v1/snapshots/*" && jsondecode(aws_s3_bucket_policy.sbom.policy).Statement[1].Condition.Null["s3:if-none-match"] == "true" && jsondecode(aws_s3_bucket_policy.sbom.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "Conditional writes must protect snapshots only, and TLS is mandatory."
  }
  assert {
    condition     = output.ingestion_config == { protocol_version = 1, destination = { bucket = "example-distroless-sbom-test", prefix = "sbom-analytics/poc-v1", region = "us-east-1", expected_bucket_owner = "123456789012" } } && output.query_results_prefix == "query-results/poc-v1/"
    error_message = "Outputs must match the integrated ingestion contract."
  }
}

run "reject_wrong_owner" {
  command = plan
  module {
    source = "../s3"
  }
  variables {
    bucket_name           = "example-distroless-sbom-test"
    bucket_region         = "us-east-1"
    expected_bucket_owner = "999999999999"
    tags                  = {}
  }
  expect_failures = [aws_s3_bucket.sbom]
}

run "reject_invalid_bucket" {
  command = plan
  module {
    source = "../s3"
  }
  variables {
    bucket_name           = "UNSAFE_BUCKET"
    bucket_region         = "us-east-1"
    expected_bucket_owner = "123456789012"
    tags                  = {}
  }
  expect_failures = [var.bucket_name]
}
