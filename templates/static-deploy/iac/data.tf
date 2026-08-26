# 只读 SSM 派生：对接现有基础设施暴露的参数。禁止硬编码账号 ID / VPC ID / 角色 ARN。

locals {
  repo_pascal = var.repo_pascal
  env_pascal  = lookup({ dev = "Development", staging = "Staging", prod = "Production" }, var.env, title(var.env))

  # prod 才有 CloudFront（dev/staging 无 CF，deploy_cloudfront=false 不写 SSM）。
  has_cf = var.env == "prod"
}

# 账号 ID（由 landing-zone 发布）。用于构造 CloudFront distribution ARN（prod）。
data "aws_ssm_parameter" "account_id" {
  name = "/landing-zone/accounts/${var.env}/account_id"
}

# 本应用部署角色 ARN（一致性校验）。
data "aws_ssm_parameter" "deploy_role_arn" {
  name = "/infra/bl/${var.env}/ap-east-1/platform/role-app-deploy-${local.repo_pascal}-${local.env_pascal}-arn"
}

# prod 共享 CloudFront distribution ID（仅 prod 存在；CI invalidate 时亦直接从 SSM 读）。
data "aws_ssm_parameter" "cf_distribution_id" {
  count = local.has_cf ? 1 : 0
  name  = "/balance/ingress/external/${var.env}/cloudfront/distribution_id"
}
