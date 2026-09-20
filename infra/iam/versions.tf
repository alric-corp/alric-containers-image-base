terraform {
  required_version = ">= 1.10.0"

  # Bootstrap ownership is local and independent of the ECR state/backend.
  backend "local" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.28"
    }
  }
}
