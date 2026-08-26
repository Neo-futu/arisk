variable "app_name" {
  type        = string
  description = "小写应用名（与 app-registry 一致，用于资源命名）"
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
  description = "AppDeployRole ARN（CI 从 SSM 读出后注入）"
}

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "rds_allocated_storage" {
  type    = number
  default = 20
}

variable "rds_max_allocated_storage" {
  type    = number
  default = 100
}

variable "postgres_version" {
  type    = string
  default = "16"
}
