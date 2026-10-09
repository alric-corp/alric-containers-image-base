mock_provider "aws" {}

variables {
  aws_region                 = "us-east-1"
  aws_account_id             = "712107929769"
  github_repository_id       = "1360616627"
  github_repository_owner_id = "178685987"
  github_subject_prefix      = "repo:alric-corp@178685987/alric-containers-image-base@1360616627"
  github_apply_environment   = "lab-image-base-infra"
  backend_bucket             = "712107929769-alric-containers-image-base-tfstate"
  backend_region             = "us-east-2"
}

run "central_role_identity_and_trust" {
  command = plan

  assert {
    condition = (
      aws_iam_role.factory_distroless_v1.name == "itau-github-repo-factory-distroless-v1" &&
      aws_iam_role.factory_distroless_v1.max_session_duration == 10800 &&
      aws_iam_role.infra["plan"].name == "alric-github-repo-1360616627-infra-plan" &&
      aws_iam_role.infra["apply"].name == "alric-github-repo-1360616627-infra-apply"
    )
    error_message = "The central role is added with its exact name and 3h sessions; Infra roles keep their names."
  }

  assert {
    condition = (
      length(jsondecode(aws_iam_role.factory_distroless_v1.assume_role_policy).Statement) == 1 &&
      jsondecode(aws_iam_role.factory_distroless_v1.assume_role_policy).Statement[0].Action == "sts:AssumeRoleWithWebIdentity" &&
      jsondecode(aws_iam_role.factory_distroless_v1.assume_role_policy).Statement[0].Principal.Federated == "arn:aws:iam::712107929769:oidc-provider/token.actions.githubusercontent.com" &&
      toset(keys(jsondecode(aws_iam_role.factory_distroless_v1.assume_role_policy).Statement[0].Condition)) == toset(["StringEquals"]) &&
      jsonencode(jsondecode(aws_iam_role.factory_distroless_v1.assume_role_policy).Statement[0].Condition.StringEquals) == jsonencode({
        "token.actions.githubusercontent.com:aud"                 = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:repository_id"       = "1360616627"
        "token.actions.githubusercontent.com:repository_owner_id" = "178685987"
        "token.actions.githubusercontent.com:sub" = [
          "repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:lab-image-base-infra",
          "repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:DEV",
        ]
      })
    )
    error_message = "Trust must accept only the two exact protected Environment subjects of this repository and owner."
  }
}

run "central_role_domain_policies" {
  command = plan

  assert {
    condition = (
      toset(keys(aws_iam_policy.factory_distroless_v1)) == toset(["infra", "ecr", "releases", "sbom"]) &&
      length(aws_iam_role_policy_attachment.factory_distroless_v1) == 4 &&
      alltrue([for key, policy in aws_iam_policy.factory_distroless_v1 :
        policy.name == "itau-github-repo-factory-distroless-v1-${key}" &&
        length(policy.policy) <= 6144 &&
        aws_iam_role_policy_attachment.factory_distroless_v1[key].role == "itau-github-repo-factory-distroless-v1"
      ])
    )
    error_message = "Four exact customer-managed domain policies, within the managed-policy size limit, attached to the central role."
  }

  assert {
    condition     = aws_iam_policy.factory_distroless_v1["infra"].policy == aws_iam_role_policy.infra["apply"].policy
    error_message = "Domain A must be exactly the reviewed Infra apply permissions (backend, state, lock, ECR configuration, analytics bucket)."
  }

  assert {
    condition = (
      jsonencode(jsondecode(aws_iam_policy.factory_distroless_v1["ecr"].policy).Statement[0]) == jsonencode({
        Sid       = "RegistryAuthentication", Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = ["*"],
        Condition = { StringEquals = { "aws:RequestedRegion" = "us-east-1" } }
      }) &&
      toset(jsondecode(aws_iam_policy.factory_distroless_v1["ecr"].policy).Statement[1].Resource) == toset([
        for definition in fileset("${path.module}/../../frameworks", "*.yaml") :
        "arn:aws:ecr:us-east-1:712107929769:repository/image-base-${trimsuffix(definition, ".yaml")}"
      ]) &&
      toset(jsondecode(aws_iam_policy.factory_distroless_v1["ecr"].policy).Statement[1].Action) == toset([
        "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability", "ecr:DescribeImages",
        "ecr:DescribeRepositories", "ecr:ListImages", "ecr:ListImageReferrers", "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"
      ]) &&
      length(jsondecode(aws_iam_policy.factory_distroless_v1["ecr"].policy).Statement) == 2
    )
    error_message = "Domain B: regional registry login plus read/publication on the exact catalog only."
  }

  assert {
    condition = jsonencode(jsondecode(aws_iam_policy.factory_distroless_v1["releases"].policy).Statement) == jsonencode([
      { Sid = "DevReleaseInventory", Effect = "Allow", Action = ["s3:ListBucket"], Resource = ["arn:aws:s3:::712107929769-image-base-releases-dev"] },
      { Sid = "DevReleaseRecords", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = ["arn:aws:s3:::712107929769-image-base-releases-dev/*"] },
    ])
    error_message = "Domain C: the proven DEV release store scope, without deletion."
  }

  assert {
    condition = jsonencode(jsondecode(aws_iam_policy.factory_distroless_v1["sbom"].policy).Statement) == jsonencode([
      { Sid      = "SbomSnapshotObjects", Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"],
        Resource = ["arn:aws:s3:::alric-distroless-sbom-712107929769-us-east-1/sbom-analytics/poc-v1/snapshots/*"],
      Condition = { StringEquals = { "aws:RequestedRegion" = "us-east-1" } } },
      { Sid      = "SbomSnapshotListing", Effect = "Allow", Action = ["s3:ListBucket"],
        Resource = ["arn:aws:s3:::alric-distroless-sbom-712107929769-us-east-1"],
        Condition = { StringEquals = { "aws:RequestedRegion" = "us-east-1" },
      StringLike = { "s3:prefix" = ["sbom-analytics/poc-v1/snapshots/*"] } } },
    ])
    error_message = "Domain D: snapshot objects and prefix listing only; no deletion."
  }
}

run "reject_mismatched_pipeline_account" {
  command = plan
  variables {
    aws_account_id = "123456789012"
  }
  expect_failures = [aws_iam_role.factory_distroless_v1]
}
