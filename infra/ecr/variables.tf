variable "aws_region" {
  description = "AWS region explicitly selected for the personal deployment."
  type        = string
}

variable "additional_tags" {
  description = "Optional tags; the ManagedBy and Source provenance tags cannot be overridden."
  type        = map(string)
  default     = {}
}

variable "expected_bucket_owner" {
  description = "Expected account supplied by the authorized Infra configuration."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_bucket_owner))
    error_message = "Expected bucket owner must contain 12 digits."
  }
}

variable "sbom_bucket_name" {
  description = "Exact Distroless SBOM Analytics bucket name, supplied by the deployment configuration; never derived."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.sbom_bucket_name)) && !strcontains(var.sbom_bucket_name, "--")
    error_message = "The analytics bucket name must be an exact lowercase S3 bucket name."
  }
}
