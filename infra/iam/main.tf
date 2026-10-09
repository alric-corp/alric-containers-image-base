provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]
}

locals {
  catalog = sort([
    for definition in fileset("${path.module}/../../frameworks", "*.yaml") : trimsuffix(definition, ".yaml")
  ])
  repository_arns = [
    for framework in local.catalog : "arn:aws:ecr:${var.aws_region}:${var.aws_account_id}:repository/image-base-${framework}"
  ]
  bucket_arn = "arn:aws:s3:::${var.backend_bucket}"
  state_key  = "alric-containers-image-base/terraform.tfstate"
  state_arn  = "${local.bucket_arn}/${local.state_key}"
  lock_arn   = "${local.state_arn}.tflock"
  # Same default name as module.sbom in infra/ecr/s3.tf; one exact bucket ARN.
  analytics_bucket_arn = "arn:aws:s3:::alric-distroless-sbom-${var.aws_account_id}-${var.aws_region}"

  ecr_read_actions = [
    "ecr:DescribeRepositories",
    "ecr:GetRepositoryPolicy",
    "ecr:GetLifecyclePolicy",
    "ecr:ListTagsForResource",
  ]
  ecr_apply_actions = [
    "ecr:DescribeImages",
    "ecr:CreateRepository",
    "ecr:PutLifecyclePolicy",
    "ecr:SetRepositoryPolicy",
    "ecr:TagResource",
    "ecr:UntagResource",
    "ecr:PutImageScanningConfiguration",
    "ecr:PutImageTagMutability",
  ]
  # Reads made by the pinned AWS provider and the S3 read-back (infra/s3/permissions.md).
  analytics_read_actions = [
    "s3:ListBucket",
    "s3:GetBucketLocation",
    "s3:GetBucketAcl",
    "s3:GetBucketCORS",
    "s3:GetBucketWebsite",
    "s3:GetBucketVersioning",
    "s3:GetBucketLogging",
    "s3:GetBucketTagging",
    "s3:ListTagsForResource",
    "s3:GetBucketRequestPayment",
    "s3:GetAccelerateConfiguration",
    "s3:GetReplicationConfiguration",
    "s3:GetLifecycleConfiguration",
    "s3:GetEncryptionConfiguration",
    "s3:GetBucketObjectLockConfiguration",
    "s3:GetBucketPublicAccessBlock",
    "s3:GetBucketOwnershipControls",
    "s3:GetBucketPolicy",
  ]
  # Creation and configuration only: no object access, no deletion.
  analytics_apply_actions = [
    "s3:CreateBucket",
    "s3:PutBucketPublicAccessBlock",
    "s3:PutBucketOwnershipControls",
    "s3:PutEncryptionConfiguration",
    "s3:PutBucketVersioning",
    "s3:PutBucketPolicy",
    "s3:TagResource",
    "s3:PutBucketTagging",
  ]
  subjects = {
    plan  = "${var.github_subject_prefix}:pull_request"
    apply = "${var.github_subject_prefix}:environment:${var.github_apply_environment}"
  }
  trust_policies = {
    for purpose, subject in local.subjects : purpose => {
      Version = "2012-10-17"
      Statement = [{
        Sid       = "ExactProductIdentity"
        Effect    = "Allow"
        Action    = "sts:AssumeRoleWithWebIdentity"
        Principal = { Federated = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com" }
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud"                 = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:repository_id"       = var.github_repository_id
            "token.actions.githubusercontent.com:repository_owner_id" = var.github_repository_owner_id
            "token.actions.githubusercontent.com:sub"                 = subject
          }
        }
      }]
    }
  }
  execution_policies = {
    for purpose, subject in local.subjects : purpose => {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "ExactCatalogEcr"
          Effect   = "Allow"
          Action   = purpose == "plan" ? local.ecr_read_actions : concat(local.ecr_read_actions, local.ecr_apply_actions)
          Resource = local.repository_arns
        },
        {
          Sid    = "EnsureExactBackendBucket"
          Effect = "Allow"
          Action = [
            "s3:ListBucket",
            "s3:GetBucketLocation",
            "s3:GetBucketVersioning",
            "s3:GetEncryptionConfiguration",
            "s3:GetBucketPublicAccessBlock",
            "s3:GetBucketOwnershipControls",
            "s3:CreateBucket",
            "s3:PutBucketPublicAccessBlock",
            "s3:PutBucketOwnershipControls",
            "s3:PutEncryptionConfiguration",
            "s3:PutBucketVersioning",
          ]
          Resource = [local.bucket_arn]
          Condition = {
            StringEquals = { "aws:RequestedRegion" = var.backend_region }
          }
        },
        {
          Sid      = "ExactDefaultWorkspaceState"
          Effect   = "Allow"
          Action   = purpose == "plan" ? ["s3:GetObject"] : ["s3:GetObject", "s3:PutObject"]
          Resource = [local.state_arn]
        },
        {
          Sid      = "ExactDefaultWorkspaceLock"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
          Resource = [local.lock_arn]
        },
        {
          # Required to detect unexpected image-base-* repositories as well as
          # missing members. Inventory cannot be enumerated with an ARN filter.
          Sid      = "ReadOnlyRegionalRepositoryInventory"
          Effect   = "Allow"
          Action   = ["ecr:DescribeRepositories"]
          Resource = ["*"]
          Condition = {
            StringEquals = { "aws:RequestedRegion" = var.aws_region }
          }
        },
        {
          Sid      = "ExactSbomAnalyticsBucket"
          Effect   = "Allow"
          Action   = purpose == "plan" ? local.analytics_read_actions : concat(local.analytics_read_actions, local.analytics_apply_actions)
          Resource = [local.analytics_bucket_arn]
          Condition = {
            StringEquals = { "aws:RequestedRegion" = var.aws_region }
          }
        },
      ]
    }
  }
}

# The pre-existing shared OIDC provider is referenced, never managed here.
# The existing product BUILD role is also deliberately outside this state.
resource "aws_iam_role" "infra" {
  for_each             = local.subjects
  name                 = "${var.role_name_prefix}-${var.github_repository_id}-infra-${each.key}"
  assume_role_policy   = jsonencode(local.trust_policies[each.key])
  max_session_duration = 3600

  lifecycle {
    precondition {
      condition = (
        endswith(var.github_subject_prefix, "@${var.github_repository_id}") &&
        strcontains(var.github_subject_prefix, "@${var.github_repository_owner_id}/")
      )
      error_message = "OIDC subject IDs must match the independently checked repository and owner IDs."
    }
  }

  tags = {
    ManagedBy          = "Terraform-Bootstrap"
    Source             = "alric-corp/alric-containers-image-base"
    GithubRepositoryId = var.github_repository_id
    Responsibility     = "infra-${each.key}"
  }
}

resource "aws_iam_role_policy" "infra" {
  for_each = local.subjects
  name     = "image-base-infra-${each.key}"
  role     = aws_iam_role.infra[each.key].name
  policy   = jsonencode(local.execution_policies[each.key])
}
