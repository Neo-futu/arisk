# 对接 infra ingress 共享外部 ALB（R-06/R-07）：应用只挂 target group + listener rule，
# 不自建 ALB。listener_arn 与 ALB SG ID 从 SSM 读取。

resource "aws_lb_target_group" "app" {
  name        = "${var.app_name}-${var.env}"
  port        = var.app_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = local.vpc_id

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
  }
}

resource "aws_lb_listener_rule" "app" {
  listener_arn = nonsensitive(data.aws_ssm_parameter.external_listener_443_arn.value)
  priority     = var.alb_listener_rule_priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  condition {
    host_header {
      values = [local.app_fqdn]
    }
  }
}
