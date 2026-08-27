# 内部 ALB —— 供 VPC 内服务间通过 PHZ 域名（svc-a.<env>.bl.internal）访问。
# 公网入口不在这里：公网 ALB / cert / TG 由 dns/app-iac 集中管理，
# 本服务的 ECS task 直接注册到 dns/app-iac 写出的 public-tg-arn（见 ecs.tf）。

resource "aws_security_group" "internal_alb" {
  name        = "${local.name}-int-alb"
  description = "svc-a internal ALB (${var.env})"
  vpc_id      = local.vpc_id

  ingress {
    description = "HTTP from within VPC"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.main.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_vpc" "main" {
  id = local.vpc_id
}

resource "aws_lb" "internal" {
  name               = "${local.name}-int"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.internal_alb.id]
  subnets            = local.priv_subnet_ids
}

resource "aws_lb_target_group" "internal" {
  name        = "${local.name}-int-tg"
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

resource "aws_lb_listener" "internal_http" {
  load_balancer_arn = aws_lb.internal.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.internal.arn
  }
}
