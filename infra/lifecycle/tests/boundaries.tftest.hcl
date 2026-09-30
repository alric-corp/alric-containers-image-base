mock_provider "aws" { alias = "dev" }
mock_provider "aws" { alias = "hom" }

run "environment_bound_roles_and_exact_catalog" {
  command = plan
  assert {
    condition     = local.trust.DEV.Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:DEV" && local.trust.HOM.Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:HOM"
    error_message = "Only exact immutable repository subjects in DEV/HOM may assume the roles."
  }
  assert {
    condition = toset(keys(aws_ecr_repository.hom)) == local.catalog && alltrue([
      for repo in aws_ecr_repository.hom : repo.image_tag_mutability == "IMMUTABLE_WITH_EXCLUSION" && length(repo.image_tag_mutability_exclusion_filter) == 1 && alltrue([for rule in repo.image_tag_mutability_exclusion_filter : rule.filter == "stable" && rule.filter_type == "WILDCARD"]) && repo.force_delete == false
    ])
    error_message = "HOM must preserve the entire catalog and stable-only mutation."
  }
  assert {
    condition = alltrue([for statement in local.permissions.DEV.Statement : alltrue([
      for arn in statement.Resource : !strcontains(arn, local.hom.account_id)
    ])])
    error_message = "DEV must not receive access to the HOM account."
  }
  assert {
    condition = alltrue([for statement in local.permissions.HOM.Statement : alltrue([
      for action in statement.Action : !strcontains(action, "Delete") && !strcontains(action, "CreateRepository") && action != "sts:AssumeRole"
      ])]) && toset(local.permissions.HOM.Statement[4].Resource) == toset(local.repos.DEV) && alltrue([
      for action in local.permissions.HOM.Statement[4].Action : !strcontains(action, "Put") && !strcontains(action, "Upload")
    ])
    error_message = "HOM can read the exact DEV catalog, but cannot write it or administer infrastructure."
  }
  assert {
    condition     = alltrue([for env, policy in local.bucket_policies : policy.Statement[1].Effect == "Deny" && policy.Statement[1].Condition.Null["s3:if-none-match"] == "true"])
    error_message = "Manifest/event creation must reject unconditional overwrites."
  }
}
