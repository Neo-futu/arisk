output "bucket_name" {
  description = "S3 静态桶名。CI 上传静态文件的目标（aws s3 sync）。"
  value       = aws_s3_bucket.static.bucket
}

output "bucket_arn" {
  description = "S3 静态桶 ARN。"
  value       = aws_s3_bucket.static.arn
}

output "account_id" {
  description = "本环境业务账号 ID（自 SSM landing-zone 派生）。"
  value       = data.aws_ssm_parameter.account_id.value
  sensitive   = true
}
