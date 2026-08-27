# 只读 SSM 派生：对接现有基础设施暴露的参数。禁止硬编码账号 ID / VPC ID / 子网 ID / 角色 ARN。

locals {
  name       = "${var.app_name}-dev-server"
  account_id = data.aws_caller_identity.current.account_id

  vpc_id          = nonsensitive(data.aws_ssm_parameter.vpc_id.value)
  priv_subnet_ids = split(",", nonsensitive(data.aws_ssm_parameter.priv_subnet_ids.value))
  ami_id          = nonsensitive(data.aws_ssm_parameter.al2023_ami.value)

  permission_boundary_arn = nonsensitive(data.aws_ssm_parameter.permission_boundary_arn.value)

  # 根卷：基准 20 GB + 每位开发人员 40 GB（1人→60G / 2人→100G / 3人→140G）
  root_volume_size_gb = 20 + var.developer_count * 40
}

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "vpc_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/vpc-id"
}

data "aws_ssm_parameter" "priv_subnet_ids" {
  name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/priv"
}

data "aws_ssm_parameter" "permission_boundary_arn" {
  name = "/infra/bl/${var.env}/ap-east-1/platform/permission-boundary-arn"
}

# Latest Amazon Linux 2023 AMI（AWS-managed SSM parameter，无需 ec2:DescribeImages）
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
