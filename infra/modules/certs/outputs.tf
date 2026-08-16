output "api_certificate_arn" {
  value = aws_acm_certificate_validation.api.certificate_arn
}

output "app_certificate_arn" {
  value = aws_acm_certificate_validation.app.certificate_arn
}
