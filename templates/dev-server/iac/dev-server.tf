# =============================================================================
# 云端开发机：Spot EC2（dev only）
# -----------------------------------------------------------------------------
# 约束：
#   - 仅 dev（var.env 校验强制）
#   - priv 子网，无公网 IP，Security Group 零入站
#   - 访问：SSM Session Manager（DevDataDebugPermissionSet 临时凭证）
#   - Spot persistent（stop on interruption），中断时 EBS 数据保留
#   - EventBridge Scheduler 工作日 08:30–20:30 HKT 自动开关机
#   - IMDSv2 强制（防 SSRF）
# =============================================================================

# ---- Security Group（零入站，全出站）----

resource "aws_security_group" "dev_server" {
  name        = "${local.name}-sg"
  description = "dev-server: zero inbound, SSM-only access"
  vpc_id      = local.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all egress (package installs, SSM endpoints, AWS APIs)"
  }

  tags = { Name = "${local.name}-sg" }
}

# ---- IAM：Instance Role（SSM 最小权限）----

resource "aws_iam_role" "dev_server" {
  name                 = "${local.name}-role"
  permissions_boundary = local.permission_boundary_arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.name}-role" }
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.dev_server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "dev_server" {
  name = "${local.name}-profile"
  role = aws_iam_role.dev_server.name

  tags = { Name = "${local.name}-profile" }
}

# ---- EC2 Spot Instance（persistent，stop on interruption）----

resource "aws_instance" "dev_server" {
  ami                    = local.ami_id
  instance_type          = var.instance_type
  subnet_id              = local.priv_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.dev_server.id]
  iam_instance_profile   = aws_iam_instance_profile.dev_server.name

  # 竞价型：persistent 模式，中断时 stop（EBS 数据保留，容量恢复后自动重启）
  instance_market_options {
    market_type = "spot"
    spot_options {
      spot_instance_type             = "persistent"
      instance_interruption_behavior = "stop"
    }
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = local.root_volume_size_gb
    encrypted             = true
    delete_on_termination = false
    tags                  = { Name = "${local.name}-root" }
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  user_data_base64 = base64encode(<<-EOF
    #!/bin/bash
    systemctl enable amazon-ssm-agent
    systemctl start amazon-ssm-agent
    dnf install -y git tmux vim htop jq unzip make
    EOF
  )

  tags = { Name = local.name }

  lifecycle {
    ignore_changes = [ami]
  }
}

# ---- IAM：EventBridge Scheduler 执行角色（仅 ec2 start/stop 该实例）----

resource "aws_iam_role" "scheduler" {
  name                 = "${local.name}-scheduler-role"
  permissions_boundary = local.permission_boundary_arn

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
      }
    }]
  })

  tags = { Name = "${local.name}-scheduler-role" }
}

resource "aws_iam_role_policy" "scheduler_ec2" {
  name = "ec2-start-stop"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:StartInstances", "ec2:StopInstances"]
      Resource = ["arn:aws:ec2:${var.region}:${local.account_id}:instance/${aws_instance.dev_server.id}"]
    }]
  })
}

# ---- EventBridge Scheduler：工作日自动开关机（HKT = UTC+8）----
# 08:30 HKT = 00:30 UTC；20:30 HKT = 12:30 UTC。周一至周五。

resource "aws_scheduler_schedule" "start" {
  name       = "${local.name}-start"
  group_name = "default"

  flexible_time_window { mode = "OFF" }

  schedule_expression          = "cron(30 0 ? * MON-FRI *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ InstanceIds = [aws_instance.dev_server.id] })
  }
}

resource "aws_scheduler_schedule" "stop" {
  name       = "${local.name}-stop"
  group_name = "default"

  flexible_time_window { mode = "OFF" }

  schedule_expression          = "cron(30 12 ? * MON-FRI *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ InstanceIds = [aws_instance.dev_server.id] })
  }
}
