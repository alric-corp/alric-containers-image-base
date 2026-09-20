variable "aws_region" {
  description = "AWS region explicitly selected for the personal LAB."
  type        = string
}

variable "additional_tags" {
  description = "Optional tags; the ManagedBy and Source provenance tags cannot be overridden."
  type        = map(string)
  default     = {}
}
