# Children of the existing root: the same provider, backend, key and workspace.
module "sbom_analytics" {
  source                = "../s3"
  bucket_name           = var.sbom_bucket_name
  bucket_region         = var.aws_region
  expected_bucket_owner = var.expected_bucket_owner
  tags                  = local.tags
}
