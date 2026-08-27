resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "${var.app_name} shared RDS (${var.env})"
  vpc_id      = local.vpc_id

  ingress {
    description = "PostgreSQL from VPC private subnets"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.main.cidr_block]
  }
}

data "aws_vpc" "main" {
  id = local.vpc_id
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = local.data_subnet_ids
}

resource "random_password" "master" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "rds_master" {
  name                    = "${local.name}/rds/master-password"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "rds_master" {
  secret_id     = aws_secretsmanager_secret.rds_master.id
  secret_string = random_password.master.result
}

resource "aws_db_instance" "main" {
  identifier = local.name

  engine         = "postgres"
  engine_version = var.postgres_version
  instance_class = var.rds_instance_class

  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "postgres"
  username = var.app_name
  password = random_password.master.result

  # IAM 认证：运行时服务和 migration job 均走 RDS IAM token，不用静态密码
  iam_database_authentication_enabled = true

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  multi_az            = var.env == "prod"
  publicly_accessible = false
  skip_final_snapshot = var.env != "prod"

  backup_retention_period = var.env == "prod" ? 7 : 1
  deletion_protection     = var.env == "prod"

  performance_insights_enabled = var.env == "prod"
}
