# ARISK AWS 部署指引（藍圖 · 上線階段落地）

> 更新时间：2026-08-27 北京时间 | 生成模型：Claude Opus 4.8
>
> 本文是 arisk 上雲的**藍圖**，參照已上線派生應用 `ideclare` 的 ECS 派生架構，
> 但 **arisk 使用自有庫和自有服務，不消費平台共享 Aurora**。
> **當前階段專注本地業務開發與 PostgreSQL 本地/雲雙模驗證**；下列 iac / workflows
> 尚未落地，屬正式上線部署階段的工作。本地啟動見 `startup_app_template_derived.md`。

## 目標架構（單 ECS 任務 = frontend + 統一 backend）

對齊 ideclare 的「單任務雙容器」，但把 arisk 的多服務**整合進一個 backend 進程**
（見 `backend/app/unified.py`：`/processing`、`/entry`、`/mcp`、`/autorisk` 子應用掛載）：

```
共享 external ALB (:443)
  → host: arisk[.<env>].balancehk.com
  → ECS Fargate 單任務：
       ├─ frontend 容器（nginx :80，SPA + /api 反代 backend:8000）
       └─ backend  容器（統一 FastAPI :8000，掛載 processing/entry/mcp/autorisk）
  → arisk 自有 RDS PostgreSQL（IAM 認證；非共享 Aurora）
  → Redis / TimescaleDB / S3（arisk 自有）
```

> Celery worker、TimescaleDB 等的雲上形態於上線階段細化。

## 待落地清單（上線階段，參照 ideclare 但用自有庫）

1. **自有 RDS**：參照 `app-template/templates/monorepo-ecs/shared/iac/{postgres.tf,db_roles.tf}`
   為 arisk 自建 RDS（`aws_db_instance`，`iam_database_authentication_enabled=true`）
   + 三角色分離 `arisk_db_owner`/`arisk_app_rw`/`arisk_ro`。**不使用共享 Aurora。**
2. **iac/（ECS）**：參照 `ideclare/iac/*.tf` 落 `provider/data/locals/variables/ecs/alb/iam/secrets/s3/cloudwatch/sg/dev-server/outputs.tf` + `backend/{dev,staging,prod}.hcl`；
   `data.tf` 讀 arisk 自有 RDS 的 SSM（而非 `shared-postgres`）。
3. **鏡像**：`app-arisk-backend`、`app-arisk-frontend`，推集中 ECR（`/infra/bl/<env>/ap-east-1/ecr/registry-url`）。
4. **Secrets Manager**：`arisk/<env>/app`（JWT、LLM API keys、Wind 憑證等）。
5. **S3**：`arisk-docs-<env>-ap-east-1`（KMS + 版本 + 生命週期 + CORS + `/app/arisk/<env>/s3-data-bucket` 註冊）。
6. **.github/workflows（ECS 版）**：參照 `ideclare/.github/workflows/*` 落
   `deploy.yml`（push main→dev 自動、dispatch→staging/prod；build/push 雙鏡像 + `tofu apply`）、
   `ci.yml`（docker build + `tofu init -backend=false`+`validate`+`fmt`）、
   `migrate-db.yml`、`seed-secrets.yml`、`dev-server.yml`、`diag-ecs-logs.yml`、`gen-presigned-url.yml`。
7. **repo Variables / Environments**：`AWS_ROLE_ARN`、`DEV_SERVER_SSH_PUBLIC_KEY`；
   `development`/`staging`/`production-app`（prod 需審批）。
8. **app-registry 登記**：在 `app-registry/access-surface/apps.yaml` 聲明 arisk 的
   identity / capabilities(compute: ecs-fargate) / deployment.state / ingress / ecr.repositories。

## DB 連接契約（本地/雲雙模，已實現）

連庫層 `backend/app/core/{config,db,db_auth}.py` + `alembic/env.py` 已支持雙模：

| 環境 | 連接方式 |
|---|---|
| 本地 | `POSTGRES_SERVER=localhost` + 靜態 `POSTGRES_PASSWORD`（`POSTGRES_IAM_AUTH=false`） |
| AWS（自有 RDS） | `POSTGRES_SERVER=<arisk-rds-endpoint>`、`POSTGRES_USER=arisk_app_rw`、`POSTGRES_PASSWORD=` 留空、`POSTGRES_IAM_AUTH=true`、`POSTGRES_SSLMODE=require`（連接時生成 RDS IAM token） |

> 上線階段可按需將命名對齊 ideclare 的 `DB_*`；當前保留 `POSTGRES_*` 以兼容
> `1_datastorage` / `2_processing` / `aiagent` 各層。變量見 `.env.example`。

## 遷移

舊業務庫 → arisk 自有 RDS：見 `scripts/migrate-db.sh`（dump/restore + `alembic upgrade head`）。
dev 聯調雲庫：`scripts/bl-dev.sh`（`bl-dev shell arisk`）。
