output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "alb_dns_name" {
  value = module.alb.dns_name
}

output "frontend_bucket" {
  value = module.frontend.bucket_name
}

output "cloudfront_distribution_id" {
  value = module.frontend.distribution_id
}

output "cloudfront_domain_name" {
  value = module.frontend.distribution_domain_name
}

output "rds_endpoint" {
  value = module.rds.address
}

output "redis_endpoint" {
  value = module.redis.primary_endpoint
}
