# ecs-deploy（长驻容器形态）

长驻容器服务形态：ECS（Fargate）服务 + 共享 ALB listener rule，经 OpenTofu 部署到 dev/staging/prod。对接基础设施的约定与 `lambda-deploy` 一致（只读 SSM 派生、partial backend、OIDC 假设 `AppDeployRole`）。

适用：需要常驻进程、自定义运行时、长连接或较重并发的服务。

## 目录结构

```
app/          — 示例容器应用（FastAPI，可替换为任意运行时）
iac/          — OpenTofu：ECS Fargate + 共享 ALB target group/rule + IAM roles
.github/
  workflows/
    ci.yml              — PR 门控（Docker build smoke test）
    deploy.yml          — v* tag 触发，dev → staging → prod
    _deploy-ecs-env.yml — 可复用：OIDC + build/push ECR + tofu apply + ECS update
```

## 镜像走集中 ECR（不自建仓库）

镜像一律推到基础设施预置的集中 ECR（`shared-services` 账号）；部署角色已含跨账号 push 权限。
仓库名 `app-<app_name>`，在 `app-registry` 的 `ecr.repositories` 声明驱动预置。
registry 从 SSM `/infra/bl/<env>/ap-east-1/ecr/registry-url` 读取，不硬编码账号 ID。
详见根 `AGENTS.md` §「容器镜像 → 集中 ECR」与 infra `ADR-0017`。

## ALB 接入（消费平台共享 ALB）

本模板挂载到 infra ingress 域管理的平台共享 ALB，**平台拥有 ALB / 证书 / CloudFront / Route53 leaf，应用不自建公网 ALB / ACM / DNS**（依据 infra `ADR-0003` / `ADR-0042` / `ADR-0030`）：

- 应用只创建 `aws_lb_target_group` + `aws_lb_listener_rule`，不自建 ALB / cert / Route53。
- **lane → listener**：customer（R-06 公网）读 `/balance/ingress/external/<env>/alb/listener_443_arn`；ops（R-07 办公网）读 `/balance/ingress/employee/<env>/alb/listener_443_arn`。本骨架默认接 R-06 customer；ops 入口按同样方式挂 employee listener（参考 `echopoc/infra/alb_ops.tf`）。
- ALB SG ID 读 `/balance/ingress/external/<env>/alb/sg_id`（ECS service SG 入站放行）；`sg_mode` 读同前缀 `.../sg_mode`（prod=cloudfront、dev/staging=office）；prod customer 链路的 CloudFront origin-verify 头读 `.../origin_verify/secret_value`。
- **FQDN 在 `app-registry` 声明**：`ingress.hostnames.{customer,ops}` 列出本应用 FQDN（默认 `<app>` / `<app>-ops`，可自定义如 `www`/`api`/`admin.balancehk.ai`）；`app-onboarding` 在共享入口注册并供给 leaf 记录。**常规新增 / 调整 managed-domain hostname 不需要改 `infra`。**
- `alb_listener_rule_priority` 当前由应用填，**接入前与平台确认该共享 ALB 上的优先级段不冲突**（过渡期人工协调，仅限 priority；证书 / DNS / leaf 归属是平台的）。

## 快速起步

1. **app-registry 登记**（一次性）：在 `app-registry/access-surface/apps.yaml` 中声明
   `capabilities.compute: ecs-fargate`、`ecr.repositories`、`deployment.state` 与 `capabilities.ingress` lanes。
   `app-onboarding` 承接 ECR 预置、AppDeployRole、state backend contract 与 ingress 注册。

2. **替换应用代码**：`app/` 换成真实业务代码；保留 `/health` endpoint（ALB 健康检查）。

3. **配置变量**：部署前确认 `iac/variables.tf` 中 `app_name`、`alb_listener_rule_priority`（找基础设施确认不冲突）。`enable_container_insights=null` 时仅 prod 开启容器粒度付费指标；有明确 SLO、告警或排障依赖时再按环境显式覆盖。

4. **GitHub 仓库变量**（各 Environment 级）：`APP_NAME`、`REPO_PASCAL`、`AWS_ACCOUNT_ID`、`AWS_REGION`（可选，默认 `ap-east-1`）。

5. **打 tag 发布**：`git tag v0.1.0 && git push --tags`，`deploy.yml` 自动 dev → staging → prod（prod 走 `production-app` Environment 审批）。

## dev 数据库调试访问

需要连 dev 库时，在 ECS service 开启 `enable_execute_command = true`、task role 加 `ssmmessages` 四动作，详见根 `AGENTS.md` §「开发者 dev 数据库调试访问」。
