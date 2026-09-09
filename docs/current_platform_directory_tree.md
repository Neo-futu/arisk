<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# arisk 平台主要文件目录树

本文档整理当前 arisk 项目的主要文件与核心目录树，侧重平台主干结构，不展开缓存目录、构建产物或零散临时文件。

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
│   ├── etl/
│   ├── logging/
│   ├── review/
│   ├── sql/
│   ├── test/
│   ├── tools/
│   └── workers/
├── 3_skills/
├── 4_mcp/
├── 5_deploy/
├── 6_entry/
├── aiagent/
├── app/
├── artefacts/
├── autorisk/
├── backend/
├── docs/
├── frontend/
├── iac/
├── mmf-eva-report/
├── platform_agent/
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
    └── modules/                # 业务模块页
        ├── data-management/
        ├── indicator-explorer/
        ├── investment-risk/
        ├── portfolio-cockpit/
        ├── portfolio-opt/
        ├── risk-testing/
        ├── sql-library/
        ├── system-config/
        └── valuation-pnl/
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
└── current_platform_directory_tree.md

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

### 6. 其他平台能力目录

```text
3_skills/       # 技能、命令与运行时资产
4_mcp/          # MCP 相关服务与客户端
5_deploy/       # 部署相关内容
6_entry/        # 入口层 / 静态入口 / Web 汇聚
aiagent/        # AI Agent 相关实现
autorisk/       # 自动风控子系统
iac/            # 基础设施与部署配置
templates/      # 模板与样板工程
tests/          # 根级通用测试
```

## 三、建议理解顺序

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

## 四、说明

1. 本文档描述的是“当前平台主要目录树”，不是完整文件清单。
2. 目录树以当前仓库实际存在的主干结构为准。
3. 若需要，我可以继续补一份“目录 -> 职责 -> 关键入口文件”的映射表。
