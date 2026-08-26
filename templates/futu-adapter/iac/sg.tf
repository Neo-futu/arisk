# ──────────────────────────────────────────────────────────────────────────────
# Gateway SG（futu-adapter 侧）
#
# 入站：consumer_sg_ids → listen_port/tcp
# 出站：futu_upstream_cidrs → futu_upstream_port/tcp（仅放行 FUTU ECN 网段，最小权限）
#
# 不加 default egress "allow all"，partner 子网出站只放行 FUTU ECN，
# 其余出站（含 SSM endpoint TCP 443）均被 SG 阻断——这是预期行为，
# gateway.py 零依赖纯标准库，不需要出站 443。
# ──────────────────────────────────────────────────────────────────────────────

resource "aws_security_group" "gateway" {
  name        = local.name
  description = "${var.app_name} futu-adapter gateway (${var.env}): ingress from consumers, egress to FUTU ECN only"
  vpc_id      = local.vpc_id
}

# 入站：每个消费方 SG 单独一条规则（Terraform 管理，state 可审计）
resource "aws_vpc_security_group_ingress_rule" "from_consumer" {
  for_each = toset(var.consumer_sg_ids)

  security_group_id            = aws_security_group.gateway.id
  referenced_security_group_id = each.value
  from_port                    = var.listen_port
  to_port                      = var.listen_port
  ip_protocol                  = "tcp"
  description                  = "Allow consumer ECS task (${each.value}) → gateway:${var.listen_port}"
}

# 出站：每个 FUTU ECN CIDR 单独一条规则
resource "aws_vpc_security_group_egress_rule" "to_futu" {
  for_each = toset(var.futu_upstream_cidrs)

  security_group_id = aws_security_group.gateway.id
  cidr_ipv4         = each.value
  from_port         = var.futu_upstream_port
  to_port           = var.futu_upstream_port
  ip_protocol       = "tcp"
  description       = "Allow gateway → FUTU ECN ${each.value}:${var.futu_upstream_port} (via TGW)"
}

# ──────────────────────────────────────────────────────────────────────────────
# 消费方 SG 出站规则（可选，仅当消费方 ECS SG 出站非全放通时需要）
#
# 如果消费方 SG 出站已是 0.0.0.0/0，将 add_consumer_egress_rules 设为 false 跳过。
# 如果消费方 SG 出站是收紧的（最小权限），将 add_consumer_egress_rules 设为 true，
# 本资源为消费方 SG 添加允许访问 gateway 的出站规则。
# ──────────────────────────────────────────────────────────────────────────────

variable "add_consumer_egress_rules" {
  type        = bool
  default     = false
  description = <<-EOT
    是否为消费方 SG 添加出站规则（消费方 SG → gateway listen_port/tcp）。
    消费方 SG 出站已是 0.0.0.0/0 时设为 false（默认）。
    消费方 SG 出站已收紧时设为 true，本模板自动补充出站规则。
  EOT
}

resource "aws_vpc_security_group_egress_rule" "consumer_to_gateway" {
  for_each = var.add_consumer_egress_rules ? toset(var.consumer_sg_ids) : toset([])

  security_group_id            = each.value
  referenced_security_group_id = aws_security_group.gateway.id
  from_port                    = var.listen_port
  to_port                      = var.listen_port
  ip_protocol                  = "tcp"
  description                  = "Allow consumer ECS task → futu-adapter gateway:${var.listen_port}"
}
