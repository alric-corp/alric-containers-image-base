variable "aws_region" {
  description = "AWS region explicitly selected for the personal LAB."
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
  description = "Optional explicit analytics bucket name; otherwise derive the LAB name from the expected account and region."
  type        = string
  default     = null
}
