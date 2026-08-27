locals {
  bucket_name = "${var.app_name}-static-${var.env}-ap-east-1"

  # prod: CloudFront distribution ARN（账号 ID + distribution ID 均来自 SSM）。
  # CF 部署在同一业务账号内，故账号 ID 与 S3 桶一致。
  cf_distribution_arn = local.has_cf ? "arn:aws:cloudfront::${data.aws_ssm_parameter.account_id.value}:distribution/${data.aws_ssm_parameter.cf_distribution_id[0].value}" : null
}

# ---------------------------------------------------------------------------
# S3 静态桶（应用自建）
#
# 命名约定：<app_name>-static-<env>-ap-east-1
# AppDeployRole 按此命名约定获得 s3:* 权限（infra platform-iam 已按前缀授权）。
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "static" {
  bucket = local.bucket_name

  tags = {
    Purpose = "static-site"
  }
}

# 安全基线：完整禁止公网直访（infra SCP 亦强制，此处显式配置便于 tofu validate 检查）。
resource "aws_s3_bucket_public_access_block" "static" {
  bucket                  = aws_s3_bucket.static.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 安全基线：服务端加密（SSE-S3/AES256）。
resource "aws_s3_bucket_server_side_encryption_configuration" "static" {
  bucket = aws_s3_bucket.static.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# 版本控制：允许回滚到上一次同步的静态文件版本。
resource "aws_s3_bucket_versioning" "static" {
  bucket = aws_s3_bucket.static.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ---------------------------------------------------------------------------
# 桶策略（prod-only）：允许共享 CloudFront distribution 经 OAC 读取。
#
# 前提：infra 须已为本应用在 cloudfront-external 模块创建 OAC 并把本桶加为 S3 origin。
# 触发方式：在 app-registry 的 capabilities.compute 列表中声明 static-site，
#           并在 capabilities.ingress 中声明 customer-web；
#           app-onboarding 消费后触发平台控制面完成 OAC + CF origin 关联。
#
# dev/staging：无 CloudFront，开发者通过 bl-dev s3 + IAM auth 访问桶内容。
# ---------------------------------------------------------------------------
resource "aws_s3_bucket_policy" "static" {
  count  = local.has_cf ? 1 : 0
  bucket = aws_s3_bucket.static.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontOACRead"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.static.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = local.cf_distribution_arn
          }
        }
      },
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.static]
}

# ---------------------------------------------------------------------------
# bl-dev S3 registry（dev-only）：开发者用 bl-dev s3 ls <app> 发现此桶。
# ---------------------------------------------------------------------------
resource "aws_ssm_parameter" "bl_dev_s3_registry" {
  count = var.env == "dev" ? 1 : 0

  name        = "/app/${var.app_name}/${var.env}/s3-data-bucket"
  description = "bl-dev S3 registry: static site bucket for ${var.app_name} ${var.env}"
  type        = "String"
  value       = aws_s3_bucket.static.bucket
}
