<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# arisk 平台主要文件目录树（Current）

本文档整理**当前仓库实际存在**的主干目录树，侧重平台主干结构，不展开缓存目录、构建产物或零散临时文件。目标架构见 [`target_platform_directory_tree.md`](target_platform_directory_tree.md)；迁移映射见 [`architecture_migration_map.md`](architecture_migration_map.md)。

## 一、仓库主目录树

```text
arisk/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── PROJECT_OVERVIEW.md
├── pyproject.toml
├── .env.example
├── 1_datastorage/
│   ├── docker-compose.yml
│   ├── moduleinfo.md
│   ├── object_store/
│   ├── postgres/
│   ├── redis/
│   └── timeseries/
├── 2_processing/
│   ├── moduleinfo.md
│   ├── requirements.txt
│   ├── api/
│   ├── compatibility/          # Wave 2：Processing 内兼容 Facade（skeleton）
│   ├── etl/
│   ├── logging/
│   ├── review/
│   ├── sql/
│   ├── test/
│   ├── tools/                  # 当前计算权威；逐步桥接至 3_riskengine
│   └── workers/
├── 3_riskengine/               # Wave 2：RiskEngine skeleton（算法尚未迁入）
│   ├── moduleinfo.md
│   ├── core/
│   ├── adapters/
│   ├── valuation/
│   ├── instruments/
│   ├── market/
│   ├── risk/
│   ├── stress/
│   ├── scenario/
│   ├── liquidity/
│   ├── counterparty/
│   ├── pnl/
│   ├── limits/
│   ├── validation/
│   └── tests/
├── 3_skills/                   # 运行时权威；目标迁移至 7_ai/skills
├── 4_business/                 # 业务用例层
│   ├── moduleinfo.md
│   ├── investment_risk/        # Wave 4：投资风险分析 + KPI
│   │   ├── overview/
│   │   ├── exposure/
│   │   ├── market_risk/
│   │   ├── factor_risk/
│   │   ├── rates_credit/
│   │   ├── fx/
│   │   ├── liquidity/
│   │   ├── concentration/
│   │   ├── counterparty/
│   │   ├── leverage/
│   │   ├── pnl_attribution/
│   │   ├── risk_budget/
│   │   ├── macro_dynamics/
│   │   └── factor_behavior/
│   ├── portfolio_optimization/ # Wave 5：Riskfolio 优化 + 仿真仓 + 过闸
│   │   ├── construction/
│   │   ├── saa/
│   │   ├── taa/
│   │   ├── risk_budget/
│   │   ├── risk_parity/
│   │   ├── black_litterman/
│   │   ├── hrp/
│   │   ├── herc/
│   │   ├── cvar/
│   │   ├── constraints/
│   │   ├── liquidity/
│   │   ├── turnover/
│   │   ├── simulation/
│   │   └── validation/
│   ├── risk_testing/
│   ├── risk_governance/        # Wave 6：政策 / 限额 / 违约 / 审批 / 审计
│   │   ├── policy/
│   │   ├── appetite/
│   │   ├── limits/
│   │   ├── breach/
│   │   ├── exception/
│   │   ├── escalation/
│   │   ├── action/
│   │   ├── approval/
│   │   ├── closure/
│   │   ├── model_validation/
│   │   ├── valuation_control/
│   │   └── audit/
│   ├── portfolio_management/
│   ├── operations/             # Wave 7：NAV / PnL / 托管 / FA
│   └── trading/
├── 4_mcp/                      # 运行时权威；目标迁移至 5_integrations/mcp
├── 5_integrations/             # Wave 7：外部 Adapter + Quant API
│   ├── market_data/
│   ├── pms/
│   ├── oms/
│   ├── ems/
│   ├── broker/
│   ├── custodian/
│   ├── fund_admin/
│   ├── accounting/
│   └── quant/
├── 5_deploy/
├── 6_entry/
├── 7_ai/                       # Wave 8：NL / Workflow Interface
│   ├── moduleinfo.md
│   ├── runtime.py
│   ├── agents/
│   │   ├── investment_agent/
│   │   ├── portfolio_agent/
│   │   ├── risk_agent/
│   │   ├── valuation_agent/
│   │   └── workflow_agent/
│   ├── skills/                 # 索引；SKILL.md 仍在 3_skills/
│   ├── tools/                  # Business / Quant / MCP connectivity
│   ├── workflows/              # 索引；autorisk/ 仍为自动化运行时
│   └── knowledge/
├── adapter/                    # Wave 2：旧新 DTO 适配（skeleton）
├── aiagent/                    # 运行时权威；目标迁移至 7_ai/agents
├── app/
├── artefacts/
├── autorisk/                   # 保留：Risk Workflow / Automation
├── backend/
├── compatibility/              # Wave 2：迁移链文档入口（Python Facade 在 2_processing.compatibility）
├── docs/
├── frontend/
├── iac/
├── legacy/                     # Wave 2：遗留路径登记
├── mmf-eva-report/
├── platform_agent/             # 运行时权威；目标迁移至 7_ai/agents
├── scripts/
├── templates/
└── tests/
```

## 二、核心模块展开

### 1. 数据存储层

```text
1_datastorage/
├── docker-compose.yml          # 本地基础依赖编排
├── moduleinfo.md               # 模块说明
├── object_store/               # 对象存储相关配置
├── postgres/                   # PostgreSQL schema / 初始化脚本
├── redis/                      # Redis 相关配置
└── timeseries/                 # 时序数据相关存储
```

### 2. 处理与分析层

```text
2_processing/
├── moduleinfo.md               # 处理层说明
├── requirements.txt            # Python 依赖
├── api/                        # FastAPI 入口与路由
├── etl/                        # 数据抽取、转换、加载
├── logging/                    # 日志处理
├── review/                     # 审核/复核能力
├── sql/                        # SQL 脚本与查询资产
├── test/                       # 处理层测试
├── tools/                      # 风险、估值、分析核心工具库
└── workers/                    # 异步任务/后台工作进程
```

### 3. Backend 服务层

```text
backend/
└── app/
    ├── main.py                 # 标准 FastAPI 入口
    ├── unified.py              # 统一单进程入口，挂载 processing/entry 等子应用
    ├── crud.py                 # 通用数据访问
    ├── models.py               # 模型定义
    ├── utils.py                # 工具函数
    ├── backend_pre_start.py    # 启动前检查
    ├── initial_data.py         # 初始化数据
    ├── core/                   # 配置、数据库、鉴权等基础设施
    ├── services/               # 领域服务封装
    ├── email-templates/        # 邮件模板
    ├── alembic/                # 数据库迁移
    └── api/
        ├── deps.py             # 依赖注入与鉴权
        ├── main.py             # API router 聚合入口
        └── routes/
            ├── login.py
            ├── users.py
            ├── access_control.py
            ├── api_keys.py
            ├── notifications.py
            ├── chat.py
            ├── knowledge.py
            ├── frontend_log.py
            ├── user_agent.py
            ├── user_custom_tool.py
            ├── items.py
            ├── private.py
            ├── utils.py
            └── fsi/            # FSI 业务聚合路由
```

### 4. Frontend 应用层

```text
frontend/
└── src/
    ├── main.tsx                # 前端入口
    ├── index.css               # 全局样式
    ├── utils.ts                # 通用前端工具
    ├── fsiClient.ts            # 前后端 API 客户端
    ├── routeTree.gen.ts        # TanStack Router 生成路由树
    ├── vite-env.d.ts
    ├── client/                 # 客户端能力封装
    ├── components/             # 通用组件与侧边栏
    ├── hooks/                  # React Hooks
    ├── i18n/                   # 多语言资源
    ├── lib/                    # 前端基础库封装
    ├── routes/                 # 路由页面
    │   ├── __root.tsx
    │   ├── _layout.tsx
    │   ├── login.tsx
    │   ├── signup.tsx
    │   ├── recover-password.tsx
    │   ├── reset-password.tsx
    │   └── _layout/
    ├── modules/                # 业务模块页（不重命名 portfolio-opt）
    │   ├── README.md
    │   ├── data-management/
    │   ├── indicator-explorer/
    │   ├── investment-risk/
    │   ├── portfolio-cockpit/
    │   ├── portfolio-opt/      # 路由 /portfolio-opt 保留
    │   ├── risk-testing/
    │   ├── sql-library/
    │   ├── system-config/
    │   └── valuation-pnl/
    └── platform/               # Wave 9：Workbench / Copilot 上下文 / 菜单合同
```

### 5. 文档与脚本

```text
docs/
├── technical_architecture.md
├── integrated_architecture.md
├── database-schema.md
├── local_development_stack.md
├── startup_app_template_derived.md
├── startup_commands_and_roles.md
├── risk-testing.md
├── menu_dataflow_matrix.md
├── knowledge_base_guide.md
├── current_system_menu.md
├── current_platform_directory_tree.md
├── target_platform_directory_tree.md
├── architecture_migration_map.md
└── third_party_patches.md

scripts/
├── dev.py                      # 本地开发统一启动器
├── dev.ps1                     # PowerShell 启动脚本
├── setup_db.py                 # 本地数据库初始化
├── migrate-db.sh               # 迁移脚本
├── bl-dev.sh                   # dev 云调试辅助
├── run_api.py                  # API 启动辅助
├── sync_openapi_contracts.py   # OpenAPI 合同同步
├── run_dataflow_unit_checks.py # 数据流单元检查
├── fix_db_grants.py            # 数据库授权修复
└── protect-main-branch.sh      # 主分支保护
```

### 6. Wave 2 新增骨架目录

```text
3_riskengine/           # Wave 3：统一 RiskEngine + adapters（FinancePy/Riskfolio/ORE）
4_business/             # 业务用例；investment_risk KPI + portfolio_optimization 过闸优化
7_ai/                   # AI 目标 skeleton（3_skills / aiagent 仍为权威）
legacy/                 # 遗留模块登记
compatibility/          # 迁移链文档入口（非 import 包名）
adapter/                # DTO 适配 skeleton
2_processing/compatibility/  # 可导入 Processing Facade
```

### 7. 其他平台能力目录

```text
3_skills/       # 技能、命令与运行时资产（权威）
4_mcp/          # MCP 相关服务与客户端（权威）
5_deploy/       # 部署相关内容
6_entry/        # 入口层 / 静态入口 / Web 汇聚
aiagent/        # AI Agent 相关实现（权威）
platform_agent/ # 平台 Agent（权威）
autorisk/       # 自动风控子系统
iac/            # 基础设施与部署配置
templates/      # 模板与样板工程
tests/          # 根级通用测试
```

## 三、架构迁移文档

| 文档 | 内容 |
|---|---|
| [`current_platform_directory_tree.md`](current_platform_directory_tree.md) | 本文：当前实际目录 |
| [`target_platform_directory_tree.md`](target_platform_directory_tree.md) | 目标目录树 |
| [`architecture_migration_map.md`](architecture_migration_map.md) | Current → Target 映射与兼容要求 |

## 四、建议理解顺序

若要快速理解当前平台，建议按以下顺序阅读：

1. `AGENTS.md`
2. `README.md`
3. `PROJECT_OVERVIEW.md`
4. `docs/technical_architecture.md`
5. `backend/app/unified.py`
6. `backend/app/api/main.py`
7. `frontend/src/components/Sidebar/AppSidebar.tsx`
8. `frontend/src/fsiClient.ts`
9. `2_processing/api/`
10. `2_processing/tools/`

## 五、说明

1. 本文档描述的是**当前**平台主要目录树，不是完整文件清单。
2. 目录树以当前仓库实际存在的主干结构为准；`5_integrations/` 与 `7_ai/` Agent 内核已落地，`4_mcp/`、`aiagent/`、`3_skills/`、`autorisk/` 仍为对应运行时权威。
3. 目标结构与迁移步骤见 [`target_platform_directory_tree.md`](target_platform_directory_tree.md) 与 [`architecture_migration_map.md`](architecture_migration_map.md)。
