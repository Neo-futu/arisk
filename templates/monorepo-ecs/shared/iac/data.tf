locals {
  name            = "${var.app_name}-${var.env}"
  vpc_id          = nonsensitive(data.aws_ssm_parameter.vpc_id.value)
  data_subnet_ids = split(",", nonsensitive(data.aws_ssm_parameter.data_subnet_ids.value))
  priv_subnet_ids = split(",", nonsensitive(data.aws_ssm_parameter.priv_subnet_ids.value))
}

data "aws_ssm_parameter" "vpc_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/vpc-id"
}

data "aws_ssm_parameter" "data_subnet_ids" {
  name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/data"
}

data "aws_ssm_parameter" "priv_subnet_ids" {
  name = "/infra/bl/${var.env}/ap-east-1/network/subnet-ids/priv"
}

data "aws_ssm_parameter" "permission_boundary_arn" {
  name = "/infra/bl/${var.env}/ap-east-1/platform/permission-boundary-arn"
}

data "aws_caller_identity" "current" {}
