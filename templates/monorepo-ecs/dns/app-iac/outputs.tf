# CI (_deploy-dns-app.yml) 读取此输出，交给 deploy-dns-route53 在公网 Hosted Zone
# 中 UPSERT ACM 验证 CNAME 与 leaf A 记录（详见 .github/workflows/_deploy-dns-app.yml）。

output "dns_handoffs" {
  description = "per-service dns_handoff：acm_validation（验证 CNAME）+ leaf_records（域名 -> ALB 别名）"
  value = {
    for svc, cfg in local.services : svc => {
      acm_validation = [
        for dvo in concat(
          tolist(aws_acm_certificate.cert[svc].domain_validation_options),
          try(tolist(aws_acm_certificate.leaf_cert[svc].domain_validation_options), [])
          ) : {
          name  = dvo.resource_record_name
          type  = dvo.resource_record_type
          value = dvo.resource_record_value
        }
      ]
      leaf_records = concat(
        [{
          domain       = cfg.cert_domain
          alb_dns_name = aws_lb.public[svc].dns_name
          alb_zone_id  = aws_lb.public[svc].zone_id
        }],
        [
          for domain in try(cfg.leaf_domains, []) : {
            domain       = domain
            alb_dns_name = aws_lb.public[svc].dns_name
            alb_zone_id  = aws_lb.public[svc].zone_id
          }
        ],
        cfg.apex_redirect ? [{
          domain       = var.domain
          alb_dns_name = aws_lb.public[svc].dns_name
          alb_zone_id  = aws_lb.public[svc].zone_id
        }] : []
      )
    }
  }
}
