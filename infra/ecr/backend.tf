# The pipeline bootstraps S3 before this root is initialized. Bucket, key
# and region are supplied by terraform init; this state never owns S3.
terraform {
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}
