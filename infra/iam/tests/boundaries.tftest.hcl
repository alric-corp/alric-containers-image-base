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

run "separate_roles_exact_trust_and_permissions" {
  command = plan

  assert {
    condition = (
      length(aws_iam_role.infra) == 2 && length(aws_iam_role_policy.infra) == 2 &&
      aws_iam_role.infra["plan"].name == "alric-github-repo-1360616627-infra-plan" &&
      aws_iam_role.infra["apply"].name == "alric-github-repo-1360616627-infra-apply"
    )
    error_message = "Bootstrap must own exactly two distinct Infra roles and two inline policies."
  }

  assert {
    condition = alltrue([
      for purpose, role in aws_iam_role.infra : (
        length(jsondecode(role.assume_role_policy).Statement) == 1 &&
        jsondecode(role.assume_role_policy).Statement[0].Action == "sts:AssumeRoleWithWebIdentity" &&
        jsondecode(role.assume_role_policy).Statement[0].Principal.Federated == "arn:aws:iam::712107929769:oidc-provider/token.actions.githubusercontent.com" &&
        toset(keys(jsondecode(role.assume_role_policy).Statement[0].Condition)) == toset(["StringEquals"]) &&
        jsonencode(jsondecode(role.assume_role_policy).Statement[0].Condition.StringEquals) == jsonencode({
          "token.actions.githubusercontent.com:aud"                 = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:repository_id"       = "1360616627"
          "token.actions.githubusercontent.com:repository_owner_id" = "178685987"
          "token.actions.githubusercontent.com:sub"                 = purpose == "plan" ? "repo:alric-corp@178685987/alric-containers-image-base@1360616627:pull_request" : "repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:lab-image-base-infra"
        })
      )
    ])
    error_message = "Trust must require the exact event/environment subject, audience and immutable IDs."
  }

  assert {
    condition = alltrue([
      for purpose, policy in aws_iam_role_policy.infra :
      toset(jsondecode(policy.policy).Statement[0].Resource) == toset([
        for definition in fileset("${path.module}/../../frameworks", "*.yaml") :
        "arn:aws:ecr:us-east-1:712107929769:repository/image-base-${trimsuffix(definition, ".yaml")}"
      ])
    ])
    error_message = "ECR permissions must exactly match the product catalog without repository wildcards."
  }

  assert {
    condition = (
      toset(jsondecode(aws_iam_role_policy.infra["plan"].policy).Statement[0].Action) == toset([
        "ecr:DescribeRepositories", "ecr:GetRepositoryPolicy", "ecr:GetLifecyclePolicy", "ecr:ListTagsForResource"
      ]) &&
      toset(jsondecode(aws_iam_role_policy.infra["apply"].policy).Statement[0].Action) == toset([
        "ecr:DescribeRepositories", "ecr:GetRepositoryPolicy", "ecr:GetLifecyclePolicy", "ecr:ListTagsForResource",
        "ecr:DescribeImages", "ecr:CreateRepository", "ecr:PutLifecyclePolicy", "ecr:SetRepositoryPolicy", "ecr:TagResource",
        "ecr:UntagResource", "ecr:PutImageScanningConfiguration", "ecr:PutImageTagMutability"
      ])
    )
    error_message = "Plan must be ECR read-only; apply must configure ECR without publication or deletion."
  }

  assert {
    condition = alltrue([
      for purpose, policy in aws_iam_role_policy.infra : (
        jsondecode(policy.policy).Statement[1].Resource == ["arn:aws:s3:::712107929769-alric-containers-image-base-tfstate"] &&
        jsondecode(policy.policy).Statement[1].Condition.StringEquals["aws:RequestedRegion"] == "us-east-2" &&
        jsondecode(policy.policy).Statement[2].Resource == ["arn:aws:s3:::712107929769-alric-containers-image-base-tfstate/alric-containers-image-base/terraform.tfstate"] &&
        toset(jsondecode(policy.policy).Statement[2].Action) == toset(purpose == "plan" ? ["s3:GetObject"] : ["s3:GetObject", "s3:PutObject"]) &&
        jsondecode(policy.policy).Statement[3].Resource == ["arn:aws:s3:::712107929769-alric-containers-image-base-tfstate/alric-containers-image-base/terraform.tfstate.tflock"] &&
        toset(jsondecode(policy.policy).Statement[3].Action) == toset(["s3:GetObject", "s3:PutObject", "s3:DeleteObject"])
      )
    ])
    error_message = "Backend must target the one bucket/state/lock; only apply may write state; only lock is deletable."
  }

  assert {
    condition = alltrue([
      for purpose, policy in aws_iam_role_policy.infra : (
        length(jsondecode(policy.policy).Statement) == 5 &&
        toset(jsondecode(policy.policy).Statement[4].Action) == toset(["ecr:DescribeRepositories"]) &&
        jsondecode(policy.policy).Statement[4].Resource == ["*"] &&
        jsondecode(policy.policy).Statement[4].Condition.StringEquals["aws:RequestedRegion"] == "us-east-1"
      )
    ])
    error_message = "The only global-resource Infra grant must be regional read-only repository inventory."
  }
}

run "reject_mismatched_subject_owner" {
  command = plan
  variables {
    github_repository_owner_id = "999999999"
  }
  expect_failures = [aws_iam_role.infra]
}

run "reject_wildcard_subject" {
  command = plan
  variables {
    github_subject_prefix = "repo:alric-corp@178685987/*@1360616627"
  }
  expect_failures = [var.github_subject_prefix]
}
