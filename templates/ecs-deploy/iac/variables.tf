variable "app_name" {
  type        = string
  description = "小写应用名（与 app-registry 一致，用于资源命名与 ECR 仓库路径 app-<app_name>）"
}

variable "repo_pascal" {
  type        = string
  description = "仓库名 PascalCase，用于 AppDeployRole 命名（如 MyApp）"
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
  description = "AppDeployRole ARN（CI 从 SSM 读出后注入；本地 plan 手填）"
}

variable "image_tag" {
  type        = string
  description = "ECR 镜像 tag（app/ 目录内容哈希），CI 注入"
  default     = "latest"
}

variable "app_port" {
  type    = number
  default = 8000
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "enable_container_insights" {
  type        = bool
  default     = null
  nullable    = true
  description = "是否启用 ECS Container Insights；null 时仅 prod 启用，dev/staging 使用 AWS/ECS 基础指标"
}

variable "alb_listener_rule_priority" {
  type        = number
  description = "共享 ALB listener rule 优先级（100–49999，全局唯一，接入前与基础设施确认不冲突）"
}
