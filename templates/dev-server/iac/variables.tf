variable "app_name" {
  type        = string
  description = "小写应用名（与 app-registry 一致，用于资源命名）"
}

variable "repo_pascal" {
  type        = string
  description = "仓库名 PascalCase，用于 AppDeployRole 命名（如 MyApp）"
}

variable "env" {
  type        = string
  description = "仅支持 dev（云端开发机 dev-only 强默认）"
  default     = "dev"

  validation {
    condition     = var.env == "dev"
    error_message = "dev-server 仅允许 env = dev（平台护栏：ADR-0018）。"
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

variable "developer_count" {
  description = "开发人员数量；根卷 = 20 GB 基准 + 每人 40 GB。推荐实例 t3.medium（2 vCPU / 4 GB）。"
  type        = number
  default     = 2

  validation {
    condition     = var.developer_count >= 1
    error_message = "developer_count 至少为 1。"
  }
}

variable "instance_type" {
  description = "EC2 实例类型；推荐 t3.medium（≤3 人共用），人多或重编译场景可升 t3.large。"
  type        = string
  default     = "t3.medium"
}
