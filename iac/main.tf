locals {
  name = "${var.app_name}-${var.env}"

  # 显式日志组名，便于把 retention 与 Lambda 解耦管理（Lambda 默认隐式创建无 retention 的组）。
  log_group_name = "/aws/lambda/${local.name}"
}

# ---------------------------------------------------------------------------
# 打包：把 app/ 目录打成 zip 供 Lambda 部署。
# 纯 stdlib handler 无第三方依赖，直接 zip 源码即可；如需依赖，CI 在打包前 pip install -t app/。
# ---------------------------------------------------------------------------
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../app"
  output_path = "${path.module}/.build/${local.name}.zip"
  excludes    = ["README.md"]
}

# ---------------------------------------------------------------------------
# Lambda 执行角色（scoped）：只授予写本函数日志组的权限。
# 角色由部署角色（AppDeployRole）创建，须挂 PermissionsBoundary 防提权——
# 边界 policy 由基础设施统一发布；这里读其 ARN（如基础设施暴露 SSM 可改为 data 读取）。
# 默认不附加 boundary 以保证模板在未登记环境也能 validate；接入真实环境时按平台指引补 permissions_boundary。
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name}-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  # 接入真实环境时取消注释并指向基础设施发布的边界 policy ARN（防提权强制要求）：
  # permissions_boundary = data.aws_ssm_parameter.permissions_boundary_arn.value
}

# 仅日志写权限，scoped 到本函数的日志组。
data "aws_iam_policy_document" "lambda_logs" {
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda_logs" {
  name   = "${local.name}-logs"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_logs.json
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name = local.name
  role          = aws_iam_role.lambda_exec.arn
  runtime       = var.lambda_runtime
  handler       = var.lambda_handler
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  environment {
    variables = {
      APP_NAME = var.app_name
      ENV      = var.env
    }
  }

  # Lambda 默认不进 VPC（见 data.tf 说明）。需要访问 VPC 内私网资源时取消注释，
  # 并把 lambda_logs policy 补上 ENI 权限（ec2:CreateNetworkInterface/DescribeNetworkInterfaces/DeleteNetworkInterface）。
  # vpc_config {
  #   subnet_ids         = split(",", data.aws_ssm_parameter.private_subnet_ids.value)
  #   security_group_ids = [aws_security_group.lambda.id]
  # }

  # 显式依赖日志组：避免 Lambda 首次调用隐式创建无 retention 的同名组导致冲突。
  depends_on = [
    aws_iam_role_policy.lambda_logs,
    aws_cloudwatch_log_group.lambda,
  ]
}
