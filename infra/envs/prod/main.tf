# Re-wire modules without circular deps:
# 1) dns creates ACM certs (+ validation records)
# 2) alb / frontend / ecs consume cert ARNs
# 3) dns_records attaches app/api aliases

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

locals {
  name = var.project_name
  tags = {
    Project     = var.project_name
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

module "vpc" {
  source     = "../../modules/vpc"
  name       = local.name
  cidr_block = "10.40.0.0/16"
  tags       = local.tags
}

module "ecr" {
  source = "../../modules/ecr"
  name   = local.name
  tags   = local.tags
}

module "certs" {
  source = "../../modules/certs"

  route53_zone_id = var.route53_zone_id
  app_hostname    = var.app_hostname
  api_hostname    = var.api_hostname

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }
}

module "rds" {
  source = "../../modules/rds"

  name                = local.name
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.public_subnet_ids
  allowed_cidr_blocks = [module.vpc.vpc_cidr]
  db_username         = var.db_username
  db_password         = var.db_password
  instance_class      = "db.t4g.micro"
  tags                = local.tags
}

module "redis" {
  source = "../../modules/redis"

  name                = local.name
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.public_subnet_ids
  allowed_cidr_blocks = [module.vpc.vpc_cidr]
  node_type           = "cache.t4g.micro"
  tags                = local.tags
}

module "alb" {
  source = "../../modules/alb"

  name              = local.name
  vpc_id            = module.vpc.vpc_id
  subnet_ids        = module.vpc.public_subnet_ids
  certificate_arn   = module.certs.api_certificate_arn
  health_check_path = "/health"
  tags              = local.tags
}

module "ecs" {
  source = "../../modules/ecs"

  name                  = local.name
  vpc_id                = module.vpc.vpc_id
  subnet_ids            = module.vpc.public_subnet_ids
  assign_public_ip      = true
  ecr_repository_url    = module.ecr.repository_url
  alb_target_group_arn  = module.alb.target_group_arn
  alb_security_group_id = module.alb.security_group_id
  container_image_tag   = var.api_image_tag
  ssm_prefix            = "/${local.name}"
  postgres_host         = module.rds.address
  redis_host            = module.redis.primary_endpoint
  cors_origins          = "https://${var.app_hostname}"
  allowed_hosts         = var.api_hostname
  tags                  = local.tags
}

module "frontend" {
  source = "../../modules/frontend"

  name                = local.name
  domain_name         = var.app_hostname
  acm_certificate_arn = module.certs.app_certificate_arn
  tags                = local.tags
}

module "dns_records" {
  source = "../../modules/dns_records"

  route53_zone_id           = var.route53_zone_id
  app_hostname              = var.app_hostname
  api_hostname              = var.api_hostname
  alb_dns_name              = module.alb.dns_name
  alb_zone_id               = module.alb.zone_id
  cloudfront_domain_name    = module.frontend.distribution_domain_name
  cloudfront_hosted_zone_id = module.frontend.distribution_hosted_zone_id
}
