# 区域固定 ap-east-1（香港）。
# 部署身份假设 AppDeployRole-<RepoPascal>-<EnvPascal>；ARN 由 CI 从 SSM 读出后以 var.deploy_role_arn 传入。
# provider 的 assume_role 在 SSM data 求值前生效，不能用 data 派生自己要假设的角色。
provider "aws" {
  region = var.region

  assume_role {
    role_arn     = var.deploy_role_arn
    session_name = "${var.app_name}-${var.env}-tofu"
  }

  default_tags {
    tags = {
      App         = var.app_name
      Environment = var.env
      managed-by  = "opentofu"
    }
  }
}
