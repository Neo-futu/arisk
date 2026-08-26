# 将 gateway base URL 发布到 SSM，消费方 IaC 通过 data source 读取，
# 注入 ECS task definition 环境变量（deploy 时固化，不在容器内动态读取）。

resource "aws_ssm_parameter" "gateway_base_url" {
  name        = local.gateway_url_ssm_path
  type        = "String"
  value       = local.gateway_base_url
  description = "${var.app_name} futu-adapter gateway URL (${var.env})"
}
