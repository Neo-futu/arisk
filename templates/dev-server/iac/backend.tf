# Partial backend：backend 块不支持变量，由 tofu init 时 -backend-config 注入。
#
# 约定：
#   bucket         = "balance-tf-state-dev-ap-east-1"
#   dynamodb_table = "balance-tf-locks-dev-ap-east-1"
#   key            = "app/<app-name>/dev-server/dev/terraform.tfstate"
#   region         = "ap-east-1"
#   encrypt        = true
terraform {
  backend "s3" {}
}
