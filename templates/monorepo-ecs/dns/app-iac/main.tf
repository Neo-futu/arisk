# =============================================================================
# dns/app-iac — （旧 / 特例）自管公网入口（cert + 专用公网 ALB + TG）
# -----------------------------------------------------------------------------
# 注意：managed domain（balancehk.com / balancehk.ai）的 customer/ops 入口默认
#   消费平台共享 ALB（在 app-registry 声明 ingress.hostnames，应用只建 TG +
#   listener rule，平台拥有 cert/Route53/CloudFront）。本目录的自管公网入口仅用于
#   非 managed domain 自定义客户域，或经平台评审获准的专属 ALB。详见 README §2.5
#   与根 AGENTS.md §「公网 / ops 域名（消费平台共享 ALB）」。
# -----------------------------------------------------------------------------
# 职责（走自管路径时）：
#   为 services.tf 中声明的每个公网子项目，在对应环境账号里创建：
#   - ACM 公网证书（DNS 验证方式；验证 CNAME 由 CI deploy-dns-route53 写入 Route53）
#   - 专用公网 ALB + Security Group
#   - ALB Target Group（ECS task IP 注册点；子项目 ECS service 注册到此 TG）
#   - HTTP → HTTPS 301 重定向 listener
#   - HTTPS listener（证书 PENDING 期间 listener 已存在，cert ISSUED 后流量自动生效）
#
# 完成 apply 后，CI job (_deploy-dns-app.yml) 读取 dns_handoffs output，
# 交给 deploy-dns-route53 在公网 Hosted Zone 中 UPSERT 验证 CNAME 与 leaf A 记录。
#
# SSM 写出（供子项目 iac/ 读取，见 ssm.tf）：
#   /app/<app_name>/<svc>/<env>/public-cert-arn   — ACM 证书 ARN
#   /app/<app_name>/<svc>/<env>/public-tg-arn     — ALB Target Group ARN
#   /app/<app_name>/<svc>/<env>/public-alb-sg-id  — ALB Security Group ID
#
# State key: app/<app_name>/dns-app/<env>/terraform.tfstate
# =============================================================================

data "aws_ssm_parameter" "vpc_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/vpc-id"
}

data "aws_ssm_parameter" "pub_subnet_ids" {
  name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/pub"
}

# ── ACM 证书 ─────────────────────────────────────────────────────────────────

resource "aws_acm_certificate" "cert" {
  for_each = local.services

  domain_name               = each.value.cert_domain
  subject_alternative_names = each.value.cert_san
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate" "leaf_cert" {
  for_each = { for k, v in local.services : k => v if length(v.leaf_domains) > 0 }

  domain_name               = each.value.leaf_domains[0]
  subject_alternative_names = slice(each.value.leaf_domains, 1, length(each.value.leaf_domains))
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# ── ALB Security Groups ───────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  for_each = local.services

  name        = "${each.value.alb_base}-alb-sg"
  description = "${each.key} internet-facing ALB (${var.env})"
  vpc_id      = data.aws_ssm_parameter.vpc_id.value

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP from internet (301 redirect only)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── 专用公网 ALB ───────────────────────────────────────────────────────────────

resource "aws_lb" "public" {
  for_each = local.services

  # 命名规则 {alb_base}-p（含后缀须 ≤32 字符）
  name               = "${each.value.alb_base}-p"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[each.key].id]
  subnets            = split(",", data.aws_ssm_parameter.pub_subnet_ids.value)

  lifecycle {
    ignore_changes = [tags, tags_all]
  }
}

# ── Target Groups ─────────────────────────────────────────────────────────────

resource "aws_lb_target_group" "app" {
  for_each = local.services

  # 命名规则 {alb_base}-atg（含后缀须 ≤32 字符）
  name        = "${each.value.alb_base}-atg"
  port        = each.value.app_port
  protocol    = "HTTP"
  vpc_id      = data.aws_ssm_parameter.vpc_id.value
  target_type = "ip"

  health_check {
    path                = each.value.hc_path
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = each.value.hc_matcher
  }

  lifecycle {
    ignore_changes = [tags, tags_all]
  }
}

# ── HTTP Listener: 80 → 443 永久重定向 ───────────────────────────────────────

resource "aws_lb_listener" "http" {
  for_each = local.services

  load_balancer_arn = aws_lb.public[each.key].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# ── HTTPS Listener ────────────────────────────────────────────────────────────
# 证书 PENDING 期间 listener 已就绪；cert ISSUED 后 HTTPS 流量自动生效。

resource "aws_lb_listener" "https" {
  for_each = local.services

  load_balancer_arn = aws_lb.public[each.key].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.cert[each.key].arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[each.key].arn
  }
}

# 多叶证书时挂到同一 HTTPS listener
resource "aws_lb_listener_certificate" "leaf_cert" {
  for_each = aws_acm_certificate.leaf_cert

  listener_arn    = aws_lb_listener.https[each.key].arn
  certificate_arn = each.value.arn
}

# ── 裸域 301 重定向（门户类服务可选）─────────────────────────────────────────
# apex_redirect = true 时，把裸域 <domain> 301 跳到 www.<domain>。

resource "aws_lb_listener_rule" "apex_redirect" {
  for_each = { for k, v in local.services : k => v if v.apex_redirect }

  listener_arn = aws_lb_listener.https[each.key].arn
  priority     = 10

  condition {
    host_header {
      values = [var.domain]
    }
  }

  action {
    type = "redirect"
    redirect {
      host        = "www.${var.domain}"
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
