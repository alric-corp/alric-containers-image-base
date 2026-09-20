output "role_arns" {
  description = "Separate role ARNs for INFRA_PLAN_ROLE_ARN and INFRA_APPLY_ROLE_ARN."
  value       = { for purpose, role in aws_iam_role.infra : purpose => role.arn }
}

output "role_names" {
  value = { for purpose, role in aws_iam_role.infra : purpose => role.name }
}

output "catalog" {
  value = local.catalog
}

output "trust_policies" {
  description = "Reviewable OIDC boundaries; no credentials."
  value       = local.trust_policies
}

output "execution_policies" {
  description = "Reviewable resource-scoped permissions; no credentials."
  value       = local.execution_policies
}
