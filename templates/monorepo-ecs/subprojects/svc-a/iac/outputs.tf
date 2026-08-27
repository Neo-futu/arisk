output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "db_owner_task_role_arn" {
  value = aws_iam_role.db_owner_task.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.app.name
}

output "app_url" {
  value       = "https://${local.app_fqdn}"
  description = "公网访问地址（cert + 公网 ALB + TG 由 dns/app-iac 提供，Route53 记录由 deploy-dns-route53 写入）"
}

output "internal_fqdn" {
  value       = local.internal_fqdn
  description = "VPC 内网域名（{service_name}.{env}.bl.internal），消费方 ECS 服务用此地址访问"
}
