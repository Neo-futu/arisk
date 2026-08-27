variable "app_name" {
  description = "应用名（小写连字符）。用于资源命名与标签，决定 state key app/<app_name>/<env>/。"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}[a-z0-9]$", var.app_name))
    error_message = "app_name 须为小写字母/数字/连字符，3-32 字符，不以连字符结尾。"
  }
}

variable "repo_pascal" {
  description = "仓库名的 PascalCase 形式，用于拼 SSM 部署角色路径与 AppDeployRole-<RepoPascal>-<EnvPascal>。"
  type        = string
}

variable "env" {
  description = "环境：dev / staging / prod。"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env 仅支持 dev / staging / prod。"
  }
}

variable "region" {
  description = "AWS 区域，固定 ap-east-1（香港）。"
  type        = string
  default     = "ap-east-1"
}

variable "deploy_role_arn" {
  description = <<-EOT
    部署角色 ARN（AppDeployRole-<RepoPascal>-<EnvPascal>），provider 假设它执行 tofu。
    CI 在 tofu 前从 SSM /infra/bl/<env>/ap-east-1/platform/role-app-deploy-<RepoPascal>-<EnvPascal>-arn 读出后注入；
    本地手动 plan 时手填。data.tf 会读同一 SSM 值做一致性校验。
  EOT
  type        = string
}
