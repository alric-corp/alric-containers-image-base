variable "aws_region" {
  description = "Region of the ECR repositories; independent of the state bucket region."
  type        = string
}

variable "aws_account_id" {
  description = "Only this LAB account may receive the IAM bootstrap."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain exactly 12 digits."
  }
}

variable "github_repository_id" {
  description = "Immutable GitHub product repository ID."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must be a numeric string."
  }
}

variable "github_repository_owner_id" {
  description = "Immutable GitHub owner ID, checked independently of the subject."
  type        = string
  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_owner_id))
    error_message = "github_repository_owner_id must be a numeric string."
  }
}

variable "github_subject_prefix" {
  description = "Observed immutable GitHub subject prefix, without event/environment suffix."
  type        = string
  validation {
    condition     = can(regex("^repo:[A-Za-z0-9_.-]+@[0-9]+/[A-Za-z0-9_.-]+@[0-9]+$", var.github_subject_prefix))
    error_message = "github_subject_prefix must be an exact repo:owner@owner_id/repo@repo_id identity, without wildcards."
  }
}

variable "github_apply_environment" {
  description = "Protected GitHub environment authorized to apply product Infra."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+$", var.github_apply_environment))
    error_message = "github_apply_environment must be an exact, nonempty environment name."
  }
}

variable "backend_bucket" {
  description = "One exact S3 bucket bootstrapped by the Infra pipeline."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.backend_bucket))
    error_message = "backend_bucket must be an exact S3 bucket name, without wildcards."
  }
}

variable "backend_region" {
  description = "State bucket region; absent us-east-1 buckets are rejected by backend.py."
  type        = string
  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.backend_region))
    error_message = "backend_region must be an explicit AWS region."
  }
}

variable "role_name_prefix" {
  description = "Repository identity naming convention, configurable for the corporate port."
  type        = string
  default     = "alric-github-repo"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.role_name_prefix))
    error_message = "role_name_prefix must be a literal IAM role-name prefix."
  }
}
