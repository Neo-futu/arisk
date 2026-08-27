# gateway.py 源码（通过 templatefile 内嵌到 userdata）
# 零依赖纯标准库：partner SG 阻断 TCP 443，无法安装任何外部依赖
locals {
  gateway_py = file("${path.module}/gateway.py")

  userdata = templatefile("${path.module}/userdata.tftpl", {
    gateway_py       = local.gateway_py
    listen_port      = var.listen_port
    upstream_url_csv = local.upstream_url_csv
    request_timeout  = var.request_timeout
  })
}

# ── 独立 ENI：固定 IP，EC2 替换后 IP 不变 ────────────────────────────────────
# 消费方通过固定 IP 访问 gateway，不走 DNS，EC2 替换无需更新任何下游配置。
resource "aws_network_interface" "gateway" {
  subnet_id       = local.partner_subnet_id
  private_ips     = [var.gateway_private_ip]
  security_groups = [aws_security_group.gateway.id]

  tags = { Name = local.name }
}

# ── IAM role（IMDSv2 + SSM Session Manager，无需开放 SSH）────────────────────
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name                 = local.name
  assume_role_policy   = data.aws_iam_policy_document.ec2_assume.json
  managed_policy_arns  = ["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"]
  permissions_boundary = data.aws_ssm_parameter.permission_boundary_arn.value
}

resource "aws_iam_instance_profile" "gateway" {
  name = local.name
  role = aws_iam_role.gateway.name
}

# ── EC2 实例 ──────────────────────────────────────────────────────────────────
resource "aws_instance" "gateway" {
  ami           = data.aws_ssm_parameter.al2023_ami.value
  instance_type = var.instance_type

  network_interface {
    network_interface_id = aws_network_interface.gateway.id
    device_index         = 0
  }

  iam_instance_profile = aws_iam_instance_profile.gateway.name

  user_data = local.userdata

  # 应用代码（gateway.py）变更 → userdata hash 变 → EC2 自动替换
  # ENI 独立于 EC2，替换后 gateway IP 不变，消费方无感知
  user_data_replace_on_change = true

  metadata_options {
    http_tokens = "required" # 强制 IMDSv2，禁止 v1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
  }

  tags = { Name = local.name }
}
