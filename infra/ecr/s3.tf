# Children of the existing root: the same provider, backend, key and workspace.
module "sbom_analytics" {
  source                = "../s3"
  bucket_name           = var.sbom_bucket_name
  bucket_region         = var.aws_region
  expected_bucket_owner = var.expected_bucket_owner
  tags                  = local.tags
}

# LEGACY (historical bucket replaced by Distroless SBOM Analytics, authorized
# 2026-10-11): it keeps its real state address only until the new analytics
# proof. The next revision deletes this block and Terraform destroys exactly
# this bucket, versions included.
module "sbom" {
  source                = "../s3-legacy"
  bucket_name           = "alric-distroless-sbom-${var.expected_bucket_owner}-${var.aws_region}"
  bucket_region         = var.aws_region
  expected_bucket_owner = var.expected_bucket_owner
  tags                  = local.tags
}
