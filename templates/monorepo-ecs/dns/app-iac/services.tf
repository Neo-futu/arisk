# =============================================================================
# dns/app-iac/services.tf — 公网服务声明
# -----------------------------------------------------------------------------
# 在此处声明所有需要自定义公网域名的子项目。
# 每条记录驱动：ACM 证书、专用公网 ALB、Target Group、SSM 参数写入。
#
# 设计要点：
#   - 公网入口集中在本子项目，子项目 iac/ 不自建公网 ALB / 不自申 ACM，
#     只读 ssm.tf 写出的 public-cert/tg/sg 三个参数接入（见 svc-a/iac/data.tf）。
#   - prod 用裸子域，dev/staging 多一层 <env>（见 cert_domain 三元）。
#   - ALB / TG 命名受 32 字符限制：用 alb_base 控制长度，最长环境（staging）也要 ≤32。
#
# 新增公网子项目时：
#   1. 在 local.services 中加一条记录
#   2. 同步更新 deploy-dev.yml / deploy-all.yml 的 dns 相关 job 依赖
# =============================================================================

locals {
  services = {
    "svc-a" = {
      # ALB / TG 命名基础（含后缀 -p / -atg 后须 ≤32 字符）
      alb_base = "${var.app_name}-svc-a-${var.env}"
      # 公网域名：prod 用裸子域，其他环境多一层 <env>
      cert_domain = var.env == "prod" ? "svc-a.${var.domain}" : "svc-a.${var.env}.${var.domain}"
      cert_san    = []
      app_port    = 8000
      hc_path     = "/health"
      hc_matcher  = "200"
      # 额外叶证书域名（同一 ALB 多域名时用），无则留空
      leaf_domains = []
      # 是否加裸域 -> www 的 301 重定向规则（仅门户类服务需要）
      apex_redirect = false
    }
  }
}
