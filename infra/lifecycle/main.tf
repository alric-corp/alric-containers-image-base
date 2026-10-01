# Bootstrap with the two explicit administrator profiles. Runtime workflows
# receive only the Environment-bound roles below, never these credentials.
terraform {
  required_version = ">= 1.10.0"
  backend "local" {}
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.28"
    }
  }
}

variable "dev_profile" {
  type    = string
  default = "default"
}
variable "hom_profile" {
  type    = string
  default = "revolution-dev"
}

locals {
  config = jsondecode(file("${path.module}/../../policies/pipeline/config.json"))
  dev    = local.config.DEV
  hom    = local.config.HOM
  catalog = toset([
    for file in fileset("${path.module}/../../frameworks", "*.yaml") : trimsuffix(file, ".yaml")
  ])
  environments = { DEV = local.dev, HOM = local.hom }
  roles = {
    for env, cfg in local.environments : env => "arn:aws:iam::${cfg.account_id}:role/${cfg.role_name}"
  }
  repos = {
    for env, cfg in local.environments : env => [
      for name in sort(tolist(local.catalog)) : "arn:aws:ecr:${cfg.region}:${cfg.account_id}:repository/image-base-${name}"
    ]
  }
  read_actions = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability",
  "ecr:DescribeImages", "ecr:DescribeRepositories", "ecr:ListImages", "ecr:ListImageReferrers"]
  push_actions = ["ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"]
  trust = {
    for env, cfg in local.environments : env => {
      Version = "2012-10-17"
      Statement = [{
        Effect    = "Allow"
        Action    = "sts:AssumeRoleWithWebIdentity"
        Principal = { Federated = "arn:aws:iam::${cfg.account_id}:oidc-provider/token.actions.githubusercontent.com" }
        Condition = { StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "${local.config.subject_prefix}:environment:${env}"
        } }
      }]
    }
  }
  permissions = {
    for env, cfg in local.environments : env => {
      Version = "2012-10-17"
      Statement = concat([
        { Sid = "RegistryAuthentication", Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = ["*"] },
        { Sid = "OwnCatalog", Effect = "Allow", Action = concat(local.read_actions, local.push_actions), Resource = local.repos[env] },
        { Sid = "ReleaseInventory", Effect = "Allow", Action = ["s3:ListBucket"], Resource = ["arn:aws:s3:::${cfg.release_bucket}"] },
        { Sid = "ReleaseRecords", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = ["arn:aws:s3:::${cfg.release_bucket}/*"] }
        ], env == "HOM" ? [
        { Sid = "ReadDevCatalog", Effect = "Allow", Action = local.read_actions, Resource = local.repos.DEV },
        { Sid = "ReadDevReleaseInventory", Effect = "Allow", Action = ["s3:ListBucket"], Resource = ["arn:aws:s3:::${local.dev.release_bucket}"] },
        { Sid = "ReadDevReleases", Effect = "Allow", Action = ["s3:GetObject"], Resource = ["arn:aws:s3:::${local.dev.release_bucket}/releases/*"] }
      ] : [])
    }
  }
  bucket_policies = {
    for env, cfg in local.environments : env => {
      Version = "2012-10-17"
      Statement = concat([
        { Sid      = "TLSOnly", Effect = "Deny", Principal = "*", Action = "s3:*",
          Resource = ["arn:aws:s3:::${cfg.release_bucket}", "arn:aws:s3:::${cfg.release_bucket}/*"],
        Condition = { Bool = { "aws:SecureTransport" = "false" } } },
        { Sid      = "ImmutableReleaseRecords", Effect = "Deny", Principal = "*", Action = "s3:PutObject",
          Resource = [for prefix in ["releases", "promoted", "events"] : "arn:aws:s3:::${cfg.release_bucket}/${prefix}/*"],
        Condition = { Null = { "s3:if-none-match" = "true" } } }
        ], env == "DEV" ? [
        { Sid = "HOMInventory", Effect = "Allow", Principal = { AWS = local.roles.HOM },
        Action = ["s3:ListBucket"], Resource = ["arn:aws:s3:::${cfg.release_bucket}"] },
        { Sid = "HOMApprovedReleases", Effect = "Allow", Principal = { AWS = local.roles.HOM },
        Action = ["s3:GetObject"], Resource = ["arn:aws:s3:::${cfg.release_bucket}/releases/*"] }
      ] : [])
    }
  }
}

provider "aws" {
  alias               = "dev"
  profile             = var.dev_profile
  region              = local.dev.region
  allowed_account_ids = [local.dev.account_id]
}
provider "aws" {
  alias               = "hom"
  profile             = var.hom_profile
  region              = local.hom.region
  allowed_account_ids = [local.hom.account_id]
}

# Existing shared OIDC providers are referenced, not recreated or altered.
resource "aws_iam_role" "dev" {
  provider             = aws.dev
  name                 = local.dev.role_name
  max_session_duration = 10800
  assume_role_policy   = jsonencode(local.trust.DEV)
  tags                 = { ManagedBy = "Terraform", Source = local.config.repository, Environment = "DEV" }
}
resource "aws_iam_role" "hom" {
  provider             = aws.hom
  name                 = local.hom.role_name
  max_session_duration = 10800
  assume_role_policy   = jsonencode(local.trust.HOM)
  tags                 = { ManagedBy = "Terraform", Source = local.config.repository, Environment = "HOM" }
}
resource "aws_iam_role_policy" "dev" {
  provider = aws.dev
  name     = "factory-dev"
  role     = aws_iam_role.dev.id
  policy   = jsonencode(local.permissions.DEV)
}
resource "aws_iam_role_policy" "hom" {
  provider = aws.hom
  name     = "factory-hom"
  role     = aws_iam_role.hom.id
  policy   = jsonencode(local.permissions.HOM)
}

resource "aws_s3_bucket" "dev" {
  provider = aws.dev
  bucket   = local.dev.release_bucket
  lifecycle { prevent_destroy = true }
  tags = { ManagedBy = "Terraform", Source = local.config.repository, Environment = "DEV" }
}
resource "aws_s3_bucket" "hom" {
  provider = aws.hom
  bucket   = local.hom.release_bucket
  lifecycle { prevent_destroy = true }
  tags = { ManagedBy = "Terraform", Source = local.config.repository, Environment = "HOM" }
}
resource "aws_s3_bucket_versioning" "dev" {
  provider = aws.dev
  bucket   = aws_s3_bucket.dev.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_versioning" "hom" {
  provider = aws.hom
  bucket   = aws_s3_bucket.hom.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_public_access_block" "dev" {
  provider                = aws.dev
  bucket                  = aws_s3_bucket.dev.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_public_access_block" "hom" {
  provider                = aws.hom
  bucket                  = aws_s3_bucket.hom.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "dev" {
  provider = aws.dev
  bucket   = aws_s3_bucket.dev.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "hom" {
  provider = aws.hom
  bucket   = aws_s3_bucket.hom.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_ownership_controls" "dev" {
  provider = aws.dev
  bucket   = aws_s3_bucket.dev.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_ownership_controls" "hom" {
  provider = aws.hom
  bucket   = aws_s3_bucket.hom.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_policy" "dev" {
  provider   = aws.dev
  bucket     = aws_s3_bucket.dev.id
  policy     = jsonencode(local.bucket_policies.DEV)
  depends_on = [aws_iam_role.hom]
}
resource "aws_s3_bucket_policy" "hom" {
  provider = aws.hom
  bucket   = aws_s3_bucket.hom.id
  policy   = jsonencode(local.bucket_policies.HOM)
}

resource "aws_ecr_repository" "hom" {
  provider             = aws.hom
  for_each             = local.catalog
  name                 = "image-base-${each.value}"
  image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"
  image_tag_mutability_exclusion_filter {
    filter      = "stable"
    filter_type = "WILDCARD"
  }
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
  force_delete = false
  lifecycle { prevent_destroy = true }
  tags = { ManagedBy = "Terraform", Source = local.config.repository, Environment = "HOM" }
}
# HOM deliberately retains approved versions and trust artifacts for recovery.
# No age-only lifecycle can silently delete a recoverable release or its SBOM.

output "roles" { value = local.roles }
output "release_buckets" {
  value = { DEV = aws_s3_bucket.dev.id, HOM = aws_s3_bucket.hom.id }
}
output "hom_repositories" {
  value = { for key, value in aws_ecr_repository.hom : key => value.repository_url }
}
