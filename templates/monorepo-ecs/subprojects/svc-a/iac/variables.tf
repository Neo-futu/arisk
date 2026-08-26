variable "app_name" {
  type        = string
  description = "小写应用名（与 app-registry 一致）"
}

variable "repo_pascal" {
  type        = string
  description = "仓库名 PascalCase，用于 AppDeployRole 命名"
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

variable "image_tag" {
  type        = string
  description = "ECR 镜像 tag（subprojects/svc-a/app/ 目录内容哈希），CI 注入"
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

variable "service_name" {
  type        = string
  default     = "svc-a"
  description = "服务短名（小写，用于内网 DNS 记录名 {service_name}.{env}.bl.internal，须与 dns/app-iac 的 service key 一致）"
}

variable "domain" {
  type        = string
  description = "应用公网根域名（如 example.com）。prod 用裸子域 <svc>.<domain>，其他环境用 <svc>.<env>.<domain>；须与 dns/app-iac/variables.tf 的 domain 一致"
}
