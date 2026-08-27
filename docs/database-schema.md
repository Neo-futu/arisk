# ARISK 数据库结构概览

> 更新时间：2026-08-27 北京时间 | 生成模型：Claude Opus 4.8
>
> 本文只做**导航概览**，指向权威源；表结构以下列 SQL / 迁移文件为准，勿在此复述细节。

arisk 使用**单一 PostgreSQL 实例（`fsi_risk` 库）**，两个 schema 共存、互不干扰：

| schema | 管理方式 | 权威源 | 用途 |
|---|---|---|---|
| `iam` | backend Alembic 迁移 | `backend/app/alembic/versions/` + `backend/app/models/` | 身份 / 权限 / 用户 / 菜单 / 角色 |
| `fsi` | SQL 脚本 | `1_datastorage/postgres/schema/*.sql` + `2_processing/sql/*.sql` | 业务数据 + 计算 |

## `fsi` 业务 schema（`1_datastorage/postgres/schema/`，按序初始化）

| 文件 | 领域 |
|---|---|
| `001_schema_init.sql` | schema / 扩展初始化 |
| `002_raw.sql` | 原始落地数据 |
| `003_para.sql` | 参数 / 配置 |
| `004_balance.sql` | 余额 / 头寸 |
| `005_mktdata.sql` | 行情数据 |
| `006_transact.sql` | 交易流水 |
| `007_risk.sql` | 风控指标 |
| `008_workflow.sql` | 工作流 |
| `009_sys.sql` | 系统表 |
| `010_index_counterparty.sql` | 指数 / 交易对手 |
| `011_user_menu.sql` | 用户 / 菜单 |
| `012_risk_rule_configuration.sql` | 风控规则配置 |
| `013_risk_rule_attachments.sql` | 风控规则附件 |
| `014_risk_rule_applications.sql` | 风控规则应用 |
| `015_risk_rule_permissions.sql` | 风控规则权限 |

seed 数据见 `1_datastorage/postgres/seeds/`。

## `fsi` 计算 SQL（`2_processing/sql/`）

WAM/WAL/VaR/久期/杠杆/集中度/归因等 87+ 个 atomic / composite 查询（如
`atomic_portfolio_wam.sql`、`atomic_portfolio_wal.sql`、`atomic_max_drawdown.sql` …）。
计算引擎在 `2_processing/tools/{risk,performance}/`。

## `iam` 权限 schema（backend）

由 `backend/app/alembic/` 管理，模型在 `backend/app/models/`。首次初始化：
`cd backend && alembic upgrade head && python app/initial_data.py`（建超级用户 `admin@fsi.com`）。

## 初始化 / 连接

- 本地初始化：`python scripts/setup_db.py`（建库/用户 + 执行 `schema/*.sql`），再跑 Alembic。
- schema 变更：走 `1_datastorage/postgres/migrations/`（fsi）与 `backend/app/alembic/`（iam），不直接改 schema 文件。
- 本地/云连接双模见 [`aws-deployment.md`](aws-deployment.md) 与 `startup_app_template_derived.md`。
