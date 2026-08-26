# monorepo-ecs（多服务大仓形态）

多个 ECS Fargate 服务共享一套 RDS 实例，统一发布编排，严格分离 migration 权限与运行时权限。

适用：同一业务域的多个后端服务，共享数据层，希望在同一仓库内统一管理发布顺序和基础设施生命周期。

## 目录结构

```
shared/
  iac/                  — 共享基础设施（RDS + DB roles + SSM 输出），独立 tofu state
dns/
  app-iac/              — （旧 / 特例）自管公网入口（ACM + 专用公网 ALB + TG），独立 tofu state；managed domain 默认走平台共享 ALB，见 §2.5
subprojects/
  svc-a/                — 骨架子项目（复制此目录添加新服务）
    app/                — 应用代码（Dockerfile + entrypoint.sh + main.py）
    iac/                — ECS Fargate + 内部 ALB（PHZ）+ 公网 TG 接入 + IAM roles（两套 task role）
.github/workflows/
  _deploy-shared-env.yml      — 可复用：shared/iac tofu apply
  _deploy-dns-app.yml         — 可复用：dns/app-iac tofu apply + Route53 UPSERT
  _deploy-ecs-env.yml         — 可复用：子项目 build/push/deploy（内容哈希 tag）
  _deploy-ecs-db-migrate.yml  — 可复用：DB migration（owner role，预检+停服可选）
  deploy-dev.yml              — dev push → 路径检测 → 有序按需部署
  deploy-all.yml              — staging push / v* tag → 全量部署
  sync-dev-to-main.yml        — dev 全绿 → 自动 ff merge 到 main
  validate-pr-source.yml      — 分支线性保护（staging←main，prod←staging）
  lint-deploy-workflows.yml   — 新子项目漏更新编排 workflow 时 CI 报红
```

## 核心设计

### 1. 部署顺序

```
shared/iac → dns-app → migrate-<subproject> → deploy-<subproject>
```

shared 先于所有子项目；公网入口（dns/app-iac）先于子项目部署（子项目要从 SSM 读 public-tg-arn）；migration 先于服务启动。顺序由 workflow `needs` 约束，CI 强制。

### 2. DB 角色分离（IAM 层隔离）

每个子项目运行时与 migration 用两套 task role，外加一个只读角色：

| Role | PostgreSQL role | `rds-db:connect` 权限 | 使用方 |
|---|---|---|---|
| `*-task` | `svc_a_app_rw`（无 DDL） | 只能连 `svc_a_app_rw` | 运行时 ECS service |
| `*-db-owner-task` | `svc_a_db_owner`（有 DDL） | 只能连 `svc_a_db_owner` | CI migration job |
| （按需，分析/BI） | `svc_a_ro`（仅 SELECT） | — | 只读访问 |

运行时即使代码被注入 DDL 语句，IAM 层就会拒绝，不会到 PostgreSQL 鉴权层。`svc_a_ro` 只读角色在 `shared/iac/db_roles.tf` 一并创建（表级 SELECT + `ALTER DEFAULT PRIVILEGES`）。Master 密码仅在 `db_roles.tf` 初始化时使用，初始化后封存于 Secrets Manager。

### 2.5 公网入口：默认走平台共享 ALB；dns/app-iac 自管为旧 / 特例

**managed domain（`balancehk.com` / `balancehk.ai`）的 customer/ops 入口默认消费平台共享 ALB**（在 `app-registry` 声明 `ingress.hostnames`，应用 IaC 只建 TG + listener rule 读 `/balance/ingress/{external,employee}/<env>/alb/...`，平台拥有 cert / Route53 / CloudFront）。参考 `echopoc/infra/` 与 `templates/ecs-deploy/`，背景见根 `AGENTS.md` §「公网 / ops 域名（消费平台共享 ALB）」与 infra `ADR-0003`/`ADR-0042`/`ADR-0030`。

本目录的 `dns/app-iac/`（自建 ACM + 专用公网 ALB + Route53 leaf）是**旧 / 特例路径**，仅用于：① 非 managed domain 的自定义客户域；② 经平台评审获准用专属 ALB 的 prod 关键 app。**起常规新应用不要默认带它**——若不需要自管公网入口，删除 `dns/` 目录与 `_deploy-dns-app.yml`，按上面共享 ALB 方式接入。走自管路径时：ACM/TG/SG 在 `dns/app-iac/` 用 `for_each` 统一管理，子项目读 `public-cert/tg/sg` SSM 接入，Route53 由 `_deploy-dns-app.yml` UPSERT（同账号；跨账号 handoff 见 AGENTS.md）。

### 3. 内容哈希镜像 tag

```bash
git ls-tree -r HEAD subprojects/svc-a/app/ | sha1sum | cut -c1-40
```

每个子项目独立计算内容哈希。代码未变则 tag 不变，跳过 docker build 和 ECS 重启。任何子项目的提交不会触发其他子项目的重建。

### 4. 分支策略

```
dev → (全绿后自动 ff merge) → main → (PR) → staging → (PR) → prod tag
```

开发者只推送到 `dev`。CI 负责 `dev → main` 的同步。`validate-pr-source` 拦截非合规 PR 来源。

## 快速起步

### 1. app-registry 登记（一次性）

在 `app-registry/access-surface/apps.yaml` 声明：
- `capabilities.compute: ecs-fargate`
- `deployment.state.layout: monorepo-components`
- `deployment.state.components: [shared, dns-app, svc-a]`
- `ecr.repositories: [app-<app_name>-svc-a]`

### 2. 替换 svc-a 应用代码

`subprojects/svc-a/app/` 目录换成真实业务代码，保留 `/health` endpoint（ALB 健康检查）。

### 3. 配置 IaC 变量

- `shared/iac/variables.tf`：确认 `rds_instance_class`、`postgres_version`
- `dns/app-iac/services.tf`：确认 service 的 `alb_base`（≤32 字符）、`cert_domain`、`app_port`
- `subprojects/svc-a/iac/variables.tf`：确认 `service_name`（须与 dns/app-iac service key 一致）；`enable_container_insights=null` 时仅 prod 开启容器粒度付费指标，有明确 SLO、告警或排障依赖时再按环境显式覆盖

### 4. GitHub 仓库变量（各 Environment 级）

`APP_NAME`、`REPO_PASCAL`、`AWS_ACCOUNT_ID`、`DOMAIN`、`PUBLIC_HOSTED_ZONE_ID`、`AWS_REGION`（可选）

> 仅内网服务（无公网域名）时 `DOMAIN`/`PUBLIC_HOSTED_ZONE_ID` 可留空，dns/app-iac 的 Route53 写入会跳过。

### 5. 第一次部署

```bash
git push origin dev   # 触发 deploy-dev.yml：shared → dns-app → migrate → svc-a
```

shared/iac 会创建 RDS 并初始化 DB roles（Fargate psql 任务，约 1-2 分钟）。首次部署后 ACM 证书需 5–10 分钟 ISSUED，期间域名可达但 HTTPS 握手报证书错误（见 AGENTS.md「公网域名生效时序」）。

## 新增子项目

1. 复制 `subprojects/svc-a/` 目录，重命名（如 `svc-b`）
2. 在 `shared/iac/db_roles.tf` 的 `subproject_names` 列表加入新名称（下划线）
3. 若需公网域名：在 `dns/app-iac/services.tf` 的 `local.services` 加一条 service
4. 在 `deploy-dev.yml` 和 `deploy-all.yml` 加入新子项目的 migrate + deploy job（并串好 `deploy-dns-app` 依赖）
5. 在 `app-registry` 补充新的 ECR repository 和 component

步骤 4 遗漏时，`lint-deploy-workflows.yml` 会在 PR 阶段报红。

## entrypoint.sh 配置生成模式

`subprojects/svc-a/app/entrypoint.sh` 在容器启动时从环境变量生成 `config.yaml`。
优点：镜像内无明文配置，本地可直接 `cat config.yaml` 查看生成结果，调试方便；同时保持 12-factor 原则（配置来自环境变量）。
