output "gateway_base_url" {
  value       = local.gateway_base_url
  description = "消费方 ECS 服务访问 gateway 的 base URL，也发布到 SSM"
}

output "gateway_url_ssm_path" {
  value       = local.gateway_url_ssm_path
  description = "gateway base URL 在 SSM 中的路径，消费方 IaC data source 使用"
}

output "gateway_sg_id" {
  value       = aws_security_group.gateway.id
  description = "gateway SG ID，可作为消费方 SG 出站规则的目标引用"
}

output "gateway_private_ip" {
  value       = var.gateway_private_ip
  description = "gateway ENI 固定 IP（ENI 独立，EC2 替换后不变）"
}
