# futu-adapter（FUTU VPN 网关形态）

在 `partner` 子网部署一台轻量 EC2 代理，让 `priv` 子网的 ECS 服务能经由 TGW 访问 FUTU ECN。

## 为什么需要这个

`priv` 子网（ECS 服务所在）的路由表**没有**指向 FUTU ECN CIDR 的 TGW 路由，只有 `partner` 子网有。ECS 服务无法直接访问 FUTU，是路由表约束，不是应用侧能解决的。

```
ECS Fargate（priv 子网）
    │  无法直接到 FUTU（没有 TGW 路由）
    │
    ├─ http → futu-adapter EC2（partner 子网，固定 IP）
    │                  │
    │             TGW（IPsec 隧道，传输层加密）
    │                  │
    └─────────────────►FUTU ECN（10.14.x.x:19999）
```

TGW 已提供传输层加密，gateway→FUTU 走明文 HTTP 是预期行为。

## 目录结构

```
iac/
  versions.tf     — provider 版本约束
  providers.tf    — OIDC assume AppDeployRole
  backend.tf      — S3 partial backend
  variables.tf    — 所有可配置参数（含详细说明）
  data.tf         — SSM 读取 VPC/subnet/AMI
  sg.tf           — SG 创建 + 入站/出站规则（双向均用 Terraform resource 管理）
  ec2.tf          — 独立 ENI（固定 IP）+ EC2 + IAM role
  ssm.tf          — 发布 gateway base URL 到 SSM
  outputs.tf      — gateway URL / SG ID / SSM 路径
  gateway.py      — 零依赖纯标准库 HTTP 代理（内嵌到 userdata）
  userdata.tftpl  — EC2 启动脚本（部署 gateway.py + systemd + 启动自检）
```

## Security Group 说明（最容易踩坑的地方）

连接失败最常见原因是 SG 两侧有一侧规则缺失，两侧都要检查：

### gateway SG（本模板管理，`sg.tf`）

| 方向 | 协议:端口 | 来源/目标 | 说明 |
|------|-----------|-----------|------|
| **入站** | tcp:`listen_port`（默认 8443） | `consumer_sg_ids` 中每个 SG | 消费方 ECS task → gateway |
| **出站** | tcp:`futu_upstream_port`（默认 19999） | `futu_upstream_cidrs` 中每个 CIDR | gateway → FUTU ECN（经 TGW）|
| ~~出站~~ | ~~tcp:443~~ | ~~0.0.0.0/0~~ | **不放行**，partner 子网设计如此，gateway.py 零依赖不需要出站 443 |

### 消费方 ECS SG（消费方自己管理）

| 方向 | 协议:端口 | 来源/目标 | 操作 |
|------|-----------|-----------|------|
| **出站** | tcp:`listen_port` | gateway SG ID（或 gateway 固定 IP/32） | **必须有此规则**，否则 ECS task → gateway 被 SG 拦截 |

如果消费方 ECS SG 出站已是 `0.0.0.0/0`，此规则已隐式包含，无需额外配置。

**如果消费方 SG 出站是收紧的**（最小权限模式），需要在消费方 IaC 中添加：

```hcl
# 在消费方 ECS service 的 IaC 中添加
resource "aws_vpc_security_group_egress_rule" "to_futu_gateway" {
  security_group_id            = aws_security_group.your_ecs_service_sg.id
  referenced_security_group_id = data.aws_ssm_parameter.gateway_sg_id.value  # 从 SSM 或 output 取
  from_port                    = 8443
  to_port                      = 8443
  ip_protocol                  = "tcp"
  description                  = "Allow ECS task → futu-adapter gateway"
}
```

或者直接设 `add_consumer_egress_rules = true`，本模板会自动为 `consumer_sg_ids` 中的每个 SG 添加出站规则。

### 诊断 checklist

连接失败时按此顺序排查：

```
1. EC2 userdata 是否执行成功？
   aws ec2 get-console-output --instance-id <id> --region ap-east-1
   → 看 "gateway deployed" 或 "FAIL" 行

2. gateway.service 是否运行？
   （用 SSM Session Manager 进实例）
   systemctl status gateway.service
   journalctl -u gateway.service -n 50

3. gateway SG 入站规则是否存在？
   aws ec2 describe-security-groups --group-ids <gateway-sg-id>
   → 确认 ingress 有 consumer SG → listen_port 规则

4. 消费方 ECS SG 出站规则是否存在？
   aws ec2 describe-security-groups --group-ids <consumer-sg-id>
   → 确认 egress 有 → gateway SG/IP listen_port 规则（或 0.0.0.0/0）

5. FUTU 侧是否白名单了 gateway 的出口 IP？
   gateway 在 partner 子网，出口 IP = gateway_private_ip（dev 无 SNAT，源 IP 就是私网 IP）
   向 FUTU 网络运维确认此 IP 已在 ECN 白名单
   （注意：白名单登记的 IP 必须与实际出口 IP 完全一致）

6. SG 出站 FUTU ECN CIDR 是否正确？
   确认 futu_upstream_cidrs 包含实际 ECN IP 所在的 /24 网段
```

## 快速起步

### 1. 获取 FUTU ECN 信息

联系 FUTU 网络运维申请 ECN 机器，获取：
- ECN IP 和端口（如 `10.14.132.10:19999`）——填入 `futu_upstream_urls`
- 对应 /24 网段（如 `10.14.132.0/24`）——填入 `futu_upstream_cidrs`
- 确认 gateway 固定 IP（`gateway_private_ip`）已在 FUTU 白名单，或提交申请

详细申请流程见 infra `bl-futu-interconnect/runbook §7`。

### 2. 选取 partner 子网 IP

从 SSM `/infra/bl/<env>/ap-east-1/network/subnet-ids/partner` 查出 partner 子网 CIDR，选一个未被占用的 IP 填入 `gateway_private_ip`。

### 3. 配置变量

```hcl
# dev.tfvars 示例
app_name           = "your-app"
repo_pascal        = "YourApp"
env                = "dev"
gateway_private_ip = "10.63.147.X"      # 从 partner 子网选取
listen_port        = 8443

futu_upstream_urls = ["http://10.14.132.10:19999"]
futu_upstream_cidrs = ["10.14.132.0/24"]

consumer_sg_ids = ["sg-xxxxxxxx"]       # 消费方 ECS task SG ID
# add_consumer_egress_rules = true       # 消费方 SG 出站非全放通时取消注释
```

### 4. 消费方读取 gateway URL

消费方 IaC 中读取 SSM 并注入 ECS task definition：

```hcl
data "aws_ssm_parameter" "gateway_base_url" {
  name = "/app/${var.app_name}/${var.env}/futu-adapter/gateway-base-url"
}

# 在 aws_ecs_task_definition.app 的 container_definitions 中：
{ name = "GATEWAY_BASE_URL", value = data.aws_ssm_parameter.gateway_base_url.value }
```

容器内通过环境变量读取，或经 `entrypoint.sh` 写入 config 文件（参考 `templates/monorepo-ecs/subprojects/svc-a/app/entrypoint.sh`）。

**注意**：gateway URL 在 `tofu apply` 时由 Terraform 固化到 task definition，不在运行时动态读取（partner SG 阻断 TCP 443，容器内也无法访问 SSM endpoint）。

### 5. 部署

```bash
tofu init -backend-config=backend.dev.hcl
tofu apply -var-file=dev.tfvars
```

部署完成后用 `aws ec2 get-console-output` 确认启动自检通过，再部署消费方服务。

## 关键约束

- **upstream URL 不能热更新**：partner SG 阻断 TCP 443，gateway 无法访问 SSM，upstream 配置在 EC2 启动时固化。upstream 变更必须重新 `tofu apply`（触发 EC2 替换，ENI 不变，IP 不变，约 2-3 分钟）。
- **EC2 替换时短暂不可用**：`user_data_replace_on_change = true` 会销毁旧 EC2 再启新 EC2，期间约 60-120 秒 gateway 不可用。生产环境建议部署多台（需要 FUTU 侧分配多个 ECN IP），多 upstream 在 gateway.py 层做随机 fallback。
- **FUTU 白名单**：gateway 出口 IP = `gateway_private_ip`（dev 无 SNAT）。FUTU 侧防火墙按源 IP 白名单，此 IP 必须事先登记，否则 SG 层通但 FUTU 侧丢包（表现为连接超时，不是 connection refused）。
