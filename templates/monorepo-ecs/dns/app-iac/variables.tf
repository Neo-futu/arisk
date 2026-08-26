variable "app_name" {
  type        = string
  description = "小写应用名（与 app-registry 一致，用于资源命名与 SSM 路径）"
}

variable "env" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env 仅支持 dev / staging / prod。"
  }
}

variable "region" {
  type    = string
  default = "ap-east-1"
}

variable "deploy_role_arn" {
  type        = string
  description = "AppDeployRole ARN（CI 从 SSM 读出后注入）"
}

variable "domain" {
  type        = string
  description = "应用公网根域名（如 example.com）。prod 用裸子域 svc.<domain>，其他环境用 svc.<env>.<domain>"
}
