# ARISK 数据库结构概览

> 更新时间：2026-09-29 北京时间 | 生成模型：Grok 4.7
>
> 本文只做**导航概览**，指向权威源；表结构以下列 SQL / 迁移文件为准，勿在此复述细节。

arisk 使用**单一 PostgreSQL 实例（`fsi_risk` 库）**，两个 schema 共存、互不干扰：

| schema | 管理方式 | 权威源 | 用途 |
|---|---|---|---|
| `iam` | backend Alembic 迁移 | `backend/app/alembic/versions/` + `backend/app/models/` | 身份 / 权限 / 用户 / 菜单 / 角色 |
| `fsi` | SQL 脚本 | `1_datastorage/postgres/schema/*.sql` + `2_processing/sql/{indicators,mmf}/*.sql` | 业务数据 + 计算 |

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
| `016_data_management_workbench.sql` | 模拟交易、前置风控结果与数据管理审计闭环 |
| `018_risk_metric_extensions.sql` | 投资者 sponsor、发行人舆情、关联方 |
| `019_am_category_tables.sql` | 固收信用、停牌、保护条款、权益风格、发行人主体 |
| `020_portfolio_benchmark.sql` | 组合基准关联、恒生指数行情、跟踪误差控制线 |
| `021_risk_metric_report.sql` | 六大类风控指标报表：看板头与分项指标 |

seed 数据见 `1_datastorage/postgres/seeds/`。

## `fsi` 计算 SQL（`2_processing/sql/{indicators,mmf}/`）

WAM/WAL/VaR/久期/杠杆/集中度/归因等 atomic / composite 查询沉淀在
`2_processing/sql/indicators/`（非 mmf 风控指标，如 `atomic_portfolio_wam.sql`、
`brinson_asset_class.sql` …），mmf 报表 SQL 在 `2_processing/sql/mmf/`，二者平行。
这些 SQL 作为**资产**经 `/api/v1/fsi/sql-assets/*` 提供目录/正文/AI 上下文（查看与
参考用途，非执行器）。计算引擎在 `2_processing/tools/{risk,performance}/`。

## `iam` 权限 schema（backend）

由 `backend/app/alembic/` 管理，模型在 `backend/app/models/`。首次初始化：
`cd backend && alembic upgrade head && python app/initial_data.py`（建超级用户 `admin@fsi.com`）。

数据管理中心由 `iam.menu` 的 `/data-management` 开关控制。持仓写入沿用
`portfolio.manage` 与组合级 `MANAGE` 授权，模拟交易沿用 `trade.manage` 与组合级
`MANAGE` 授权；共享行情写入要求 `market_data.manage`。读取仍受登录认证和组合查看权限约束。
组合主数据 `fsi.para_portfolio` 也可在此 CRUD（新建/编辑/停用/删除），写入要求全局
`portfolio.admin`（授予 SYSTEM_ADMIN，超管绕过）；删除带依赖守卫（有 NAV/估值/模拟单则拒删、改用停用）。

**组合优化（PyPortfolioOpt）**：`2_processing/tools/performance/portfolio_optimizer.py`（有效前沿/Black-Litterman/HRP + CML 切点，
数据源 synthetic/db/yfinance）+ 路由 `portfolio_opt.py`；后端代理 `/api/v1/fsi/portfolio-opt/*`（analyze/evaluate/universe/
portfolios/holdings/risk-free-options/chart PNG，登录即可）。**对接平台组合**：`holdings/{port_id}` 从 `balance_bond/stock/cd/deposit`
取证券级持仓作为 universe+用户权重；RF 预设取自 `mktdata_indicator_series`（US_FEDRATE/HK_HIBOR3M/CN_LPR1Y）。菜单 `/portfolio-opt`
以 `BETA` 灰度上线。依赖见 `2_processing/requirements.txt`（PyPortfolioOpt/yfinance）。

**组合列表与驾驶舱（Module 2.1）**：纯计算/展示，复用 `fsi.para_portfolio`（组合主数据/类型/MMF 限额）
+ `fsi.balance_portfolio_nav`/`balance_portfolio_mmf`（NAV 与 MMF 指标）。计算层
`2_processing/api/routers/portfolio_cockpit.py`，后端代理 `/api/v1/fsi/portfolio-cockpit/*`（只读，
`portfolio.view` 组合级授权）。菜单 `/portfolio-cockpit` 以 `BETA` 灰度上线，与现有 `/` 风控仪表板并存。

**组合估值与损益（Module 4）**：纯计算/报表模块，复用 `fsi.balance_valuation_sheet`（科目级估值，可算未实现损益）
与 `fsi.balance_portfolio_nav`（每日 NAV 历史）。计算层 `2_processing/api/routers/valuation.py`（`/report`、`/pnl`），
后端代理 `/api/v1/fsi/valuation/*`（只读，`portfolio.view` 组合级授权）。菜单 `/valuation` 以 `BETA` 灰度上线。无新表。

**指标探索引擎（DataJungle）**：`fsi.mktdata_indicator_def`（指标目录）+ `fsi.mktdata_indicator_series`
（long-format 时序观测，可界面增删改并直连底层表）承载「选指标/国家/周期/数据源 → 对比折线 + CSV 导出」。
schema 见 `1_datastorage/postgres/schema/017_indicator_explorer.sql`（含示例种子）；计算层
`2_processing/api/routers/indicators.py`，后端代理 `/api/v1/fsi/indicator-explorer/*`（读=登录、写=`market_data.manage`）。
菜单 `/indicator-explorer` 以 `BETA` 灰度上线。

**灰度上线（模块菜单显隐）**：`iam.menu.release_stage`（`GA`/`BETA`/`HIDDEN`）在 per-role
`role_menu` 授权之上再叠加一层发布阶段——`GA` 对已授权用户可见；`BETA` 仅超级管理员预览
（普通用户即使有授权也看不到）；`HIDDEN` 对所有人隐藏。管理入口为「系统配置」页
（`/system-config`，权限 `system.config.manage`），API 在 `access-control/menu-releases`。
`system-config` 菜单自身禁止置 `HIDDEN`/停用，防止管理员自锁。

## 初始化 / 连接

- 本地初始化：`python scripts/setup_db.py`（建库/用户 + 执行 `schema/*.sql`），再跑 Alembic。
- schema 变更：走 `1_datastorage/postgres/migrations/`（fsi）与 `backend/app/alembic/`（iam），不直接改 schema 文件。
- 本地/云连接双模见 [`aws-deployment.md`](aws-deployment.md) 与 `startup_app_template_derived.md`。
