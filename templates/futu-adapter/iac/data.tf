locals {
  name = "${var.app_name}-futu-adapter-${var.env}"

  # gateway base URL：消费方 ECS 服务通过此 URL 访问 gateway
  gateway_base_url = "http://${var.gateway_private_ip}:${var.listen_port}"

  # gateway URL SSM 路径：默认路径可在 variables.tf 覆盖
  gateway_url_ssm_path = var.gateway_url_ssm_path != "" ? var.gateway_url_ssm_path : "/app/${var.app_name}/${var.env}/futu-adapter/gateway-base-url"

  # FUTU upstream URL 列表拼成逗号分隔字符串（gateway.py 的 UPSTREAM_URL env var 格式）
  upstream_url_csv = join(",", var.futu_upstream_urls)

  vpc_id = nonsensitive(data.aws_ssm_parameter.vpc_id.value)
}

data "aws_ssm_parameter" "vpc_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/vpc-id"
}

# partner 子网：有 TGW 路由到 FUTU ECN，priv/pub 子网没有此路由
# 从逗号分隔列表中选取与 gateway_private_ip 同 /24 的子网（多 AZ 时自动匹配）
data "aws_ssm_parameter" "partner_subnet_ids_raw" {
  name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/partner"
}

data "aws_subnet" "partner" {
  for_each = toset(split(",", nonsensitive(data.aws_ssm_parameter.partner_subnet_ids_raw.value)))
  id       = each.value
}

locals {
  # 找到与 gateway_private_ip 同 /24 的 partner subnet
  partner_subnet_id = [
    for id, s in data.aws_subnet.partner :
    id if cidrcontains(s.cidr_block, var.gateway_private_ip)
  ][0]
}

data "aws_ssm_parameter" "permission_boundary_arn" {
  name = "/infra/bl/${var.env}/ap-east-1/platform/permission-boundary-arn"
}

# AL2023 最新 AMI（通过 SSM 动态获取，不硬编码 AMI ID）
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
