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

variable "listen_port" {
  type        = number
  default     = 8443
  description = "gateway 监听端口，消费方 ECS 服务向此端口发请求"
}

# ── FUTU 上游配置（填写由 FUTU 网络运维分配的 ECN 机器地址） ─────────────────────

variable "futu_upstream_urls" {
  type        = list(string)
  description = <<-EOT
    FUTU ECN 上游 URL 列表（逗号分隔传给 gateway.py，连接级故障自动 fallback）。
    格式：["http://10.14.132.10:19999", "http://10.14.133.10:19999"]
    ECN IP 由 FUTU 网络运维在 CMDB 申请后分配，每个环境不同；
    端口通常为 19999，确认以 FUTU 侧提供为准。
  EOT
}

variable "futu_upstream_cidrs" {
  type        = list(string)
  description = <<-EOT
    FUTU ECN 上游 CIDR 列表，用于 gateway SG 出站规则白名单。
    与 futu_upstream_urls 中的 IP 对应的 /24 网段，由 FUTU 网络运维提供。
    示例（meerkat dev/staging）：["10.14.132.0/24", "10.14.133.0/24"]
    示例（meerkat prod）：         ["10.15.4.0/24",  "10.15.5.0/24"]
  EOT
}

variable "futu_upstream_port" {
  type        = number
  default     = 19999
  description = "FUTU ECN 上游端口，gateway SG 出站规则放行此端口"
}

# ── 消费方（ECS 服务）SG 配置 ──────────────────────────────────────────────────

variable "consumer_sg_ids" {
  type        = list(string)
  description = <<-EOT
    消费方 ECS service 的 Security Group ID 列表（允许其访问 gateway listen_port）。
    gateway SG 的入站规则：consumer_sg_ids → listen_port/tcp。
    同时，对应的消费方 SG 也需要加出站规则（见 consumer_egress.tf），
    如果消费方 ECS SG 出站已是 0.0.0.0/0 则不需要额外配置。
  EOT
}

# ── EC2 配置 ──────────────────────────────────────────────────────────────────

variable "gateway_private_ip" {
  type        = string
  description = <<-EOT
    gateway EC2 在 partner 子网的固定 IP（ENI 携带，EC2 替换后 IP 不变）。
    消费方通过此 IP 访问 gateway，不走 DNS。
    从 partner 子网可用 IP 中选取，避开已占用地址。
  EOT
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "request_timeout" {
  type        = number
  default     = 30
  description = "gateway 转发请求的超时秒数"
}

# ── SSM 输出路径 ──────────────────────────────────────────────────────────────

variable "gateway_url_ssm_path" {
  type        = string
  description = <<-EOT
    gateway base URL 发布到的 SSM 路径，消费方 IaC 从此路径读取并注入 ECS env var。
    示例：/app/<app_name>/<env>/futu-adapter/gateway-base-url
  EOT
  default     = ""
}
