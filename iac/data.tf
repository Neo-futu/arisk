# 只读 SSM 派生：对接现有基础设施暴露的参数。禁止硬编码账号 ID / VPC ID / 子网 ID / 角色 ARN。
# 这些 data 在 provider 假设 AppDeployRole 后求值（运行在本应用所属业务账号内）。

locals {
  repo_pascal = var.repo_pascal
  env_pascal  = lookup({ dev = "Development", staging = "Staging", prod = "Production" }, var.env, title(var.env))
}

# 账号 ID（由 landing-zone 发布）。用于断言/构造 ARN 时引用，不要写死。
data "aws_ssm_parameter" "account_id" {
  name = "/landing-zone/accounts/${var.env}/account_id"
}

# 本应用部署角色 ARN（由 app-registry identity/capabilities 声明驱动平台控制面发布）。
# 仅作一致性校验与输出展示；provider 实际假设的角色由 var.deploy_role_arn 提供（见 providers.tf 说明）。
data "aws_ssm_parameter" "deploy_role_arn" {
  name = "/infra/bl/${var.env}/ap-east-1/platform/role-app-deploy-${local.repo_pascal}-${local.env_pascal}-arn"
}

# ---------------------------------------------------------------------------
# VPC / 子网派生。
# 默认本模板的 Lambda 不进 VPC（无需访问 VPC 内私网资源，走公网/AWS 服务端点即可，冷启动更快、无需 ENI/NAT）。
# 当 Lambda 需要访问 VPC 内资源（RDS、ElastiCache、内网服务等）时：
#   1) 取消下面 vpc_id / private_subnet_ids 两个 data 的注释；
#   2) 在 main.tf 的 aws_lambda_function 内取消 vpc_config 块注释；
#   3) 给 lambda exec role 附加 AWSLambdaVPCAccessExecutionRole 等效的 ENI 权限（见 main.tf 注释）。
# ---------------------------------------------------------------------------

# data "aws_ssm_parameter" "vpc_id" {
#   name = "/infra/bl/${var.env}/ap-east-1/network/vpc-id"
# }

# Lambda 进 VPC 用私有子网 tier = priv。
# data "aws_ssm_parameter" "private_subnet_ids" {
#   name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/priv"
# }
# SSM 里子网为逗号分隔字符串，使用时 split：
#   subnet_ids = split(",", data.aws_ssm_parameter.private_subnet_ids.value)
