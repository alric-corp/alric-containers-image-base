# Central Factory role (additive). The legacy Infra roles in main.tf, the lifecycle
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

  # Terraform statements reused verbatim, by Sid, from the Infra apply policy in
  # main.tf. A missing or renamed Sid fails the plan instead of silently changing
  # what the central role may do.
  infra_apply_statements = {
    for statement in local.execution_policies["apply"].Statement : statement.Sid => statement
  }

  # The single inline policy, with statements grouped by responsibility. IAM caps
  # all inline policies of one role together at 10,240 characters excluding
  # whitespace; the tests enforce it. If a later addition (Athena/Glue) does not
  # fit, report the blocker: never widen permissions or change the architecture
  # to make it fit.
  factory_statements = [
    # Terraform: backend bucket, state object, lock object (the only deletable
    # object), regional repository inventory (detects unexpected image-base-*
    # repositories) and configuration of the analytics bucket.
    local.infra_apply_statements["EnsureExactBackendBucket"],
    local.infra_apply_statements["ExactDefaultWorkspaceState"],
    local.infra_apply_statements["ExactDefaultWorkspaceLock"],
    local.infra_apply_statements["ReadOnlyRegionalRepositoryInventory"],
    local.infra_apply_statements["ExactSbomAnalyticsBucket"],

    # ECR: one statement on the exact catalog. It is the union, without
    # duplicates, of the Terraform repository configuration and the build, read
    # and publication actions; both used the same 16 repositories.
    {
      Sid      = "ExactCatalogEcr"
      Effect   = "Allow"
      Action   = sort(distinct(concat(local.ecr_read_actions, local.ecr_apply_actions, local.publication_read_actions, local.publication_push_actions)))
      Resource = local.repository_arns
    },
    {
      Sid      = "RegistryAuthentication"
      Effect   = "Allow"
      Action   = ["ecr:GetAuthorizationToken"]
      Resource = ["*"]
      Condition = {
        StringEquals = { "aws:RequestedRegion" = var.aws_region }
      }
    },

    # Release store DEV: same proven scope as the lifecycle DEV role.
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

    # SBOM Analytics snapshots. The bucket policy still requires If-None-Match on
    # creation. No deletion. The listing grant states the data-plane scope; the
    # provider's HeadBucket already needs bucket-level s3:ListBucket in
    # ExactSbomAnalyticsBucket, so it does not narrow the effective listing.
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

  factory_policy = {
    Version   = "2012-10-17"
    Statement = local.factory_statements
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

resource "aws_iam_role_policy" "factory_distroless_v1" {
  name   = "factory-distroless-v1"
  role   = aws_iam_role.factory_distroless_v1.name
  policy = jsonencode(local.factory_policy)

  lifecycle {
    precondition {
      condition     = length(replace(jsonencode(local.factory_policy), "/\\s/", "")) <= var.factory_policy_max_characters
      error_message = "The central inline policy exceeds the IAM limit for all inline policies of a role (10,240 characters excluding whitespace). Report the blocker; do not widen permissions or change the architecture to make it fit."
    }
  }
}
