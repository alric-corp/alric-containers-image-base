locals {
  # The factory's catalog is the single source of repository names.
  # Provisioning does not enable any framework for image publication.
  repositories = toset([
    for definition in fileset("${path.module}/../../frameworks", "*.yaml") :
    trimsuffix(definition, ".yaml")
  ])

  base_tags = {
    ManagedBy = "Terraform"
    Source    = "alric-corp/alric-containers-image-base"
  }
  tags                   = merge(var.additional_tags, local.base_tags)
  lifecycle_policy_json  = file("${path.module}/policies/ecr-lifecycle-7-days.json")
  repository_policy_json = file("${path.module}/policies/ecr-repository-org-pull.json")
}
