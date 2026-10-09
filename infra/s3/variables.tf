variable "bucket_name" {
  description = "Externally selected general-purpose SBOM analytics bucket name."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name)) && !startswith(var.bucket_name, "xn--") && !startswith(var.bucket_name, "sthree-") && !startswith(var.bucket_name, "amzn-s3-demo-") && !endswith(var.bucket_name, "--x-s3") && !endswith(var.bucket_name, "--table-s3") && !endswith(var.bucket_name, "-s3alias") && !endswith(var.bucket_name, "--ol-s3")
    error_message = "Use a 3-63 character general-purpose bucket name without dots or reserved suffixes."
  }
}

variable "bucket_region" {
  description = "Explicit region supplied by the execution root; no provider is configured here."
  type        = string
}

variable "expected_bucket_owner" {
  description = "Expected account from authorized configuration, not inferred from the session."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_bucket_owner))
    error_message = "Expected bucket owner must be a 12-digit account ID."
  }
}

variable "tags" {
  description = "Ownership and provenance tags supplied by the existing root."
  type        = map(string)
}
