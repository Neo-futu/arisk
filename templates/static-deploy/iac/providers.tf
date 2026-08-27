# 区域固定 ap-east-1（香港），与基础设施一致。
#
# 部署身份：假设本应用经 app-registry 接入面供给的部署角色
#   AppDeployRole-<RepoPascal>-<EnvPascal>
# 该角色 ARN 由基础设施发布在 SSM：
#   /infra/bl/<env>/ap-east-1/platform/role-app-deploy-<RepoPascal>-<EnvPascal>-arn
#
# 注意：provider 的 assume_role 在 SSM data 求值之前生效，无法用 data 派生自己要假设的角色，
# 因此 deploy_role_arn 以变量传入（CI 在 tofu 前从上面 SSM 路径读出后注入，本地手动 plan 时手填）。
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
