# 内网 DNS：在平台 PHZ 注册 {service_name}.{env}.bl.internal
# 让同 VPC 消费方通过稳定域名访问，不依赖 ALB ephemeral DNS name。
# alias 指向 alb.tf 中的内部 ALB（aws_lb.internal）。

resource "aws_route53_record" "internal" {
  zone_id = nonsensitive(data.aws_ssm_parameter.phz_id.value)
  # 记录名只写短名（如 "svc-a"），Route53 自动拼 Zone 后缀得到 svc-a.dev.bl.internal
  name = var.service_name
  type = "A"

  alias {
    name                   = aws_lb.internal.dns_name
    zone_id                = aws_lb.internal.zone_id
    evaluate_target_health = true
  }
}
