# 区域固定 ap-east-1（香港）。
# 部署身份假设 AppDeployRole-<RepoPascal>-<EnvPascal>；ARN 由 CI 从 SSM 读出后以 var.deploy_role_arn 传入。
provider "aws" {
  region = var.region

  assume_role {
    role_arn     = var.deploy_role_arn
    session_name = "${var.app_name}-dev-server-tofu"
  }

  default_tags {
    tags = {
      App         = var.app_name
      Environment = var.env
      managed-by  = "opentofu"
    }
  }
}
