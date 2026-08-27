# 只读 SSM 派生：对接现有基础设施暴露的参数。禁止硬编码账号 ID / VPC ID / 子网 ID / 角色 ARN。

locals {
  name       = "${var.app_name}-${var.env}"
  env_pascal = lookup({ dev = "Development", staging = "Staging", prod = "Production" }, var.env, title(var.env))
  env_suffix = var.env == "prod" ? "" : ".${var.env}"
  app_fqdn   = "${var.app_name}${local.env_suffix}.balancehk.com"

  vpc_id          = nonsensitive(data.aws_ssm_parameter.vpc_id.value)
  priv_subnet_ids = split(",", nonsensitive(data.aws_ssm_parameter.priv_subnet_ids.value))
  ecr_registry    = nonsensitive(data.aws_ssm_parameter.ecr_registry_url.value)
}

data "aws_ssm_parameter" "vpc_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/vpc-id"
}

data "aws_ssm_parameter" "priv_subnet_ids" {
  name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/priv"
}

data "aws_ssm_parameter" "permission_boundary_arn" {
  name = "/infra/bl/${var.env}/ap-east-1/platform/permission-boundary-arn"
}

# 集中 ECR registry（ADR-0017：镜像推 shared-services 账号，应用不自建仓库）
data "aws_ssm_parameter" "ecr_registry_url" {
  name = "/infra/bl/${var.env}/ap-east-1/ecr/registry-url"
}

# Ingress R-06：外部公网共享 ALB（443 listener + SG），由 infra ingress 域发布
data "aws_ssm_parameter" "external_listener_443_arn" {
  name = "/balance/ingress/external/${var.env}/alb/listener_443_arn"
}

data "aws_ssm_parameter" "external_alb_sg_id" {
  name = "/balance/ingress/external/${var.env}/alb/sg_id"
}
