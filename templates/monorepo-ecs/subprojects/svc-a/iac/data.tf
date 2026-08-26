# 从平台 SSM 读取网络/部署资源，从 shared/iac 读取共享 DB 连接信息，
# 从 dns/app-iac 读取公网入口（cert/tg/sg）。禁止硬编码任何 ID / ARN / endpoint。

locals {
  name = "${var.app_name}-svc-a-${var.env}"
  # 公网域名（与 dns/app-iac/services.tf 的 cert_domain 保持一致）：
  # prod 用裸子域 <svc>.<domain>，其他环境多一层 <env>
  app_fqdn = var.env == "prod" ? "${var.service_name}.${var.domain}" : "${var.service_name}.${var.env}.${var.domain}"
  # 内网域名：{service_name}.{phz_zone_name}（如 svc-a.dev.bl.internal）
  internal_fqdn = "${var.service_name}.${data.aws_route53_zone.phz.name}"
  ssm_shared    = "/app/${var.app_name}/${var.env}/shared"
  ssm_public    = "/app/${var.app_name}/${var.service_name}/${var.env}"

  vpc_id          = nonsensitive(data.aws_ssm_parameter.vpc_id.value)
  priv_subnet_ids = split(",", nonsensitive(data.aws_ssm_parameter.priv_subnet_ids.value))
  ecr_registry    = nonsensitive(data.aws_ssm_parameter.ecr_registry_url.value)

  rds_endpoint    = nonsensitive(data.aws_ssm_parameter.rds_endpoint.value)
  rds_port        = nonsensitive(data.aws_ssm_parameter.rds_port.value)
  rds_resource_id = nonsensitive(data.aws_ssm_parameter.rds_resource_id.value)
  rds_sg_id       = nonsensitive(data.aws_ssm_parameter.rds_sg_id.value)

  public_tg_arn    = nonsensitive(data.aws_ssm_parameter.public_tg_arn.value)
  public_alb_sg_id = nonsensitive(data.aws_ssm_parameter.public_alb_sg_id.value)
}

data "aws_caller_identity" "current" {}

# 平台网络
data "aws_ssm_parameter" "vpc_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/vpc-id"
}
data "aws_ssm_parameter" "priv_subnet_ids" {
  name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/priv"
}
data "aws_ssm_parameter" "permission_boundary_arn" {
  name = "/infra/bl/${var.env}/ap-east-1/platform/permission-boundary-arn"
}
data "aws_ssm_parameter" "ecr_registry_url" {
  name = "/infra/bl/${var.env}/ap-east-1/ecr/registry-url"
}

# 公网入口（由 dns/app-iac 写出）：ECS service 注册 public-tg-arn，
# service SG 入站放行 public-alb-sg-id。证书/listener 全在 dns/app-iac，子项目不碰。
data "aws_ssm_parameter" "public_tg_arn" {
  name = "${local.ssm_public}/public-tg-arn"
}
data "aws_ssm_parameter" "public_alb_sg_id" {
  name = "${local.ssm_public}/public-alb-sg-id"
}

# VPC 私有 Hosted Zone（内网 DNS 用）
data "aws_ssm_parameter" "phz_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/phz-id"
}
data "aws_route53_zone" "phz" {
  zone_id      = nonsensitive(data.aws_ssm_parameter.phz_id.value)
  private_zone = true
}

# 共享 RDS（由 shared/iac 发布）
data "aws_ssm_parameter" "rds_endpoint" {
  name = "${local.ssm_shared}/rds/endpoint"
}
data "aws_ssm_parameter" "rds_port" {
  name = "${local.ssm_shared}/rds/port"
}
data "aws_ssm_parameter" "rds_resource_id" {
  name = "${local.ssm_shared}/rds/resource-id"
}
data "aws_ssm_parameter" "rds_sg_id" {
  name = "${local.ssm_shared}/rds/sg-id"
}
