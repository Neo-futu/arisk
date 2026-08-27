# 将共享基础设施的连接信息发布到 SSM，供各子项目 IaC 和 ECS task 读取。
# 子项目 IaC 通过 data "aws_ssm_parameter" 读取，禁止硬编码 endpoint / SG / ARN。

locals {
  ssm_prefix = "/app/${var.app_name}/${var.env}/shared"
}

resource "aws_ssm_parameter" "rds_endpoint" {
  name  = "${local.ssm_prefix}/rds/endpoint"
  type  = "String"
  value = aws_db_instance.main.address
}

resource "aws_ssm_parameter" "rds_port" {
  name  = "${local.ssm_prefix}/rds/port"
  type  = "String"
  value = tostring(aws_db_instance.main.port)
}

resource "aws_ssm_parameter" "rds_resource_id" {
  name  = "${local.ssm_prefix}/rds/resource-id"
  type  = "String"
  value = aws_db_instance.main.resource_id
}

resource "aws_ssm_parameter" "rds_sg_id" {
  name  = "${local.ssm_prefix}/rds/sg-id"
  type  = "String"
  value = aws_security_group.rds.id
}

resource "aws_ssm_parameter" "rds_master_secret_arn" {
  name  = "${local.ssm_prefix}/rds/master-secret-arn"
  type  = "SecureString"
  value = aws_secretsmanager_secret.rds_master.arn
}
