# Partial backend：Terraform/OpenTofu 的 backend 块不支持变量/插值，因此这里留空，
# 由 tofu init 时用 -backend-config 注入（CI 生成或本地手填 backend.<env>.hcl）。
#
# 约定（基础设施已 bootstrap，勿改）：
#   bucket         = "balance-tf-state-<env>-ap-east-1"
#   dynamodb_table = "balance-tf-locks-<env>-ap-east-1"
#   key            = "app/<app-name>/<env>/terraform.tfstate"
#   region         = "ap-east-1"
#   encrypt        = true
#
# 多形态混合仓（同时有 lambda + static）须声明 deployment.state.layout: monorepo-components，
# 此时 key 形如 app/<app-name>/static/<env>/terraform.tfstate。
#
# 用法：
#   tofu init -backend-config=backend.<env>.hcl
# backend.<env>.hcl 已在 .gitignore 中忽略（含账号级路径，不入仓）。
terraform {
  backend "s3" {}
}
