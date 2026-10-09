# Child of the existing root: the same provider, backend, key and workspace.
module "sbom" {
  source                = "../s3"
  bucket_name           = coalesce(var.sbom_bucket_name, "alric-distroless-sbom-${var.expected_bucket_owner}-${var.aws_region}")
  bucket_region         = var.aws_region
  expected_bucket_owner = var.expected_bucket_owner
  tags                  = local.tags
}
