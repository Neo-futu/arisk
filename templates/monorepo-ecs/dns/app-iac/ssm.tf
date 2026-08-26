# 写出供子项目 IaC 消费的 SSM 参数。
# 子项目 iac/ 通过 data "aws_ssm_parameter" 读取这三个值接入公网入口，
# 禁止在子项目里自建公网 ALB 或自申 ACM 证书。

resource "aws_ssm_parameter" "cert_arn" {
  for_each = local.services

  name  = "/app/${var.app_name}/${each.key}/${var.env}/public-cert-arn"
  type  = "String"
  value = aws_acm_certificate.cert[each.key].arn
}

resource "aws_ssm_parameter" "tg_arn" {
  for_each = local.services

  name  = "/app/${var.app_name}/${each.key}/${var.env}/public-tg-arn"
  type  = "String"
  value = aws_lb_target_group.app[each.key].arn
}

resource "aws_ssm_parameter" "alb_sg_id" {
  for_each = local.services

  name  = "/app/${var.app_name}/${each.key}/${var.env}/public-alb-sg-id"
  type  = "String"
  value = aws_security_group.alb[each.key].id
}
