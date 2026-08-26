output "instance_id" {
  value       = aws_instance.dev_server.id
  description = "EC2 实例 ID"
}

output "ssm_connect_command" {
  value       = "aws ssm start-session --target ${aws_instance.dev_server.id} --region ${var.region}"
  description = "SSM Session Manager 连接命令（需持有 DevDataDebugPermissionSet 临时凭证）"
}

output "root_volume_size_gb" {
  value       = local.root_volume_size_gb
  description = "根卷实际大小（GB）"
}
