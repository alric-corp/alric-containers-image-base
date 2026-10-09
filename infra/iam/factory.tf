# Central Factory role (additive). The legacy Infra roles above, the lifecycle
# DEV role and every existing policy stay managed and unchanged; workflows keep
# their current role ARNs until a separate configuration cutover.
locals {
  pipeline = jsondecode(file("${path.module}/../../policies/pipeline/config.json"))
  factory_subjects = [
    "${var.github_subject_prefix}:environment:${var.github_apply_environment}",
    "${var.github_subject_prefix}:environment:${var.factory_dev_environment}",
  ]
  release_bucket_arn = "arn:aws:s3:::${local.pipeline.DEV.release_bucket}"
  sbom_snapshots_arn = "${local.analytics_bucket_arn}/sbom-analytics/poc-v1/snapshots/*"

  # Same proven actions as the lifecycle DEV role (infra/lifecycle/main.tf).
  publication_read_actions = [
    "ecr:BatchGetImage",
    "ecr:GetDownloadUrlForLayer",
    "ecr:BatchCheckLayerAvailability",
    "ecr:DescribeImages",
    "ecr:DescribeRepositories",
    "ecr:ListImages",
    "ecr:ListImageReferrers",
  ]
  publication_push_actions = [
    "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart",
    "ecr:CompleteLayerUpload",
    "ecr:PutImage",
  ]

  factory_trust = {
    Version = "2012-10-17"
    Statement = [{
      Sid       = "FactoryProtectedEnvironments"
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com" }
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud"                 = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:repository_id"       = var.github_repository_id
          "token.actions.githubusercontent.com:repository_owner_id" = var.github_repository_owner_id
          "token.actions.githubusercontent.com:sub"                 = local.factory_subjects
        }
      }
    }]
  }

  factory_policies = {
    # Domain A: Terraform backend/state/lock, ECR configuration and analytics
    # bucket configuration; exactly the applied Infra apply permissions.
    infra = local.execution_policies["apply"]
    # Domain B: registry login and catalog read/publication.
    ecr = {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "RegistryAuthentication"
          Effect   = "Allow"
          Action   = ["ecr:GetAuthorizationToken"]
          Resource = ["*"]
          Condition = {
            StringEquals = { "aws:RequestedRegion" = var.aws_region }
          }
        },
        {
          Sid      = "ExactCatalogPublication"
          Effect   = "Allow"
          Action   = concat(local.publication_read_actions, local.publication_push_actions)
          Resource = local.repository_arns
        },
      ]
    }
    # Domain C: DEV release store, same proven scope as the lifecycle DEV role.
    releases = {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "DevReleaseInventory"
          Effect   = "Allow"
          Action   = ["s3:ListBucket"]
          Resource = [local.release_bucket_arn]
        },
        {
          Sid      = "DevReleaseRecords"
          Effect   = "Allow"
          Action   = ["s3:GetObject", "s3:PutObject"]
          Resource = ["${local.release_bucket_arn}/*"]
        },
      ]
    }
    # Domain D: SBOM snapshot objects; the bucket policy still requires
    # If-None-Match on creation. No deletion.
    sbom = {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "SbomSnapshotObjects"
          Effect   = "Allow"
          Action   = ["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"]
          Resource = [local.sbom_snapshots_arn]
          Condition = {
            StringEquals = { "aws:RequestedRegion" = var.aws_region }
          }
        },
        {
          Sid      = "SbomSnapshotListing"
          Effect   = "Allow"
          Action   = ["s3:ListBucket"]
          Resource = [local.analytics_bucket_arn]
          Condition = {
            StringEquals = { "aws:RequestedRegion" = var.aws_region }
            StringLike   = { "s3:prefix" = ["sbom-analytics/poc-v1/snapshots/*"] }
          }
        },
      ]
    }
  }
}

resource "aws_iam_role" "factory_distroless_v1" {
  name                 = var.factory_role_name
  assume_role_policy   = jsonencode(local.factory_trust)
  max_session_duration = 10800

  lifecycle {
    precondition {
      condition = (
        local.pipeline.DEV.account_id == var.aws_account_id &&
        local.pipeline.DEV.region == var.aws_region &&
        local.pipeline.subject_prefix == var.github_subject_prefix
      )
      error_message = "The pipeline DEV account, region and subject prefix must match the bootstrap variables."
    }
  }

  tags = {
    ManagedBy          = "Terraform-Bootstrap"
    Source             = "alric-corp/alric-containers-image-base"
    GithubRepositoryId = var.github_repository_id
    Responsibility     = "factory-distroless-v1"
  }
}

resource "aws_iam_policy" "factory_distroless_v1" {
  for_each    = local.factory_policies
  name        = "${var.factory_role_name}-${each.key}"
  description = "Factory Distroless v1 ${each.key} permissions for the central role."
  policy      = jsonencode(each.value)

  tags = {
    ManagedBy          = "Terraform-Bootstrap"
    Source             = "alric-corp/alric-containers-image-base"
    GithubRepositoryId = var.github_repository_id
    Responsibility     = "factory-distroless-v1-${each.key}"
  }
}

resource "aws_iam_role_policy_attachment" "factory_distroless_v1" {
  for_each   = aws_iam_policy.factory_distroless_v1
  role       = aws_iam_role.factory_distroless_v1.name
  policy_arn = each.value.arn
}
