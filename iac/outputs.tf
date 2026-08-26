output "function_name" {
  description = "Lambda 函数名。"
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "Lambda 函数 ARN。"
  value       = aws_lambda_function.this.arn
}

output "log_group_name" {
  description = "CloudWatch 日志组名。"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "account_id" {
  description = "本环境业务账号 ID（自 SSM landing-zone 派生）。"
  value       = data.aws_ssm_parameter.account_id.value
  # aws_ssm_parameter.value 被 provider 标记为 sensitive，需显式声明。
  sensitive = true
}
