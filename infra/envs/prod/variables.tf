variable "project_name" {
  type    = string
  default = "sns-x-prod"
}

variable "aws_region" {
  type    = string
  default = "ap-northeast-1"
}

variable "route53_zone_id" {
  type        = string
  description = "Hosted zone ID for the apex domain"
}

variable "app_hostname" {
  type        = string
  description = "Frontend hostname, e.g. app.example.com"
}

variable "api_hostname" {
  type        = string
  description = "API hostname, e.g. api.example.com"
}

variable "db_username" {
  type    = string
  default = "sns"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "Strong password; also store in SSM as /{project}/POSTGRES_PASSWORD"
}

variable "api_image_tag" {
  type    = string
  default = "latest"
}
