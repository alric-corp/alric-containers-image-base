output "repositories" {
  description = "Provisioned destinations keyed by the factory framework name."
  value = {
    for framework, ecr in module.ecr : framework => {
      name = ecr.repository_name
      arn  = ecr.repository_arn
      url  = ecr.repository_url
    }
  }
}

output "go1_26_repository_name" {
  value = module.ecr["go1-26"].repository_name
}

output "go1_26_repository_arn" {
  value = module.ecr["go1-26"].repository_arn
}

output "go1_26_repository_url" {
  value = module.ecr["go1-26"].repository_url
}

output "go1_26_dev_repository_name" {
  value = module.ecr["go1-26-dev"].repository_name
}

output "go1_26_dev_repository_arn" {
  value = module.ecr["go1-26-dev"].repository_arn
}

output "go1_26_dev_repository_url" {
  value = module.ecr["go1-26-dev"].repository_url
}
