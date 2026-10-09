output "bucket_name" {
  value = aws_s3_bucket.sbom.bucket
}
output "bucket_arn" {
  value = aws_s3_bucket.sbom.arn
}
output "bucket_tags" {
  value = aws_s3_bucket.sbom.tags
}
output "bucket_region" {
  value = aws_s3_bucket.sbom.region
}
output "expected_bucket_owner" {
  value = var.expected_bucket_owner
}
output "snapshots_prefix" {
  value = local.snapshots_prefix
}
output "query_results_prefix" {
  value = local.results_prefix
}
output "ingestion_config" {
  value = {
    protocol_version = 1
    destination = {
      bucket                = aws_s3_bucket.sbom.bucket
      prefix                = local.ingestion_prefix
      region                = aws_s3_bucket.sbom.region
      expected_bucket_owner = var.expected_bucket_owner
    }
  }
}
