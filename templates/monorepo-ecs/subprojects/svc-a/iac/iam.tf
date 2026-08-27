data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ── Execution role（拉镜像 + 写 CloudWatch） ────────────────────────────────

resource "aws_iam_role" "task_exec" {
  name                 = "${local.name}-exec"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  managed_policy_arns  = ["arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"]
  permissions_boundary = data.aws_ssm_parameter.permission_boundary_arn.value
}

# ── 运行时 Task role（无 DDL，只能 rds-db:connect 到 app_rw） ────────────────

resource "aws_iam_role" "task" {
  name                 = "${local.name}-task"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  permissions_boundary = data.aws_ssm_parameter.permission_boundary_arn.value
}

resource "aws_iam_role_policy" "task_rds_iam" {
  name = "rds-iam-connect"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["rds-db:connect"]
      # 只允许连接 svc_a_app_rw role，不允许 owner role（有 DDL 权限）
      Resource = "arn:aws:rds-db:${var.region}:${data.aws_caller_identity.current.account_id}:dbuser:${local.rds_resource_id}/svc_a_app_rw"
    }]
  })
}

# dev only：ECS Exec 调试用，task role 加 ssmmessages 权限
resource "aws_iam_role_policy" "task_ecs_exec" {
  count = var.env == "dev" ? 1 : 0
  name  = "ecs-exec"
  role  = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel",
      ]
      Resource = "*"
    }]
  })
}

# ── DB owner Task role（有 DDL，仅供 migration job 使用） ─────────────────────

resource "aws_iam_role" "db_owner_task" {
  name                 = "${local.name}-db-owner-task"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  permissions_boundary = data.aws_ssm_parameter.permission_boundary_arn.value
}

resource "aws_iam_role" "db_owner_exec" {
  name                 = "${local.name}-db-owner-exec"
  assume_role_policy   = data.aws_iam_policy_document.ecs_assume.json
  managed_policy_arns  = ["arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"]
  permissions_boundary = data.aws_ssm_parameter.permission_boundary_arn.value
}

resource "aws_iam_role_policy" "db_owner_rds_iam" {
  name = "rds-iam-connect"
  role = aws_iam_role.db_owner_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["rds-db:connect"]
      # 只允许连接 svc_a_db_owner role（有 DDL），migration job 专用
      Resource = "arn:aws:rds-db:${var.region}:${data.aws_caller_identity.current.account_id}:dbuser:${local.rds_resource_id}/svc_a_db_owner"
    }]
  })
}
