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

run "central_role_single_inline_policy" {
  command = plan

  assert {
    condition = (
      aws_iam_role_policy.factory_distroless_v1.name == "factory-distroless-v1" &&
      aws_iam_role_policy.factory_distroless_v1.role == "itau-github-repo-factory-distroless-v1" &&
      jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Version == "2012-10-17" &&
      length(jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Statement) == 11
    )
    error_message = "The central role has one inline policy, factory-distroless-v1, with eleven statements."
  }

  assert {
    condition     = length(replace(aws_iam_role_policy.factory_distroless_v1.policy, "/\\s/", "")) <= 10240
    error_message = "All inline policies of a role together cannot exceed 10,240 characters excluding whitespace; do not widen permissions or change the architecture to make it fit."
  }

  assert {
    condition = (
      jsonencode(jsondecode(aws_iam_role_policy.factory_distroless_v1.policy)) ==
      jsonencode(jsondecode(file("${path.module}/tests/fixtures/factory-distroless-v1.policy.json")))
    )
    error_message = "The evaluated policy must equal the reviewed document tests/fixtures/factory-distroless-v1.policy.json."
  }

  assert {
    condition = (
      jsonencode(slice(jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Statement, 0, 5)) ==
      jsonencode(slice(jsondecode(aws_iam_role_policy.infra["apply"].policy).Statement, 1, 6))
    )
    error_message = "The Terraform statements must be the Infra apply statements, verbatim."
  }

  assert {
    condition = (
      toset(jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Statement[5].Action) == toset(concat(
        jsondecode(aws_iam_role_policy.infra["apply"].policy).Statement[0].Action,
        [
          "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability", "ecr:DescribeImages",
          "ecr:DescribeRepositories", "ecr:ListImages", "ecr:ListImageReferrers", "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"
        ]
      )) &&
      length(jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Statement[5].Action) == length(toset(jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Statement[5].Action)) &&
      jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Statement[5].Resource == jsondecode(aws_iam_role_policy.infra["apply"].policy).Statement[0].Resource &&
      !contains(keys(jsondecode(aws_iam_role_policy.factory_distroless_v1.policy).Statement[5]), "Condition")
    )
    error_message = "The single ECR statement is the duplicate-free union of the Terraform and publication actions on the same 16 repositories."
  }
}

run "reject_policy_over_the_budget" {
  command = plan
  variables {
    factory_policy_max_characters = 4000
  }
  expect_failures = [aws_iam_role_policy.factory_distroless_v1]
}

run "reject_budget_above_the_iam_quota" {
  command = plan
  variables {
    factory_policy_max_characters = 10241
  }
  expect_failures = [var.factory_policy_max_characters]
}

run "reject_mismatched_pipeline_account" {
  command = plan
  variables {
    aws_account_id = "123456789012"
  }
  expect_failures = [aws_iam_role.factory_distroless_v1]
}
