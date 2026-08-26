# 一次性初始化各子项目的 DB roles：
#   <name>_db_owner — DDL（migration 用），CREATEDB
#   <name>_app_rw   — DML only（运行时用），无 DDL
#   <name>_ro       — 只读（分析 / BI / 排障用），仅 SELECT
# 使用 RDS master 密码连库，完成后 master 密码由 Secrets Manager 封存。
# 运行时服务与各角色均通过 RDS IAM 认证，不使用静态密码。
#
# 新增子项目时：在 subproject_names 列表添加新名称，tofu apply 会触发重跑。
# 约定：PostgreSQL role 名用下划线版本，业务库名 = 子项目名（下划线版本）。

locals {
  subproject_names = ["svc_a"]
}

resource "aws_security_group" "db_init" {
  name        = "${local.name}-db-init"
  description = "DB role 初始化 Fargate task（一次性）"
  vpc_id      = local.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_iam_policy_document" "db_init_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "db_init_exec" {
  name                 = "${local.name}-db-init-exec"
  assume_role_policy   = data.aws_iam_policy_document.db_init_assume.json
  managed_policy_arns  = ["arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"]
  permissions_boundary = data.aws_ssm_parameter.permission_boundary_arn.value
}

resource "aws_iam_role" "db_init_task" {
  name                 = "${local.name}-db-init-task"
  assume_role_policy   = data.aws_iam_policy_document.db_init_assume.json
  permissions_boundary = data.aws_ssm_parameter.permission_boundary_arn.value
}

resource "aws_iam_role_policy" "db_init_task" {
  name = "secrets-read"
  role = aws_iam_role.db_init_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.rds_master.arn
    }]
  })
}

resource "aws_iam_role_policy" "db_init_exec_secrets" {
  name = "secrets-read"
  role = aws_iam_role.db_init_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.rds_master.arn
    }]
  })
}

locals {
  # 为每个子项目生成建角色 SQL（连 postgres 库执行）：
  #   owner（DDL/CREATEDB）、app_rw（无 DDL）、ro（只读）
  db_role_sql = join("\n", [for name in local.subproject_names : <<-SQL
    -- ${name}
    DO $$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${name}_db_owner') THEN
        CREATE ROLE ${name}_db_owner WITH LOGIN CREATEDB NOCREATEROLE;
        GRANT rds_iam TO ${name}_db_owner;
      END IF;
      GRANT ${name}_db_owner TO ${var.app_name};
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${name}_app_rw') THEN
        CREATE ROLE ${name}_app_rw WITH LOGIN NOCREATEDB NOCREATEROLE;
        GRANT rds_iam TO ${name}_app_rw;
      END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${name}_ro') THEN
        CREATE ROLE ${name}_ro WITH LOGIN NOCREATEDB NOCREATEROLE;
        GRANT rds_iam TO ${name}_ro;
      END IF;
    END $$;
  SQL
  ])
}

resource "aws_ecs_task_definition" "db_init" {
  family                   = "${local.name}-db-init"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.db_init_exec.arn
  task_role_arn            = aws_iam_role.db_init_task.arn

  container_definitions = jsonencode([{
    name      = "psql"
    image     = "postgres:16-alpine"
    essential = true
    secrets = [
      { name = "PGPASSWORD", valueFrom = aws_secretsmanager_secret.rds_master.arn },
    ]
    command = [
      "sh", "-c",
      <<-CMD
        set -eu
        PSQL="psql -h ${aws_db_instance.main.address} -U ${var.app_name} -v ON_ERROR_STOP=1"

        # 1) 建角色（连 postgres 库；幂等）
        $PSQL -d postgres -c "${replace(local.db_role_sql, "\"", "\\\"")}"

        # 2) 幂等创建业务库，再授予 app_rw（DML）和 ro（只读）表级权限
        # ALTER DEFAULT PRIVILEGES FOR ROLE db_owner 确保 migration 未来新建的表自动继承权限
        for name in ${join(" ", local.subproject_names)}; do
          EXISTS=$($PSQL -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$name'")
          if [ "$EXISTS" != "1" ]; then
            echo "creating database '$name'"
            $PSQL -d postgres -c "CREATE DATABASE $name OWNER $${name}_db_owner"
          fi
          echo "granting app_rw on database '$name'"
          $PSQL -d "$name" -c "GRANT CONNECT ON DATABASE $name TO $${name}_app_rw; GRANT USAGE ON SCHEMA public TO $${name}_app_rw; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $${name}_app_rw; GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $${name}_app_rw; ALTER DEFAULT PRIVILEGES FOR ROLE $${name}_db_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $${name}_app_rw; ALTER DEFAULT PRIVILEGES FOR ROLE $${name}_db_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO $${name}_app_rw;"
          echo "granting readonly on database '$name'"
          $PSQL -d "$name" -c "REVOKE CREATE ON SCHEMA public FROM $${name}_ro; GRANT CONNECT ON DATABASE $name TO $${name}_ro; GRANT USAGE ON SCHEMA public TO $${name}_ro; GRANT SELECT ON ALL TABLES IN SCHEMA public TO $${name}_ro; ALTER DEFAULT PRIVILEGES FOR ROLE $${name}_db_owner IN SCHEMA public GRANT SELECT ON TABLES TO $${name}_ro;"
        done
      CMD
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/${local.name}-db-init"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "init"
        "awslogs-create-group"  = "true"
      }
    }
  }])
}

# null_resource：tofu apply 时如 RDS 或任务定义有变化则自动重跑
resource "null_resource" "db_init" {
  triggers = {
    rds_resource_id = aws_db_instance.main.resource_id
    task_def_arn    = aws_ecs_task_definition.db_init.arn
    subprojects     = join(",", local.subproject_names)
  }

  provisioner "local-exec" {
    command = <<-CMD
      set -eu
      TASK_ARN=$(aws ecs run-task \
        --cluster ${aws_ecs_cluster.db_init.name} \
        --task-definition ${aws_ecs_task_definition.db_init.arn} \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[${join(",", local.priv_subnet_ids)}],securityGroups=[${aws_security_group.db_init.id}],assignPublicIp=DISABLED}" \
        --region ${var.region} \
        --query 'tasks[0].taskArn' \
        --output text)
      aws ecs wait tasks-stopped \
        --cluster ${aws_ecs_cluster.db_init.name} \
        --tasks "$TASK_ARN" \
        --region ${var.region}
      EXIT_CODE=$(aws ecs describe-tasks \
        --cluster ${aws_ecs_cluster.db_init.name} \
        --tasks "$TASK_ARN" \
        --query 'tasks[0].containers[0].exitCode' \
        --output text)
      if [ "$EXIT_CODE" != "0" ]; then
        echo "DB init task failed (exit code: $EXIT_CODE)"
        exit 1
      fi
    CMD
  }

  depends_on = [aws_db_instance.main]
}

# 专用 ECS cluster 仅供 db_init 任务使用
resource "aws_ecs_cluster" "db_init" {
  name = "${local.name}-db-init"
}
