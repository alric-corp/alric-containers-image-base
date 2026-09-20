# Fresh ECR state for the corporate topology rehearsal. The factory stays
# at the repository root; infra owns destinations and their policies.
module "ecr" {
  for_each = local.repositories
  source   = "terraform-aws-modules/ecr/aws"
  version  = "3.2.0"

  repository_name = "image-base-${each.value}"

  repository_image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"
  repository_image_tag_mutability_exclusion_filter = [
    { filter = "stable", filter_type = "WILDCARD" }
  ]
  repository_image_scan_on_push = true
  repository_encryption_type    = "AES256"
  repository_force_delete       = false

  create_lifecycle_policy     = true
  repository_lifecycle_policy = local.lifecycle_policy_json
  attach_repository_policy    = true
  create_repository_policy    = false
  repository_policy           = local.repository_policy_json

  tags = local.tags
}
