output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.app.name
}

output "app_url" {
  description = "应用访问地址（DNS 配好后生效）"
  value       = "https://${local.app_fqdn}"
}
