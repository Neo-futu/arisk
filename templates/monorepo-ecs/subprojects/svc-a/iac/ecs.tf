resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_security_group" "service" {
  name        = "${local.name}-svc"
  description = "svc-a ECS service (${var.env})"
  vpc_id      = local.vpc_id

  ingress {
    description     = "app port from public ALB (dns/app-iac)"
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [local.public_alb_sg_id]
  }

  ingress {
    description     = "app port from internal ALB (service-to-service via PHZ)"
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.internal_alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = coalesce(var.enable_container_insights, var.env == "prod") ? "enabled" : "disabled"
  }
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.task_exec.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = "svc-a"
    image     = "${local.ecr_registry}/app-${var.app_name}-svc-a:${var.image_tag}"
    essential = true

    portMappings = [{
      containerPort = var.app_port
      protocol      = "tcp"
    }]

    environment = [
      { name = "APP_NAME", value = "svc-a" },
      { name = "ENV", value = var.env },
      { name = "PORT", value = tostring(var.app_port) },
      { name = "DB_HOST", value = local.rds_endpoint },
      { name = "DB_PORT", value = local.rds_port },
      { name = "DB_NAME", value = "svc_a" },
      { name = "DB_USER", value = "svc_a_app_rw" },
      { name = "RDS_RESOURCE_ID", value = local.rds_resource_id },
      { name = "AWS_REGION", value = var.region },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.app.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:${var.app_port}/health')\" || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  # 禁止 ignore_changes = [task_definition]：会导致 tofu apply 后 ECS 不更新 task def
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.db_owner_exec.arn
  task_role_arn            = aws_iam_role.db_owner_task.arn

  container_definitions = jsonencode([{
    name      = "migrate"
    image     = "${local.ecr_registry}/app-${var.app_name}-svc-a:${var.image_tag}"
    essential = true
    command   = ["python", "migrate.py", "run"]

    environment = [
      { name = "APP_NAME", value = "svc-a" },
      { name = "ENV", value = var.env },
      { name = "DB_HOST", value = local.rds_endpoint },
      { name = "DB_PORT", value = local.rds_port },
      { name = "DB_NAME", value = "svc_a" },
      { name = "DB_USER", value = "svc_a_db_owner" },
      { name = "RDS_RESOURCE_ID", value = local.rds_resource_id },
      { name = "AWS_REGION", value = var.region },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.app.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "migrate"
      }
    }
  }])
}

resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = local.priv_subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  # 内部 ALB TG（服务间通过 PHZ 域名访问）
  load_balancer {
    target_group_arn = aws_lb_target_group.internal.arn
    container_name   = "svc-a"
    container_port   = var.app_port
  }

  # 公网 ALB TG（由 dns/app-iac 创建并写入 SSM）
  load_balancer {
    target_group_arn = local.public_tg_arn
    container_name   = "svc-a"
    container_port   = var.app_port
  }

  # dev only：ECS Exec 调试通道
  enable_execute_command = var.env == "dev"
}
