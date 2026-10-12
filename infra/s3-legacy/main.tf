# LEGACY, TRANSITIONAL ONLY: the historical bucket replaced by Distroless SBOM
# Analytics (authorized 2026-10-11), with its real historical prefix.
# Same resources and bucket policy as before. Destruction is enabled here so
# the next revision can remove the bucket, versions included, after the new
# analytics proof. The active module (../s3) keeps prevent_destroy = true and
# force_destroy = false.
locals {
  bucket_arn       = "arn:aws:s3:::${var.bucket_name}"
  snapshots_prefix = "sbom-analytics/poc-v1/snapshots/"
  bucket_policy = {
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [local.bucket_arn, "${local.bucket_arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "DenySnapshotUnconditionalPut"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${local.bucket_arn}/${local.snapshots_prefix}*"
        Condition = {
          Null = { "s3:if-none-match" = "true" }
          Bool = { "s3:ObjectCreationOperation" = "true" }
        }
      },
      {
        Sid       = "DenySnapshotOtherCondition"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${local.bucket_arn}/${local.snapshots_prefix}*"
        Condition = {
          Null            = { "s3:if-none-match" = "false" }
          StringNotEquals = { "s3:if-none-match" = "*" }
          Bool            = { "s3:ObjectCreationOperation" = "true" }
        }
      }
    ]
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "sbom" {
  bucket              = var.bucket_name
  region              = var.bucket_region
  force_destroy       = true
  object_lock_enabled = false
  tags                = var.tags
  lifecycle {
    prevent_destroy = false
    precondition {
      condition     = data.aws_caller_identity.current.account_id == var.expected_bucket_owner
      error_message = "The session account must match the externally configured bucket owner."
    }
  }
}

resource "aws_s3_bucket_public_access_block" "sbom" {
  bucket                  = aws_s3_bucket.sbom.id
  region                  = var.bucket_region
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  region = var.bucket_region
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "sbom" {
  bucket                = aws_s3_bucket.sbom.id
  region                = var.bucket_region
  expected_bucket_owner = var.expected_bucket_owner
  rule {
    bucket_key_enabled = false
    apply_server_side_encryption_by_default {
      sse_algorithm     = "AES256"
      kms_master_key_id = ""
    }
  }
}

resource "aws_s3_bucket_versioning" "sbom" {
  bucket                = aws_s3_bucket.sbom.id
  region                = var.bucket_region
  expected_bucket_owner = var.expected_bucket_owner
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_policy" "sbom" {
  bucket = aws_s3_bucket.sbom.id
  region = var.bucket_region
  policy = jsonencode(local.bucket_policy)
  depends_on = [
    aws_s3_bucket_public_access_block.sbom,
    aws_s3_bucket_ownership_controls.sbom,
    aws_s3_bucket_server_side_encryption_configuration.sbom,
    aws_s3_bucket_versioning.sbom,
  ]
}
