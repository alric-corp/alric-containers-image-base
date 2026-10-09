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

output "factory_role_arn" {
  description = "Central Factory role; workflows adopt it only in the separate cutover."
  value       = aws_iam_role.factory_distroless_v1.arn
}

output "factory_policy" {
  description = "Reviewable inline policy of the central role; no credentials."
  value       = local.factory_policy
}
