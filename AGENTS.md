<!-- 更新时间：2026-08-26（北京时间）｜生成模型：Claude Opus 4.8 -->

# AGENTS.md — arisk（派生自 app-template）

> **本仓是平台 golden-path 脚手架 `app-template` 的完整派生应用**：`app_name=arisk` / `repo_pascal=Arisk`。
> **忠实保留 app-template 全套脚手架**（本 `AGENTS.md`、`app/`+`iac/`+`tests/` 的 lambda golden-path 默认形态、`.github/` CI/CD、PR 模板、`templates/` 六形态样例、`.claude/`、`.envrc`、`scripts/protect-main-branch.sh`），以保证后续团队的一致性；**并与 arisk 既有业务代码并存**——真实业务在 `1_datastorage`…`6_entry`、`backend/`、`frontend/`、`aiagent/` 等目录。
> arisk 是多服务应用（frontend + backend + `2_processing` + `6_entry` + agents）；真实部署形态（ECS / 静态前端 / 多形态组合，参考 `templates/monorepo-ecs`）后续单独派生落地。日常迭代**只读 SSM 对接现有基础设施、不碰 infra 实质 IaC 与 ADR**。
>
> **PostgreSQL 本地/云双模**：连库层（`backend/app/core/{config,db,db_auth}.py`、`backend/app/alembic/env.py`）本地默认用静态密码 + localhost；云上设 `POSTGRES_IAM_AUTH=true` 即改用 **RDS IAM token**（连接时自动刷新、`sslmode=require`），**云端不存静态库密码**。变量见 `.env.example`。

以下为 app-template 的脚手架约定，派生仓沿用；协助研发同事在本仓迭代时遵循。

## app ↔ 基础设施的边界（务必遵守）

- **应用运行时架构全部写在应用仓库内**；**不改 infra 的实质 IaC**（`modules/` / `_envs/` 资源定义、部署模板）与 ADR / 设计文档。
- 对接现有云资源**只能读 SSM 派生**（`data "aws_ssm_parameter"`），**不硬编码**账号 ID / ARN / VPC ID / 子网 ID。
- 应用接入所需的**登记 / 清单条目**不在应用仓维护，也不应直接改 `infra` 实质 IaC。当前源入口是 `app-registry/access-surface/apps.yaml`：声明 identity、capabilities、deployment state、ingress、ECR repositories、shared PostgreSQL、FUTU adapters 等低半径接入面字段；由 `app-onboarding` 消费 artifacts 并承接低半径 onboarding apply。`infra/access-surface` 与 shared-middleware tfvars 只作为兼容 snapshot，不是新应用日常入口。
- 新 app 常规上架只应提交 `app-registry` PR（走 CODEOWNERS 评审）。只有新增 capability primitive、修改 IAM policy 正文、改网络 / VPN / TGW / FortiGate / NACL / CA / truststore 分发等高半径底座时，才进入 `infra` 平台评审。

## 平台护栏红线速查（镜像自 infra `docs/for-apps/platform-guardrails.md`，勿就地改）

> 应用仓的 AI 多半读不到 infra 仓，故把少数稳定红线内联于此；**canonical 在 infra**，冲突以 infra 为准。

- **交付**：infra / IaC 变更只经 GitHub Actions + OIDC；本地只做只读 + `tofu plan`，**严禁本地 `tofu apply`**。本地个人凭据按设计**只读**，apply 失败不是凭据问题、**别申请本地写权限**（依据 infra `ADR-0009/0012/0006`）。
- **dev 调试连私网资源（DB / Redis 等）**：人侧授权用 infra `DevDataDebugPermissionSet`，**禁止自建"可被 `AWSReservedSSO_*` assume"的访问角色**；**禁止自建仅用于数据库 / 私网访问的跳板机（bastion）**（用复用应用自身 ECS task / shared-middleware 共享中继）；云端开发机场景见 `infra` `platform-guardrails.md §4`；调试 / 访问类资源 **dev-only 强默认**（`count = var.env == "dev" ? 1 : 0`；staging/prod 方式未定、非必要别在 dev 外启用、要则先与平台确认、勿叠加宽信任）；连库走 **RDS IAM token**、不用静态库密码。正向步骤见下「开发者 dev 数据库调试访问」节，背景见 infra `ADR-0018` / ingress `runbook §10`。

## SSM 对接契约（权威路径，勿臆造）

| 用途 | 路径 |
|---|---|
| 账号 ID | `/landing-zone/accounts/<env>/account_id` |
| VPC | `/infra/bl/<env>/ap-east-1/network/vpc-id` |
| 子网（tier ∈ pub/priv/iso/partner/mgmt/data；Lambda 用 `priv`） | `/infra/bl/<env>/ap-east-1/network/subnet-ids/<tier>` |
| 本应用部署角色 ARN | `/infra/bl/<env>/ap-east-1/platform/role-app-deploy-<RepoPascal>-<EnvPascal>-arn` |
| 集中 ECR registry（仅 `ecs-deploy` / 容器形态需要） | `/infra/bl/<env>/ap-east-1/ecr/registry-url` |
| VPC 内网私有 Hosted Zone ID（内网 DNS 记录用） | `/infra/bl/<env>/ap-east-1/network/phz-id` |
| 共享 R-06 customer ALB :443 listener（挂 listener rule） | `/balance/ingress/external/<env>/alb/listener_443_arn` |
| 共享 R-07 ops ALB :443 listener（ops 入口） | `/balance/ingress/employee/<env>/alb/listener_443_arn` |
| 共享 ALB SG ID（ECS SG 入站放行） | `/balance/ingress/external/<env>/alb/sg_id` |
| 共享入口模式 `cloudfront`/`office`（判断是否走 CloudFront） | `/balance/ingress/external/<env>/alb/sg_mode` |
| CloudFront → ALB origin-verify 头（prod customer） | `/balance/ingress/external/<env>/origin_verify/secret_value` |
| （旧 / 特例：自管公网入口）证书 / TG / ALB SG，由 `dns/app-iac` 写出 | `/app/<app_name>/<svc>/<env>/public-{cert-arn,tg-arn,alb-sg-id}` |

- `<env>` ∈ `dev` / `staging` / `prod`；`<EnvPascal>` ∈ `Development` / `Staging` / `Production`。
- 区域固定 `ap-east-1`（香港）。
- state 后端：桶 `balance-tf-state-<env>-ap-east-1`、锁表 `balance-tf-locks-<env>-ap-east-1`。准确 key / workspace prefix 由 `app-registry` 的 `deployment.state` 声明、经 `app-onboarding/generated/deployment-contracts.json` 消费；默认单应用 key 为 `app/<app-name>/<env>/terraform.tfstate`，monorepo component key 为 `app/<app-name>/<component>/<env>/terraform.tfstate`。
- backend 块不支持变量 → 用 **partial config**（`tofu init -backend-config=backend.<env>.hcl`，该 hcl `.gitignore`，CI 生成）。
- provider `assume_role` 假设 `AppDeployRole-<RepoPascal>-<EnvPascal>`；其 ARN 经 `var.deploy_role_arn` 传入（CI 在 tofu 前从上面 SSM 路径读出注入）。**注意**：provider 的 assume_role 在 SSM data 求值前生效，不能用 data 派生自己要假设的角色。

## 部署形态（可组合，非"三选一"）

下表是**起步脚手架样例**，不是形态白名单或排他规范。**infra 不约束应用内部署形态**：单个应用仓可在同一仓库内自由组合多种形态（如 ECS + Lambda + 静态前端），按需混合。

| 起步形态 | 适用 | 状态 |
|---|---|---|
| `lambda-deploy`（默认起步） | Serverless 函数 / 事件驱动 | 完整实现：根 `app/`+`tests/`+`iac/`+workflows |
| `ecs-deploy` | 长驻容器服务 | 完整实现：`templates/ecs-deploy/`（app/ + iac/ + workflows；共享 ALB R-06/R-07） |
| `monorepo-ecs` | 多服务大仓（共享 RDS + 有序部署编排） | 完整实现：`templates/monorepo-ecs/`（shared/iac + subprojects/svc-a + 7 个 workflows） |
| `static-deploy` | 静态前端（CloudFront + S3） | 完整实现：`templates/static-deploy/iac/` + CI 样板 |
| `dev-server` | 云端共享开发机（dev only） | 完整实现：`templates/dev-server/iac/`（Spot EC2 t3.medium，存储按开发人员数动态调整，EventBridge 工作日自动开关机） |

- 默认从 `lambda-deploy` 起步仅为脚手架便利；需要常驻进程 / 静态站点 / 多形态混合时按需叠加对应 IaC（叠加新形态需先补全其实现）。
- **不得因部署形态差异而拆仓**：一个应用的代码尽量集中在一个仓库；拆仓只由业务 / 领域 / 团队 / 发布节奏驱动，与部署形态无关。
- 接入面对多形态并行供给：本仓的 `AppDeployRole-<RepoPascal>-<EnvPascal>` 权限模板覆盖该仓所需资源并集，ECS 镜像走集中 ECR。决策与边界见 infra `ADR-0019`（应用内部署形态自治）。
- 如果一个仓库内有多个独立部署 component，先在 `app-registry` 声明 `deployment.state.layout: monorepo-components` 与 component 名称 / 路径，再新增对应 workflow；component 名或 state key 形态变更属于 registry contract 变更，不改 `infra` 部署模板。

## 编码前架构准入 checklist

新应用开始编码前、或存量应用新增运行时能力前，AI 必须先向业务同事补齐以下输入；缺失时先问，不要默认给常驻 / 预置容量方案。存量应用没有历史 checklist 不阻断日常发布，但做架构性变更时应补齐。

- **业务与流量**：用途、用户、环境范围、平均 / 峰值 QPS、日 / 月请求量、峰谷规律、增长预期、外部依赖限额。
- **成本**：dev / staging / prod 月成本目标，主要成本来源，低流量 / 不确定流量下的按量、serverless、scale-to-zero 或办公时段启停方案；常驻 / 预置容量需说明业务理由和成本拐点。
- **架构选型**：至少比较一类按量 / serverless 方案与常驻方案；说明何时需要升级架构；新增能力先在 `app-registry` 登记。
- **容量**：并发、worker 数、队列积压、数据库连接、存储增长、日志量、指标量、保留周期和扩容方式。
- **容灾**：prod RTO / RPO、多 AZ 策略、备份恢复、依赖故障降级、单点资源接受理由。
- **环境差异**：dev 是否降配或启停，staging 是否与 prod 同形，prod 与非 prod 在备份、日志、告警、启停上的差异。
- **安全与合规**：敏感数据、客户 / 交易数据、私网访问、mTLS、FUTU adapter、固定出口、IAM 最小权限、审计日志。
- **运行与观测**：核心 SLI/SLO、错误率、延迟、队列积压、数据库连接、成本异常、per-app cost visibility。

## 容器镜像 → 集中 ECR（容器 / ECS 形态必读）

容器形态的镜像**一律推到基础设施预置的集中 ECR（`shared-services` 账号），应用不自建仓库**（部署角色也没有 `ecr:CreateRepository` 权限）。决策与边界见 infra `ADR-0017` / `conventions §10.4`。

- **仓库名**：`app-<app_name>`（小写 `[a-z0-9-]`），由 `app-registry` 的 `ecr.repositories` 声明驱动平台预置，不在应用仓创建。
- **registry 发现**：CI **同账号**读 `/infra/bl/<env>/ap-east-1/ecr/registry-url`（= `<shared-services 账号 ID>.dkr.ecr.ap-east-1.amazonaws.com`）；**不要**跨账号读 shared-services 的 SSM，**不要**硬编码账号 ID。
- **镜像引用**：`<registry-url>/app-<app_name>:<content-hash>`。tag 使用目录内容哈希（`git ls-tree -r HEAD app/ | sha1sum`），代码未变则 tag 不变，IaC 变更不触发无意义重建；`latest` / 浮动 tag 禁用，仓库为 `IMMUTABLE`。monorepo 多子项目场景**必须**用内容哈希（否则任一提交都会触发所有子项目重建）；单服务场景可退化为 commit SHA，但内容哈希仍推荐。
- **跨账号 push**：CI 以 `AppDeployRole-<RepoPascal>-<EnvPascal>` 经 `aws ecr get-login-password` 登录上面的 registry host（跨账号 push 由集中仓库 repository policy 放行）。build/push 样板见 `templates/ecs-deploy/README.md`。
- **运行时 pull**：ECS Task Execution Role 跨账号从同一 registry 拉取（KMS 解密由集中 key policy 放行）。

**上架新容器应用（一次性，app-registry 登记）**：在 `app-registry/access-surface/apps.yaml` 中为本应用声明 `capabilities.compute`（如 `ecs-fargate` 或 `ecs-ec2`）、`deployment.state` 与 `ecr.repositories`。`app-onboarding` 会从 artifact 派生集中 ECR 仓库、部署身份、state backend contract 与兼容 snapshot；应用仓不要自建 ECR 仓库，也不要直接修改 `infra/_envs/shared-services/ecr` 的旧消费清单。

## 开发者 dev 数据库调试访问（应用侧 onboarding）

若你的应用在 **dev** 跑 **ECS 服务 + RDS**、希望开发者调试时能连 dev 库看数据：基础设施侧已就绪——开发者经 SSM 零入口端口转发 + RDS IAM Auth 连库（无需开放入站端口、不发库密码；授权用 IdC `DevDataDebugPermissionSet`）。**应用仓侧只需在自己的 IaC 开启三项**（不碰 infra）：

1. **ECS 服务开 ECS Exec**（让运行中的 task 充当 SSM 转发落点）：
   - `aws_ecs_service` 设 `enable_execute_command = true`；
   - **Task Role**（注意是 task role，非 execution role）加 `ssmmessages` 四动作：`CreateControlChannel` / `CreateDataChannel` / `OpenControlChannel` / `OpenDataChannel`。
2. **RDS 开 IAM 认证**：`aws_db_instance`（或 `aws_rds_cluster`）设 `iam_database_authentication_enabled = true`。
3. **建一个 IAM 数据库用户**（用户名写入 bl-dev DB registry；连库时仍然是固定 DB user，RDS IAM token 只替代 password）：
   - PostgreSQL：`CREATE USER dev_debug;` + `GRANT rds_iam TO dev_debug;` + 按需授库/表权限（dev 可读写）。
   - MySQL：`CREATE USER 'dev_debug'@'%' IDENTIFIED WITH AWS_AUTHENTICATION_PLUGIN AS 'RDS';` + 按需 `GRANT`。
4. **发布 bl-dev DB registry**：应用自有数据库由应用仓在自己的 IaC 写 SSM 参数 `/app/<app>/<env>/bl-dev/databases`，列出本应用开发者可用的 DB target（`name` / endpoint 或 endpointParameter / `database` / `user` / relay）。示例见 `iac/examples/bl-dev-db-registry.tf.example`。若使用共享 PostgreSQL，先在 `app-registry` 声明 `shared_postgres.environments`；`app-onboarding` 承接 per-app provisioning，兼容期的 shared-middleware snapshot 由同步流程维护，应用仓不要重复发布。开发者用 `bl-dev shell <app>` 后执行 `db targets` 查看，用 `db psql --name <target>` 或 `db serve --name <target>` 选择。

**前提核对**：RDS 的 SG 要允许来自 ECS task SG 的库端口入站（应用本来连库就该有）；dev 经 NAT 出网即可，SSM endpoint 非必需（infra 已配）。

**仅 dev**：staging/prod 不走此路径（合规更严，另议）。开发者侧优先使用 `ai-balance/bl-dev`（先 `bl-dev shell <app>`；GUI/反复联调用 `db serve` 或 `db serve --name <target>`；一次性 CLI 用 `db psql`；排障用 `doctor` / `s3 doctor`）。`db serve` 是本地 PostgreSQL 代理，会为每个新上游连接自动生成 RDS IAM token，避免 15 分钟 token 过期打断 GUI 重连。底层命令（实时发现 target → 端口转发 → IAM token）见 infra ingress `runbook §10`，背景见 infra `ADR-0018`；应用仓不要复制粘贴自建联调脚本。

> **纯 Lambda + RDS 应用**（无常驻 ECS task 可作转发落点）：使用 shared-middleware 提供的共享 SSM 中继（`bl-shared-relay-dev`，工作日 08:30–20:30 HKT 自动在线），操作见 shared-middleware `RUNBOOK §3`。**不要在应用仓自建跳板机**。

**dev S3 内容读取**：S3 是 AWS API 数据面，不经 SSM 中继。开发者使用 `bl-dev s3 ls <app>` / `bl-dev s3 doctor <app>` 通过应用 SSM registry 发现 dev bucket；必要时再显式传 `s3://` URI 给 `cp/cat/presign`。默认能力应只读（`ListBucket` / `GetObject*` + 必要 KMS decrypt），不把 S3 读写脚本散落在各应用仓。

## 域名与 DNS

### 内网 DNS（服务间通信）

VPC 内有平台预置的私有 Hosted Zone（PHZ），命名空间为 `<env>.bl.internal`（Zone ID 由 SSM `/infra/bl/<env>/ap-east-1/network/phz-id` 提供）。每个 ECS 服务应在 PHZ 注册一条 A alias record，让消费方通过稳定的内网域名访问，而不是依赖 ALB 的 ephemeral DNS name。

**命名规范**：

| 环境 | 内网域名 | 外网域名 |
|---|---|---|
| prod | `<svc>.bl.internal`（Zone: `bl.internal`） | `<svc>.balancehk.com` / 自定义 |
| staging | `<svc>.staging.bl.internal` | `<svc>.staging.balancehk.com` / 自定义 |
| dev | `<svc>.dev.bl.internal` | `<svc>.dev.balancehk.com` / 自定义 |

> 外网 FQDN 落在 managed domain（`balancehk.com` / `balancehk.ai`）下，由 `app-registry` 的 `ingress.hostnames` 声明（默认 `<app>` / `<app>-ops`，可自定义如 `www`/`api`/`admin.balancehk.ai`）；prod 用裸子域，dev/staging 自动多一层 `<env>`。

**内网 A record 示例（Terraform）**：

```hcl
# data.tf — 读取 PHZ
data "aws_ssm_parameter" "phz_id" {
  name = "/infra/bl/${var.env}/ap-east-1/network/phz-id"
}
data "aws_route53_zone" "phz" {
  zone_id      = nonsensitive(data.aws_ssm_parameter.phz_id.value)
  private_zone = true
}

# route53.tf — 内网 A record（alias 到该服务的内网 ALB）
resource "aws_route53_record" "internal" {
  zone_id = nonsensitive(data.aws_ssm_parameter.phz_id.value)
  name    = var.service_name   # 如 "svc-a"，完整域名由 Zone 后缀自动拼接
  type    = "A"
  alias {
    name                   = aws_lb.internal.dns_name
    zone_id                = aws_lb.internal.zone_id
    evaluate_target_health = true
  }
}
```

完整示例见 `templates/monorepo-ecs/subprojects/svc-a/iac/route53.tf`。

### 公网 / ops 域名（消费平台共享 ALB —— 标准路径）

**managed domain（`balancehk.com` / `balancehk.ai`）的 customer / ops 入口走平台共享 ALB，应用不自建公网 ALB / ACM / Route53。** 平台拥有共享 ALB、wildcard 多 SAN 证书、CloudFront、Route53 hosted zone 与 leaf 记录（依据 infra `ADR-0003` 入口三分 / `ADR-0042` 多根域 / `ADR-0030` hostname ownership 下沉）。参考实现：`echopoc/infra/` 与本仓 `templates/ecs-deploy/`。

1. **声明 FQDN（一次性，在 `app-registry`）**：在 `app-registry/access-surface/apps.yaml` 的 `ingress.hostnames.{customer,ops}` 列出本应用 FQDN（默认 `<app>` / `<app>-ops`，也可自定义如 `www.balancehk.ai` / `api.balancehk.ai` / `admin.balancehk.ai`，声明规则见 app-registry README「Ingress hostname 与 managed domain」）。`app-onboarding` 消费 `artifacts/ingress.json` 在共享入口注册该 hostname 并供给 leaf 记录。**常规新增 / 调整 managed-domain leaf hostname 不需要改 `infra`**（新增第三个根域族 / apex / 证书策略仍属平台高半径）。
2. **应用 IaC 只建 TG + listener rule**：从 SSM 读共享 ALB listener 并挂载，不自建 ALB / cert / Route53：

   | SSM 参数 | 用途 |
   |---|---|
   | `/balance/ingress/external/<env>/alb/listener_443_arn` | R-06 customer 公网 ALB :443 listener（挂 `aws_lb_listener_rule`）|
   | `/balance/ingress/employee/<env>/alb/listener_443_arn` | R-07 ops 办公网 ALB :443 listener（ops 入口挂这里）|
   | `/balance/ingress/external/<env>/alb/sg_id` | ECS service SG 入站放行的共享 ALB SG |
   | `/balance/ingress/external/<env>/alb/sg_mode` | `cloudfront`(prod) / `office`(dev,staging)，据此判断是否走 CloudFront |
   | `/balance/ingress/external/<env>/origin_verify/secret_value` | CloudFront → ALB origin-verify 头（prod customer 链路）|

   listener rule 用 Host header 分流；`alb_listener_rule_priority` 当前由应用填、**接入前与平台确认该 ALB 上的优先级段不冲突**（过渡期人工协调，仅限 priority；cert / DNS / leaf 归属是平台的，不是应用动作）。
3. **内部 ALB 仍可自建**：服务间经 PHZ 访问用自建**内部 ALB**（见上「内网 DNS」）；ECS service 可用两个 `load_balancer` 块——一个挂内部 TG、一个挂共享入口 TG；service SG 入站放行内部 ALB SG 与共享 ALB SG。

### （旧 / 特例）应用自管公网入口（`dns/app-iac`）

`templates/monorepo-ecs/dns/app-iac/` 的「自建 ACM + 专用公网 ALB + Route53 leaf」是**旧 / 特例路径**，仅用于：① 托管 **非 managed domain** 的自定义客户域（managed domain 模型明确拒绝非 managed 域）；② 经平台评审、prod 关键 app 获准脱离共享 ALB 用**专属 ALB**（此时证书 / DNS 仍尽量走平台）。**managed domain（balancehk.com/.ai）的常规 customer/ops 入口不要走这条**，用上面的共享 ALB。

走此路径时，子项目通过 `dns/app-iac/ssm.tf` 写出的 `public-cert-arn` / `public-tg-arn` / `public-alb-sg-id` 接入；ACM 规范、生效时序、首次部署 bootstrap、Route53 UPSERT 去重与同账号 / 跨账号 handoff 见下列各节——这些**仅适用于自管路径**。

### 公网域名生效时序（三环境通用）

**一条域名从创建到 HTTPS 流量可达，需要以下五步严格有序完成：**

```
Step 1  deploy-dns-app（cert/ALB IaC）
        └─ tofu apply → ACM cert 创建（PENDING 状态）
           ALB + TG + SG 创建
           cert-arn / tg-arn / alb-sg-id 写入本环境 SSM

Step 2  读取 cert DVO（domain_validation_options）
        └─ tofu output dns_handoffs → 得到 ACM 验证 CNAME 记录 + 叶子 A alias 记录

Step 3  将 DNS 记录写入 Route53 Hosted Zone
        └─ aws route53 change-resource-record-sets UPSERT
           - ACM 验证 CNAME（去重：同名+类型只写一条）
           - 域名 → ALB 的 A alias record
           ⚠ 若 Hosted Zone 在另一账号（prod），需先 assume cross-account DNS role

Step 4  ACM 自动验证（异步，无需等待）
        └─ AWS 后台轮询 Route53 → 发现 CNAME 记录 → cert 状态 PENDING → ISSUED
           通常 5–10 分钟；此过程 ALB HTTPS listener 已就绪，但 cert 仍 PENDING 时
           新 TLS 连接会收到证书错误（first-time 部署需注意告知用户有延迟）

Step 5  deploy-[service]（ECS IaC）
        └─ 从 SSM 读取 cert-arn / tg-arn → 注入 ALB listener / ECS task def
           ⚠ 此步骤强依赖 Step 1 写入的 SSM 参数，Step 1 未完成则 tofu apply 必 fail
```

### CI job 依赖顺序（禁止并行的地方）

```yaml
# ✅ 正确写法 — service deploy 依赖 dns-app 完成
jobs:
  deploy-dns-app:
    # tofu apply cert/ALB，写 SSM

  deploy-dns-route53:
    needs: deploy-dns-app   # 读取 dns_handoffs output 后写 Route53
    # 可与 deploy-[service] 并行，不阻塞服务部署

  migrate-db:
    needs: deploy-dns-app   # 首部署时需先创建 public TG/SG SSM，再预落地 migration task
    # deploy-dns-app 已依赖 deploy-shared，因此 DB 和公网接入 SSM 都已就绪

  deploy-service:
    needs: [deploy-dns-app, migrate-db]   # ← 两者都要
    # deploy-dns-app 完成后 cert-arn/tg-arn SSM 才存在
    # migrate-db 完成后数据库 schema 才安全
```

**常见错误**：把 `deploy-service` 与 `deploy-dns-app` 并行，导致 `tofu apply` 读 SSM 失败（参数不存在）。这个错误只在**首次部署**时出现，后续迭代 SSM 已有值，问题被掩盖——踩坑后很难追溯。

### 首次部署 Bootstrap checklist

首次为新应用或新环境部署公网域名前，以下条件必须**人工确认**，否则 CI 必 fail：

- [ ] **Hosted Zone 已存在**：外网 Zone 由平台预创建，Zone ID 通过 SSM 可读；私有 PHZ 同理
- [ ] **DNS handoff role 已创建**（若 Hosted Zone 在另一账号）：
  跨账号写 Route53 需要目标账号预创建一个 IAM role，并授权本应用的 deploy role assume
- [ ] **跨账号 role ARN 写入 SSM**：deploy CI 从 SSM 读取该 ARN 后才能 assume；首次部署时 SSM 参数不存在会直接 fail
- [ ] **ALB 命名 ≤ 32 字符**：ALB name 有 32 字符限制，`{app_name}-{service}-{env}` 过长时必须缩写（prod 环境名不带 env 后缀，staging 最长）
- [ ] **cert 验证 CNAME 不重复**：同账号多证书（多子域）可能产生相同 DVO CNAME；Route53 UPSERT 时须按 name+type 去重，否则会报 `InvalidChangeBatch`
- [ ] **告知用户 HTTPS 有延迟**：首次部署后 cert 需 5–10 分钟 ISSUED，期间域名可达但 HTTPS 握手会报证书错误

### Route53 UPSERT 去重（多证书场景）

同一应用多个子域名（如 `api.domain.com` + `www.domain.com`）的 ACM DVO 可能产生相同的验证 CNAME。直接写入会报 `InvalidChangeBatch`，需在 UPSERT 前去重：

```bash
# 按 name+type 去重 ACM 验证记录，按 domain 去重叶子 A 记录
CHANGES=$(echo "$ALL_DNS_HANDOFFS" | jq -c '
  [ .[] ] |
  (
    [ .[].acm_validation[] | {key: (.name + "/" + .type), value: .} ] |
    from_entries | to_entries | map(.value) |
    map({"Action":"UPSERT","ResourceRecordSet":{
      "Name":.name,"Type":.type,"TTL":300,
      "ResourceRecords":[{"Value":.value}]}})
  ) +
  (
    [ .[].leaf_records[] | {key: .domain, value: .} ] |
    from_entries | to_entries | map(.value) |
    map({"Action":"UPSERT","ResourceRecordSet":{
      "Name":.domain,"Type":"A",
      "AliasTarget":{"HostedZoneId":.alb_zone_id,"DNSName":.alb_dns_name,
                     "EvaluateTargetHealth":true}}})
  )
')
aws route53 change-resource-record-sets \
  --hosted-zone-id "$ZONE_ID" \
  --change-batch "{\"Changes\":$CHANGES}"
```

幂等性保证：同内容的 UPSERT 是 no-op，多次运行安全。

### Route53 记录管理：同账号 vs 跨账号

模板 `_deploy-dns-app.yml` 默认按**同账号**实现：用应用自己的 `AppDeployRole` 直接 `route53 change-resource-record-sets` 写入公网 Hosted Zone（zone id 由 Environment 变量 `PUBLIC_HOSTED_ZONE_ID` 提供）。该 role 需具备 `route53:ChangeResourceRecordSets` 权限。

若公网 Hosted Zone 集中托管在**另一账号**（常见：DNS / prod 账号统一持有根域），改用 handoff 模式：

```
dns/app-iac tofu output dns_handoffs   （cert 验证 CNAME + leaf A alias）
  → CI 写入跨账号 SSM /<your-handoff-prefix>/<env>/<svc>
  → assume 目标账号预创建的 DnsHandoffRole（其信任策略授权本应用 deploy role）
  → 在目标账号 route53 change-resource-record-sets UPSERT
```

即把 `_deploy-dns-app.yml` 的「Upsert Route53 records」step 拆成「中继到跨账号 SSM」+「assume role 后跨账号写」两段，role ARN 与 SSM 路径用变量占位。Bootstrap checklist 里「DNS handoff role 已创建 / role ARN 写入 SSM」两项即为此模式的前置条件。

### 静态站点 S3 自建（static-deploy）

**static-deploy S3 自建**：静态站点形态的 S3 桶由**应用 IaC 自建**（infra 提供安全基线）；命名约定 `<app_name>-static-<env>-ap-east-1`；`AppDeployRole` 已按此前缀获得 `s3:*` 权限。dev 桶通过 `aws_ssm_parameter` 发布到 `/app/<app_name>/dev/s3-data-bucket` 供 `bl-dev s3` 自动发现。prod 桶策略锁定共享 CloudFront distribution ARN（OAC 读）；infra 侧需在 `app-registry` 声明 `capabilities.compute: [static-site]` 后由平台控制面完成 OAC + CF S3 origin 注册。完整 IaC 与 CI 样板见 `templates/static-deploy/README.md`。

## 接入 FUTU（需经 VPN 与富途互通时）

应用要经 BL↔FUTU VPN 与富途互通时，通常需在 **FUTU 侧申请一台 ECN 机器部署适配层**。该机器经 FUTU CMDB 申请、由 FUTU 网络运维开通；百仁思侧无需申请人额外动作。

- **新建前置 gate**：先与相关业务确认**无法复用现有适配层、架构上必须独立建设**，再申请——别每业务重复建。
- **申请参数 / 审批 / 申请后开通网络的完整流程**见 infra `bl-futu-interconnect/runbook §7`；此处不复述。
- 适配层与 BL Adapter 之间的 mTLS 证书由 BL step-ca 统一签发与代持（runbook §2），应用侧无需自处理。

### 为什么需要 partner 子网网关（futu-adapter）

`priv` 子网（ECS 服务所在）的路由表**没有**指向 FUTU ECN CIDR 的 TGW 条目，只有 `partner` 子网有。ECS 服务无法直接访问 FUTU，是路由表约束，不是应用侧能解决的——解法是在 `partner` 子网部署一台轻量 EC2 代理。完整 IaC 模板见 `templates/futu-adapter/`。

```
ECS Fargate（priv 子网）
    │  http → gateway_private_ip:listen_port
    ▼
futu-adapter EC2（partner 子网，固定 IP 靠独立 ENI）
    │  http → FUTU ECN IP:port（via TGW，IPsec 隧道提供传输层加密）
    ▼
FUTU ECN
```

### Security Group 两侧都要配（常见踩坑根因）

**gateway SG（`templates/futu-adapter/iac/sg.tf` 管理）：**

| 方向 | 规则 |
|------|------|
| 入站 | consumer ECS task SG → `listen_port`/tcp |
| 出站 | `futu_upstream_cidrs` → `futu_upstream_port`/tcp（仅此，TCP 443 不放行） |

**消费方 ECS SG（消费方自己的 IaC 管理）：**

| 方向 | 规则 |
|------|------|
| 出站 | → gateway SG（或 gateway 固定 IP/32）→ `listen_port`/tcp |

消费方 ECS SG 出站已是 `0.0.0.0/0` 则无需额外配置；出站收紧时必须加此规则，否则 ECS task → gateway 会被 SG 层静默丢包（无报错，表现为请求超时）。

两侧规则均用 `aws_vpc_security_group_*_rule` 资源管理，进 Terraform state，可 `plan` 审计——**不要用 `local-exec` 写 SG 规则**（local-exec 不进 state，失败时静默跳过，`plan` 看不出规则缺失）。

### 消费方接入步骤

1. **在消费方 IaC 中读取 gateway URL**：
   ```hcl
   data "aws_ssm_parameter" "gateway_base_url" {
     name = "/app/${var.app_name}/${var.env}/futu-adapter/gateway-base-url"
   }
   ```
2. **注入 ECS task definition 环境变量**（deploy 时 Terraform 固化，不在容器内动态读取）：
   ```hcl
   { name = "GATEWAY_BASE_URL", value = data.aws_ssm_parameter.gateway_base_url.value }
   ```
3. **检查消费方 SG 出站规则**：确认有 → gateway SG/IP → listen_port 规则（或出站已全放通）。

### 关键约束

- **upstream URL 不能热更新**：partner SG 阻断 TCP 443，gateway 无法在运行时访问 SSM。upstream 变更必须重新 `tofu apply` 触发 EC2 替换（ENI 不销毁，IP 不变，约 60-120 秒不可用）。
- **FUTU 白名单**：gateway 出口 IP = `gateway_private_ip`（dev 无 SNAT，源 IP 就是私网 IP）。FUTU 侧按源 IP 白名单，SG 层通但 FUTU 白名单未登记时表现为请求超时而非 connection refused。
- **连接失败排查**：先 `aws ec2 get-console-output` 看启动自检，再检查双侧 SG 规则，最后确认 FUTU 白名单——详见 `templates/futu-adapter/README.md §诊断 checklist`。

## 自管告警与定时（可观测性）

应用部署角色（`ecs-deploy` / `web-lambda-ecs-deploy` / `lambda-web-deploy` 模板的 `AppDeployRole-<RepoPascal>-<EnvPascal>`）已携带可观测性自管权限：**应用可在自己的 IaC 里创建 / 管理本工作负载的 CloudWatch 告警与 classic EventBridge 规则**，无需平台代建，减轻 observability 集中负担。

- **告警**：`aws_cloudwatch_metric_alarm` 自建本应用的基础告警（DB 存储逼近上限、ECS 任务异常、Lambda 错误率 / 时延等）。告警投递到平台 `alarm-p1-<env>` 等 SNS topic（topic 经 SSM 发现）。
- **定时触发**：用 **classic EventBridge**（`aws_cloudwatch_event_rule` + `aws_cloudwatch_event_target`）定时拉起 Lambda / 跑巡检。**不是 EventBridge Scheduler**——`scheduler:*` 当前仍限平台预置范围（`schedule/default/echopoc-*`），未对一般 app 放开，别用 `aws_scheduler_schedule`。
- **边界**：按 `<app>-<env>-*` 命名前缀收敛 resource，遵循最小权限；权限正文、resource 前缀与 alarm topic 发现路径以 infra 为权威，见 infra `docs/for-apps/platform-guardrails.md` 与 platform-iam 域 `app-observability-deploy` 段。能力随部署模板提供，`app-registry` 侧无需额外字段（`scheduled-job` 原语仍用于表达定时接入意图）。

## 改代码时的约定

- **handler**：`app/handler.py` 导出 `handler(event, context)`，从环境变量 `APP_NAME`/`ENV` 取上下文（在调用时读，便于测试覆写）。新增依赖时建 `app/requirements.txt`。
- **测试**：所有改动都要在 `tests/` 有对应 pytest 覆盖；`ci.yml` 在 PR 阶段跑 `pytest tests/ -q`，是合入门槛。fixtures/测试事件放 `tests/data/`。
- **IaC**：资源名/标签统一用 `app_name`+`env`；执行角色保持 scoped（最小权限）；接入真实环境时给 lambda exec role 挂基础设施发布的 PermissionsBoundary（防提权，见 `iac/main.tf` 注释）。Lambda 默认不进 VPC，需访问私网资源时按 `iac/data.tf` 注释启用 `priv` 子网 + `vpc_config` + ENI 权限。
- 改完跑 `tofu fmt` + `tofu validate -backend=false` + `pytest`。

## ECS IaC 反模式（禁用）

### `lifecycle { ignore_changes = [task_definition] }` — 严禁

```hcl
# ❌ 禁止
resource "aws_ecs_service" "app" {
  lifecycle { ignore_changes = [task_definition] }
}
```

此配置导致 `tofu apply` 后 ECS service 不更新 task definition，`--force-new-deployment` 拉起的是已注销版本，应用实际未部署。表现为 tofu 计划无变化、CI 绿灯、但线上仍是旧版本。**永远不要加这行。**

### ECS Exec 仅限 dev — 禁止在 staging/prod 开启

```hcl
# ✅ dev-only 正确写法
resource "aws_ecs_service" "app" {
  enable_execute_command = var.env == "dev"
}

# task role — ssmmessages 权限也仅 dev 需要
resource "aws_iam_role_policy" "ecs_exec" {
  count = var.env == "dev" ? 1 : 0
  # ...
}
```

`enable_execute_command = true` 要求 task role 持有 `ssmmessages:*`，扩大了运行时 task role 的攻击面。dev 调试用途可开，staging/prod 不开。

## 数据库角色分离（有 DB 的 ECS 应用必读）

应用连接数据库时，**migration 身份、运行时身份、只读身份必须分离**：

| 角色 | 权限 | 使用方 |
|---|---|---|
| `<svc>_db_owner` | `CREATEDB` + DB owner（可执行 DDL） | 仅 CI migration job（独立 ECS task role）|
| `<svc>_app_rw` | `NOCREATEDB`，无 DDL 权限 | 运行时 ECS service（task role）|
| `<svc>_ro` | 仅 `SELECT`（含 `ALTER DEFAULT PRIVILEGES` 覆盖新表） | 分析 / BI / 排障只读访问 |

三个角色均用 **RDS IAM 认证**（`rds_iam` grant + `rds-db:connect` IAM 权限），不存静态 DB 密码。Master 密码仅在初始化 role / database 时（IaC `null_resource`，Fargate psql 任务）通过 ECS secret 注入，之后封存。shared 初始化脚本负责幂等创建业务库并授予基础权限；migration 只负责业务 schema，不负责 bootstrap database。

完整实现参考 `templates/monorepo-ecs/`（`shared/iac/db_roles.tf` + `subprojects/svc-a/iac/iam.tf`，每个子项目两套 task role：运行时 `task` 连 `app_rw`、migration `db_owner_task` 连 `db_owner`）。

## 数据库 Migration 规范（有 DB 的 ECS 应用必读）

**migration 必须独立于主服务部署**，不得在主服务容器启动时顺带跑（禁止 `ENTRYPOINT`/`CMD` 调 `init_db`）。每个有库的子项目用专属 `migrate-<svc>-db` job 执行（实现见 `_deploy-ecs-db-migrate.yml`）。

- **顺序（强制）**：`deploy-shared → deploy-dns-app → migrate-<svc>-db → deploy-<svc>`。`deploy-dns-app` 先写出 public TG/SG SSM，migration job 再只预落地 migration task 必需的 ECS/IAM/SG 资源，用 DB owner task role 跑 Fargate migration；`deploy-<svc>` 的 `needs` 必须含 `migrate-<svc>-db`，`migrate` 的 `needs` 不得含 `deploy`。无 pending migration 时 migrate job 跳过，deploy 仍正常执行。
- **只读预检（必须）**：migrate job 正式执行前先以 `--check` 启动一次（`--overrides` 复用同一 task def），查 `schema_migrations`：无 pending → `exit 0` → 跳过 migration task；有 pending → 执行。`--check` 须只读、不建表、不持 advisory lock。
- **停服策略**：

  | 服务类型 | 停服 | 原因 |
  |---|---|---|
  | HTTP REST API | 否 | 短事务；migration 只做向后兼容变更 |
  | 持续写入型（scheduler / consumer / 批量写入） | 是，migration 前停、完成后恢复 | 并发写入与 schema 变更会导致数据错误 |

  停服用 `aws ecs update-service --desired-count 0` + `wait services-stable`，恢复步骤须 `if: always()`，防止服务永久停在 0 实例。

## 发布

feature 分支 → PR + CI 通过 → 合入 → 打 `v*` tag → `deploy.yml` 逐环境 dev → staging → prod（prod 走 `production-app` Environment 审批）。
