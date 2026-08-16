variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "assign_public_ip" {
  type    = bool
  default = true
}
variable "ecr_repository_url" { type = string }
variable "alb_target_group_arn" { type = string }
variable "alb_security_group_id" { type = string }
variable "container_image_tag" {
  type    = string
  default = "latest"
}
variable "ssm_prefix" { type = string }
variable "postgres_host" { type = string }
variable "redis_host" { type = string }
variable "cors_origins" { type = string }
variable "allowed_hosts" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}
