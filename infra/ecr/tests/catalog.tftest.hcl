# Exercise the real module graph with a mocked AWS provider; no deployment state,
# credentials or backend are used by terraform test.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
}

run "catalog_greenfield" {
  command = plan

  variables {
    aws_region            = "sa-east-1"
    expected_bucket_owner = "123456789012"
    sbom_bucket_name      = "example-distroless-sbom-test"
    additional_tags = {
      ManagedBy = "override-must-not-win"
      Source    = "override-must-not-win"
    }
  }

  assert {
    condition     = toset(keys(module.ecr)) == local.repositories
    error_message = "The ECR modules must exactly match the factory catalog."
  }

  assert {
    condition     = length(module.ecr) == length(fileset("${path.module}/../../frameworks", "*.yaml"))
    error_message = "The number of ECR destinations must come from frameworks/*.yaml."
  }

  assert {
    condition     = alltrue([for framework, repository in module.ecr : repository.repository_name == "image-base-${framework}"])
    error_message = "Every ECR repository must use its matching catalog name."
  }

  assert {
    condition     = local.tags.ManagedBy == "Terraform" && local.tags.Source == "alric-corp/alric-containers-image-base"
    error_message = "Additional tags must not override resource provenance."
  }

  assert {
    condition     = module.sbom_analytics.bucket_name == "example-distroless-sbom-test"
    error_message = "The analytics bucket must be exactly the configured name, never derived."
  }
}

run "reject_derived_or_invalid_analytics_bucket" {
  command = plan

  variables {
    aws_region            = "sa-east-1"
    expected_bucket_owner = "123456789012"
    sbom_bucket_name      = "Distroless_SBOM"
  }

  expect_failures = [var.sbom_bucket_name]
}
