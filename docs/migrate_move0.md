ARISK Platform Current → Target Architecture Blueprint
Wave 状态：架构理解阶段（只读）
本轮未修改源代码、数据库、API、菜单、配置、第三方源码或依赖，也未创建 Blueprint 文件。以下结论来自对当前仓库及三个第三方源码目录的实际检查。

执行摘要
当前 ARISK 已形成完整的 Web、计算、Agent、MCP、审核与报表平台，但架构仍处于多套能力逐步叠加的阶段：

2_processing 同时承担 API、查询、风险计算、报表生成、调度和部分工作流职责。
传统 Risk、Investment Risk、Portfolio Optimization、FinancePy Risk Testing 是四套并行计算路径。
Portfolio、Position、Market Data、PnL、Compliance 在不同模块中存在重复加载、计算或 fallback。
Backend 已经是统一用户鉴权入口，但 Unified 模式同时挂载多个内部服务路径。
三个第三方项目已在本机仓库中找到：
FinancePy：完整源码，当前已有有限集成。
Riskfolio-Lib：完整源码，尚未进入 ARISK 运行依赖。
ORE：主框架源码存在，但 QuantLib 与 QuantLib-SWIG 子模块为空，当前不能视为完整可构建版本。
FinancePy 为 GPL-3.0-or-later，正式集成前必须完成许可评估。
目标架构不应重写三个第三方项目，而应通过 ARISK 自有 RiskEngine 建立稳定的反腐层、统一数据合同、模型治理和结果聚合。
建议采用 Strangler Migration（绞杀式迁移）：保留现有路由和功能，在内部逐步建立 3_riskengine 与 4_business，按业务域迁移，不进行一次性大搬迁。

1. Current Architecture
1.1 当前运行架构

flowchart TD
    Browser[浏览器]
    Frontend[frontend<br/>React / TypeScript / Vite]
    Backend[backend<br/>JWT / RBAC / API Gateway]
    Processing[2_processing<br/>业务查询与计算]
    Entry[6_entry<br/>Agent / Direct / Review]
    MCP[4_mcp<br/>Internal / Wind MCP]
    AIAgent[aiagent]
    PlatformAgent[platform_agent]
    AutoRisk[autorisk]
    DB[(PostgreSQL<br/>fsi / iam / chatdb)]
    Redis[(Redis)]
    ObjectStore[(MinIO / S3)]
    ThirdParty[FinancePy<br/>PyPortfolioOpt<br/>未来 Riskfolio / ORE]

    Browser --> Frontend
    Frontend -->|/api/v1/*| Backend
    Backend -->|/api/v1/fsi/*| Processing
    Backend -->|Agent API| Entry
    Entry --> AIAgent
    Entry --> PlatformAgent
    AIAgent --> Processing
    AIAgent --> MCP
    Processing --> DB
    Processing --> Redis
    Processing --> ObjectStore
    Processing --> ThirdParty
    Backend --> AutoRisk

Backend Unified 模式会在一个 FastAPI 进程内挂载：

/api/v1：Backend 用户 API
/processing：Processing 子应用
/entry：Entry 子应用
/mcp：MCP Gateway
/autorisk：AutoRisk
实现见 backend/app/unified.py。

1.2 当前职责边界
层	当前职责	主要问题
Frontend	页面、菜单、查询编排、部分 fallback	客户端过于集中，存在业务级 fallback
Backend	JWT、RBAC、组合权限、API 代理	代理路由较多，部分聚合计算也在 Backend
2_processing	数据查询、风险计算、估值、报表、调度、审核	职责过宽，是当前最大耦合点
6_entry	Agent、Direct Query、人工审核入口	V1/V2 并存，内部边界依赖网络隔离
4_mcp	Internal DB、Wind 数据连接	Gateway 鉴权不足，Wind 当前部分为 mock
aiagent	用户业务 Agent、工具调用、知识检索	与 Processing/MCP 多路径连接
platform_agent	平台任务 Agent	测试和角色定义仍不完整
autorisk	确定性规则、AI 双审、人工双签、审计链	与 Processing 合规/规则体系尚未统一
1_datastorage	PostgreSQL、Redis、MinIO、TimescaleDB	业务表与 IAM 采用两套迁移机制
2. Current Directory Tree
arisk/
├── 1_datastorage/           数据库、Redis、MinIO、TimescaleDB
├── 2_processing/            查询、计算、报表、调度、审核
├── 3_skills/                技能、命令、技能运行时
├── 4_mcp/                   MCP Gateway、Internal MCP、Wind MCP
├── 5_deploy/                Agent 与旧部署编排
├── 6_entry/                 Agent、Direct API、审核入口
├── aiagent/                 用户业务 Agent
├── platform_agent/          平台运维 Agent
├── autorisk/                自动风控与双签审计
├── backend/                 JWT、RBAC、API Gateway
├── frontend/                唯一 Web UI
├── docs/                    架构与业务文档
├── scripts/                 开发、数据库、合同同步脚本
├── tests/                   Golden-path 根级测试
├── artefacts/               报表和任务产物
├── iac/                     应用基础设施
├── FinancePy/               FinancePy 本地源码
├── Riskfolio-Lib/           Riskfolio-Lib 本地源码
└── ORE/                     OpenSourceRisk/ORE 本地源码
三个第三方源码目录都被 .gitignore 忽略。因此当前属于本地工作树资产，不是可由 Git 稳定还原的仓库依赖，这是重要的供应链与构建可重复性风险。

1. Current Frontend Menu Tree
当前菜单权威定义位于 AppSidebar.tsx。
阿雷斯 · 智能风控和投资分析系统
├── 仪表板 (/)
├── 组合驾驶舱 (/portfolio-cockpit)
├── 投资风险分析 (/investment-risk)
│   ├── 模块总览
│   ├── 指标验证
│   ├── 组合概况
│   ├── 风险指标
│   ├── 绩效归因
│   ├── 利率与信用敏感度
│   ├── 流动性与压力测试
│   ├── 风险预算与前置试算
│   ├── 宏观与市场动态
│   └── 基本面因子与行为
├── 风险测试 (/risk-testing)
│   ├── 敏感度测试
│   ├── 压力测试
│   ├── 情景测试
│   ├── 反向压力测试
│   ├── 尾部风险测试
│   ├── 关键利率久期 KRD
│   ├── PnL 归因
│   ├── 历史收益回测
│   ├── VaR 回测
│   └── 估值调整 XVA
├── 数据管理中心
├── 指标探索
├── 持仓明细
├── 组合估值与损益
├── 组合优化
├── 合规核查
├── 风控规则配置
├── 报表中心
├── 定时任务
├── 自动风控
├── Agent Chat
├── 专家知识库
├── SQL 资产库
└── 系统管理
    ├── 用户与权限管理
    ├── 系统配置
    ├── API Key 管理
    ├── 通知中心
    └── 设置
菜单与路由规则
普通用户按 menu_paths 过滤。
超级管理员可查看除 HIDDEN 外的菜单。
BETA 标记只显示在一级菜单，不显示在子菜单。
子菜单目前没有独立的权限和发布阶段过滤。
路由全集大于菜单集合：
/items 可导航但不在菜单中。
/risk 是兼容路由，会跳转到投资风险指标页。
登录、注册、密码恢复页面不在侧边栏。
路由树是自动生成文件，不应直接编辑。
4. Current API Map
4.1 Frontend API
前端主要通过 fsiClient.ts 调用：

API 家族	前缀
用户访问上下文	/api/v1/access-control/*
组合驾驶舱	/api/v1/fsi/portfolio-cockpit/*
投资风险	/api/v1/fsi/investment/*
风险测试	/api/v1/fsi/risk-testing/*
基础风险	/api/v1/fsi/risk/*
组合优化	/api/v1/fsi/portfolio-opt/*
持仓	/api/v1/fsi/positions/*
估值与损益	/api/v1/fsi/valuation/*
数据管理	/api/v1/fsi/data-management/*
合规规则	/api/v1/fsi/risk-rules/*
报表	/api/v1/fsi/reports/*
定时任务	/api/v1/fsi/schedules/*
Agent	/api/v1/fsi/agent/*
知识库	/api/v1/knowledge/*
Chat 历史	/api/v1/chat/*
API Keys	/api/v1/api-keys/*
通知	/api/v1/notifications/*
前端日志	/api/v1/logs/batch
现有问题：

fsiClient.ts 超过 2,000 行，类型、API 和业务域高度耦合。
Expert 页面和 Logger 存在绕过统一客户端的直接 fetch/axios。
持仓、行情和风险测试存在客户端 fallback。
部分路由只有菜单隐藏，没有一致的前端 route guard。
4.2 Backend API
Backend 聚合入口位于 backend API router。

主要 API：

登录和 Token
用户管理
RBAC 与组合授权
菜单发布阶段
API Key
通知
Chat 历史
知识库
Agent 配置
自定义工具
前端日志
/api/v1/fsi/* 业务代理
FSI 路由注册见 FSI router。

Backend 的核心定位应继续保持为：

用户身份、授权、组合权限、API 合同、兼容路由和对外安全边界。

它不应逐步演变为第二个计算引擎。

4.3 Processing API
实际注册入口见 2_processing/api/main.py。

前缀	功能
/positions	持仓、摘要、NAV
/data-management	持仓、行情、模拟订单、组合 CRUD
/indicators	指标定义与观测值
/valuation	估值与 PnL
/portfolio-cockpit	驾驶舱
/portfolio-opt	组合优化
/risk-testing	FinancePy 风险测试
/risk	Exposure、VaR
/risk-rules	风控规则、附件、适用范围
/investment	投资风险分析
/reports	报表任务
/schedules	定时任务
/review	人工审核
/op-logs	操作日志
/sql-assets	SQL 资产
/health、/context	服务状态与系统上下文
Processing 采用服务级 X-API-Key，不理解最终用户 JWT。

4.4 Agent / Entry API
6_entry 提供：

前缀	功能
/agent/v2	Agent、模型、工具、同步/流式对话、异步任务
/agent	V1 兼容 Agent
/platform/v1	Platform Agent
/query	持仓、Exposure、VaR 直接查询
/review-ui	人工审核收件箱
/logs-ui	操作日志查看
/health	健康检查
主要问题：

Agent V1/V2 并存。
Entry 多数路由依赖“内部网络”而不是自身用户鉴权。
Direct Query 与 Backend FSI 出现重复代理路径。
人工审核的 AI Review 代理存在接口缺口。
4.5 MCP API
MCP Gateway：

GET /health
GET /tools
POST /mcp/{server_name}/{tool_name}
Internal MCP：

get_positions
get_risk_snapshot
get_nav_history
get_var_three_methods
get_fund_list
get_context
query_business_db
Wind MCP：

wind_get_price
wind_get_fx
wind_get_bond_info
wind_get_hibor
主要问题：

MCP Gateway 当前没有实际鉴权依赖。
Gateway 工具目录和 Wind Server 实际工具不一致。
Wind 工具当前部分是 mock，不应被认定为生产行情集成。
query_business_db 已限制为只读查询，这是应保留的安全属性。
5. Current Database Map
5.1 Schema 事实
必须纠正一个容易误解的地方：

raw
para
balance
mktdata
transact
svc
这些不是六个 PostgreSQL schema，而是 fsi schema 内的表名前缀域。命名规则见 001_schema_init.sql。

实际 PostgreSQL schema：

Schema	职责	管理机制
fsi	金融业务数据	顺序 SQL migration
iam	用户、角色、权限、菜单、组合授权	SQLModel + Alembic
chatdb	Chat、Agent、知识库	Alembic
ts	实时时序数据	TimescaleDB DDL
public	PostgreSQL 默认	系统
5.2 FSI 数据域
前缀域	主要内容
raw_*	原始持仓、交易、价格、FX、曲线、NAV、ETL 批次
para_*	组合主数据、风险限制、交易对手、业务角色、旧菜单、规则配置
balance_*	NAV、MMF 指标、债券、股票、CD、存款、回购、估值表
mktdata_*	行情、FX、指数成分、债券风险、宏观指标
transact_*	股票、债券、CD、存款、期货、期权、回购、基金、申赎、PnL、模拟订单
svc_*	风险快照、Exposure、绩效、预警、审核、Agent checkpoint、操作日志
5.3 基础设施
PostgreSQL/TimescaleDB：主业务与时序数据。
Redis：
DB0：计算/行情缓存
DB1：Celery broker
DB2：Celery result
DB3：会话
DB4：NAV 缓存
MinIO/S3：
报表、附件、生成产物
原始数据对象
当前部分规则附件仍直接以 BYTEA 存在 PostgreSQL 中。
5.4 数据库主要问题
旧表名仍被 ETL、Workers、Review、日志代码引用，例如：
fsi.positions
fsi.funds
fsi.risk_snapshots
fsi.review_requests
fsi.audit_log
当前实际表已经转为：
balance_*
para_portfolio
svc_risk_snapshot
svc_wf_*
svc_sys_op_log
IAM 菜单与 fsi.para_menu 形成双菜单体系。
fsi 使用自研 SQL migration，iam/chatdb 使用 Alembic，版本治理分裂。
Timescale 初始化脚本对 ts schema 的创建依赖不够明确。
Backend 与 Processing 的数据库配置入口不同，可能发生环境漂移。
6. Current Risk Calculation Map
能力	当前实现	主要算法/库	现状问题
Portfolio	Cockpit、Data Management	SQL 聚合、MMF 状态规则	状态口径分散
Position	Positions、Data Management、Risk Testing Holdings	多张 balance_* + fallback	多入口、多 DTO
Market Data	Data Management、Portfolio Opt、Risk Testing	DB、yfinance、OpenBB、proxy	fallback 规则重复
Valuation	Valuation router	收益、波动、回撤	未形成统一估值服务
PnL	Valuation PnL、Risk Testing PnL Explain	复利、Carry、Rates、FX、Residual	两套归因口径
Exposure	Traditional Risk	WAM/WAL、流动性、集中度	SQL/Hybrid/ORM 多模式
VaR	Traditional Risk	Historical、Distribution、Monte Carlo	与 Risk Testing 回测分离
Investment Risk	Investment router	Beta、回撤、归因、KRD、流动性、宏观、因子	业务指标编排分散
Portfolio Optimization	Portfolio optimizer	PyPortfolioOpt、HRP、CAPM、BL	尚未使用 Riskfolio
Risk Testing	ProfessionalRiskEngine	FinancePy Flat Curve + ARISK 补充算法	仅使用 FinancePy 小部分能力
MMF	SQL + 报表工具 + Exposure	WAM/WAL、SFC 规则、Excel/PDF/Word	合规口径多处复制
Compliance	Risk Rules + Exposure + 前端 fallback	动态规则 + 静态规则	前后端双规则
Reports	ThreadPool + subprocess	报表脚本	缺统一 Job Engine
Scheduler	内存线程 + JSON，另有 Celery Beat	分钟轮询、防重入	双调度体系
AutoRisk	独立服务	确定性规则、AI 双审、双签、Hash Chain	与主规则结果未统一
Human Review	Processing Review + Entry UI	Claim/Approve/Reject/Gate	状态和接口不完整统一
核心判断
当前不存在一个真正统一的 RiskEngine。

目前的风险能力是以下系统并存：

它们应逐步汇聚到统一合同和统一数据快照，但不能简单合并为一个超大模块。

7. FinancePy Capability Map
7.1 当前源码状态
路径：FinancePy
版本：
构建元数据：1.1.2
包内 __version__：1.1.0
许可证：GPL-3.0-or-later，见 FinancePy pyproject。
当前 ARISK 运行依赖只是 financepy>=1.0.2，没有锁定本地源码版本，见 2_processing/requirements.txt。
7.2 What it already provides
Discount、IBOR、OIS、CDS 曲线
曲线插值、Bootstrap、并行冲击
Equity、FX、Rates、Credit、Bond、Inflation 产品
Black-Scholes、Black、Bachelier、SABR
HW、BK、BDT 短率树
LMM、CIR、Vasicek、Heston、Copula
Equity/FX Vol Surface
Bonds、FRN、Convertible、Bond Option
CDS、Basket、Index、Tranche
Swap、OIS、FRA、Cap/Floor、Swaption
Delta、Gamma、Vega、Theta、Rho
PV01、DV01、KRD、Spread DV01、Recovery DV01
单元测试与 Golden regression tests
7.3 What ARISK should reuse
标准产品定价。
曲线和波动率结构。
Instrument-level Greeks。
债券、利率、FX、权益和信用产品的基础模型。
ARISK Adapter 内部的 FinancePy 对象构造与调用。
7.4 What ARISK should NOT duplicate
基础贴现曲线和插值。
标准产品现金流和定价公式。
Black/SABR/HW/BK/BDT 等模型。
标准 Greeks、DV01、KRD 计算。
FinancePy 已有的产品类。
7.5 What requires ARISK extension
Portfolio/Market Snapshot 标准化。
行情来源、缺失值与质量治理。
模型选择政策、参数版本和审批。
跨产品风险因子统一。
组合级聚合、限额和归因。
场景库、压力测试、反向压力。
任务、审计、结果持久化。
监管和 MMF 业务口径。
统一错误与 Diagnostics。
7.6 关键风险
GPL 许可是正式集成的首要 Gate。
版本元数据不一致。
新旧曲线模块并存。
部分包导出和跨币种 Swap import 存在不一致。
直接让业务对象依赖 FinancePy 类会产生严重版本耦合。
8. Riskfolio Capability Map
8.1 当前源码状态
路径：Riskfolio-Lib
版本：7.3.0，见 Riskfolio setup。
许可证：BSD 3-Clause。
当前 ARISK 没有运行时依赖 Riskfolio，现有优化使用 PyPortfolioOpt。
8.2 What it already provides
Mean-Risk Optimization
MinRisk、Utility、Sharpe、MaxRet
Risk Parity 与 Relaxed Risk Parity
HRP、HERC、HERC2、NCO
Worst-Case Robust Optimization
OWA Optimization
MVSK
Black-Litterman
Factor Models
Entropy Pooling
多种均值、协方差、共峰度估计
CVaR、EVaR、RLVaR、Drawdown 等大量风险度量
资产、分类、因子、整数、Cardinality、Tracking Error、Turnover 约束
网络、聚类、中心性与风险贡献约束
风险贡献、因子风险贡献、Brinson 分析
CVXPY 多 Solver 编排
8.3 What ARISK should reuse
优化问题数学建模。
Risk Measure 实现。
Risk Parity 和层次聚类优化。
BL、Factor、Entropy Pooling。
约束矩阵编译。
求解器调用和标准优化模型。
8.4 What ARISK should NOT duplicate
CVXPY 目标函数与锥规划。
HRP/HERC/NCO 算法。
标准风险度量。
通用资产/因子约束编译。
标准 BL 和因子模型估计。
8.5 What requires ARISK extension
SFC/MMF 监管约束模板。
内部风险预算和禁投规则。
组合草案、审批、发布状态。
Market/Return 数据合同。
Solver 白名单、超时、fallback 和可重复性。
模型与数据版本审计。
优化结果解释、可执行性和合规复核。
与交易前检查的衔接。
8.6 关键风险
依赖栈较重：CVXPY、编译扩展、多个 Solver。
EXP/POW 锥问题可能依赖 MOSEK 等商业 Solver 才稳定。
README 声明与具体 Solver 白名单不完全一致。
部分高级功能测试覆盖不足。
必须在 Adapter 内统一模型名和 Solver Policy。
9. ORE Capability Map
9.1 当前源码状态
路径：ORE
ORE 主框架存在：
App
OREData
OREAnalytics
QuantExt
ORETest
ORE-SWIG
Examples
Docs
缺失：
ORE/QuantLib 为空
ORE/ORE-SWIG/QuantLib-SWIG 为空
构建文件明确依赖 QuantLib，见 ORE CMake。
版本：
CMake：1.8.15.0
QuantExt Header：1.8.16.0
许可证：Modified BSD。
9.2 What it already provides
XML Trade 与 Portfolio Representation
Market 与 Today’s Market Configuration
Curve Configuration
Pricing Engine Configuration
QuantLib/QuantExt 产品与模型
Pricing
Scenario Generation
Stress Testing
Sensitivity
Historical/Parametric VaR
PnL/PnL Explain
Exposure Simulation
Netting Set
Collateral
CVA、DVA、FVA、COLVA、MVA
XVA Stress/Sensitivity/Explain
SIMM 与 CRIF
SA-CCR、SA-CVA、BA-CVA
Market Risk
完整 XML/XSD 配置体系
C++、CLI、SWIG 和测试/Examples
9.3 What ARISK should reuse
Complex Derivatives Pricing。
交易、Netting Set、CSA 表示。
Scenario、Stress、Sensitivity 语义。
Exposure Cube。
Monte Carlo XVA。
SIMM、CRIF、SA-CCR、SA-CVA。
ORE XML 配置和批处理模式。
ORE 的测试与模型验证方法。
9.4 What ARISK should NOT duplicate
QuantLib/QuantExt 定价引擎。
Monte Carlo Exposure Infrastructure。
Netting、Collateral 和 XVA 数学框架。
SIMM、CRIF、SA-CCR 计算框架。
ORE Trade XML 和 Scenario 基础设施。
9.5 What requires ARISK extension
ARISK Instrument/Trade 到 ORE Trade XML 的映射。
ARISK Market Snapshot 到 ORE Market/Curve Config 的映射。
ORE 作业编排、隔离和超时。
输出 Report/Cube 的标准化解析。
ARISK 权限、审计、组合和数据血缘。
模型政策、运行配置版本和审批。
ORE Error 到 ARISK Error Envelope 的转换。
9.6 推荐集成方式
首选：

独立进程/Sidecar/Batch Worker 边界

流程：

原因：

隔离 C++ ABI 与崩溃风险。
符合 ORE 原生 ore.xml 运行方式。
便于任务化、超时、重试和资源限制。
当前 QuantLib/SWIG 子模块缺失，不适合马上走 Python 嵌入。
SWIG 仅作为未来低延迟或交互式增强路径。

10. Target Architecture
10.1 目标分层
flowchart TD
    UI[Frontend / External Clients]
    Gateway[Backend<br/>Identity / RBAC / API Compatibility]
    Entry[6_entry<br/>Web / API / CLI / Agent Entry]
    Business[4_business<br/>Business Use Cases]
    Engine[3_riskengine<br/>Unified Quant & Risk Platform]
    Adapters[Engine Adapters]
    FP[FinancePy]
    RF[Riskfolio-Lib]
    ORE[ORE]
    Integrations[5_integrations<br/>Market / MCP / Files / Notifications]
    Storage[1_datastorage]
    AI[7_ai<br/>Agent / Skills / Knowledge]
    Audit[Audit / Review / AutoRisk]

    UI --> Gateway
    Gateway --> Entry
    Entry --> Business
    Business --> Engine
    Engine --> Adapters
    Adapters --> FP
    Adapters --> RF
    Adapters --> ORE
    Business --> Integrations
    Engine --> Integrations
    Business --> Storage
    Engine --> Storage
    AI --> Business
    Audit --> Business



10.2 核心原则
Business Domain 回答业务问题。
RiskEngine 提供统一计算能力。
第三方项目只通过 Adapter 使用。
第三方对象不能泄漏到 API 和业务领域。
Frontend 和 Agent 不直接调用第三方计算库。
数据库不是业务服务间的隐式接口。
所有计算具有数据版本、模型版本、参数版本和血缘。
现有 API 路由通过兼容 Facade 保持稳定。
AI 负责解释与编排，不作为权威数值计算源。
合规硬约束、权限、审计和人审不能下沉到 LLM。
10.3 RiskEngine 内部边界
建议 3_riskengine 包含：

组件	职责
Contracts	统一输入输出 DTO
Portfolio Snapshot	统一持仓与 NAV 快照
Market Snapshot	行情、曲线、波动率、FX
Risk Factors	利率、信用、FX、权益、波动率、流动性
Valuation	统一估值入口
Analytics	VaR、ES、Stress、Scenario、Tail、PnL
Aggregation	Security → Book → Portfolio
Limits	风险限额与监管规则接口
Validation	数据、模型、结果验证
Adapters	FinancePy、Riskfolio、ORE
Execution	同步/异步运行与资源治理
Lineage	数据与模型血缘
Diagnostics	错误、fallback、覆盖率和假设
统一合同应至少包含：

PortfolioSnapshot
PositionSnapshot
MarketSnapshot
InstrumentSpec
RiskFactorSet
ScenarioDefinition
ModelPolicy
CalculationRequest
CalculationResult
ValidationResult
Diagnostics
Lineage
11. Target Directory Tree

arisk/
├── 1_datastorage/
│   ├── postgres/
│   ├── timeseries/
│   ├── redis/
│   └── object_store/
├── 2_processing/
│   ├── api/
│   ├── jobs/
│   ├── queries/
│   └── compatibility/
├── 3_riskengine/
│   ├── contracts/
│   ├── portfolio/
│   ├── market/
│   ├── factors/
│   ├── valuation/
│   ├── analytics/
│   ├── aggregation/
│   ├── limits/
│   ├── validation/
│   ├── execution/
│   ├── lineage/
│   └── adapters/
│       ├── financepy/
│       ├── riskfolio/
│       └── ore/
├── 4_business/
│   ├── investment_risk/
│   ├── portfolio_optimization/
│   ├── risk_testing/
│   ├── portfolio_management/
│   ├── trading/
│   └── shared/
│       ├── compliance/
│       ├── reporting/
│       ├── scheduling/
│       ├── audit/
│       └── review/
├── 5_integrations/
│   ├── market_data/
│   ├── mcp/
│   ├── notifications/
│   ├── object_storage/
│   ├── fund_accounting/
│   └── external_systems/
├── 6_entry/
│   ├── web/
│   ├── cli/
│   └── excel/
├── 7_ai/
│   ├── agents/
│   ├── platform_agents/
│   ├── skills/
│   ├── knowledge/
│   ├── tools/
│   └── orchestration/
├── backend/
├── frontend/
├── docs/
├── scripts/
├── tests/
├── artefacts/
└── iac/

2_processing 在目标状态下不再是所有业务计算的容器，而是：

内部 API Host
Job Runner
Query Service
兼容 Facade
RiskEngine/Business Domain 的运行宿主
1.  Target Business Domain Map
12.1 三个核心业务
Domain	回答的问题	核心能力	主要引擎
投资风险分析	当前组合有什么风险？	Exposure、VaR/ES、归因、KRD、信用、流动性、宏观、因子	RiskEngine + FinancePy + Riskfolio 风险度量
组合配置与优化	应该配置什么组合？	Mean-Risk、Risk Parity、BL、HRP、约束优化、组合评估	RiskEngine + Riskfolio
风险测试	市场发生变化后组合会怎么样？	Sensitivity、Scenario、Stress、Reverse Stress、Tail、XVA	RiskEngine + FinancePy + ORE
12.2 支撑业务域
Domain	职责
Portfolio Management	组合主数据、持仓快照、NAV、授权组合
Trading	模拟订单、Pre-trade、交易影响
Compliance	SFC/MMF、合同限制、内部限额
Reporting	报表模板、生成、产物
Scheduling	任务计划、幂等、执行历史
AutoRisk	规则判定、AI 复核、人工双签、审计
Review	Claim、Approve、Reject、Gate
AI	Chat、Knowledge、Skills、解释与编排
Integrations	Market Data、MCP、通知、对象存储
1.  Current → Target Migration Matrix
Current	Target	迁移策略	兼容要求
2_processing/tools/risk	3_riskengine/analytics	先抽合同，再迁算法	保留 /api/v1/fsi/risk/*
risk_testing	4_business/risk_testing + 3_riskengine	业务用例与计算分离	保留全部 Risk Testing 路由
portfolio_optimizer.py	4_business/portfolio_optimization + Riskfolio Adapter	PyPortfolioOpt 作为旧 Adapter，Riskfolio 新增 Adapter	保留 /portfolio-opt
Investment router	4_business/investment_risk	逐个 Use Case 迁移	保留 /investment/*
Positions/Data Management	portfolio_management	统一 Snapshot Contract	保留原持仓 API
Simulated Orders	trading	迁移为交易草案与 Pre-trade	保留 Data Management API
Market fallback	5_integrations/market_data	合并 DB/yfinance/OpenBB/Wind 策略	不改变当前结果字段
Valuation/PnL	RiskEngine Valuation/PnL	统一计算口径	保留 /valuation/*
MMF SQL/规则	Investment Risk + Compliance	保留 SQL，外包统一合同	不删除 MMF
Risk Rules	Business Shared Compliance	规则成为服务端唯一事实	保留 /risk-rules
Reports	Business Shared Reporting	抽离作业执行合同	/reports 必须继续存在
Schedules	Business Shared Scheduling	统一线程/Celery 调度	/schedules 必须继续存在
AutoRisk	Risk Governance Workflow	保留独立高风险闭环	/autorisk 必须继续存在
4_mcp	5_integrations/mcp	保持协议适配，无业务判断	MCP 工具名尽量兼容
3_skills	7_ai/skills	迁移知识资产，不复制	保持技能调用兼容
aiagent	7_ai/agents	整合 V2，保留 V1 Facade	Agent Chat 不删除
platform_agent	7_ai/platform_agents	与业务 Agent 分域	保留 Platform API
Review UI/Processing Review	Shared Review	统一状态机	人工审核不删除
IAM + para_menu	IAM 为应用授权事实源	逐步废止双菜单写入	菜单路径保持
Third-party local trees	受治理的依赖/构建产物	锁版本、SBOM、许可记录	禁止直接修改上游源码
5_deploy	iac + CI + scripts	部署资产归位	不把部署误放到 integrations
1.  Technical Debt
P0：必须在功能迁移前处理
FinancePy GPL 许可决策尚未完成。
ORE 的 QuantLib/QuantLib-SWIG 子模块缺失。
三方源码被 Git 忽略，构建不可重复。
Processing 仍有旧表名读写。
Unified 模式可能直接暴露内部 /processing、/entry、/mcp。
MCP Gateway 缺实际鉴权。
Agent 测试目录存在硬编码外部 API Key 风险。
P1：RiskEngine 建设前处理
没有统一 PortfolioSnapshot。
没有统一 MarketSnapshot。
市场数据 fallback 在多个模块重复。
Traditional Risk 与 Risk Testing 双栈。
VaR、PnL、回测和风险度量定义重复。
Compliance 规则在 Backend/Processing/Frontend/AutoRisk 分散。
调度线程和 Celery Beat 并存。
IAM 菜单和 fsi.para_menu 双体系。
fsiClient.ts 过大。
子菜单权限没有独立过滤。
P2：后续治理
Agent V1/V2 并存。
Backend、Entry、MCP 多条代理路径重复。
Wind MCP 仍有 mock。
报表使用 subprocess 和文件状态，缺通用 Job Store。
Backend 测试依赖开发数据库。
Skills、MCP、Entry、Platform Agent 测试不足。
FinancePy、Riskfolio、ORE 自身均存在版本或文档不一致。
数据库附件使用 BYTEA，可能引发膨胀。
1.  Migration Risks
风险	等级	控制措施
FinancePy GPL 影响闭源分发	极高	法务评估；进程隔离不能替代法律判断
ORE 构建链和 C++ ABI	高	先 Sidecar/Batch，不直接嵌入
数值结果漂移	高	Golden portfolio、双算、容差和差异报告
当前路由被破坏	高	Backend Compatibility Facade + Contract Tests
持仓/NAV 口径变化	高	先建立 Snapshot Contract 和对账规则
合规规则口径变化	高	单一服务端规则事实源、双轨比对
Solver 不可用或结果不稳定	高	Solver 白名单、超时、fallback、元数据披露
ORE 市场数据映射错误	高	曲线、日历、币种和单位级 Validation
调度重复执行	高	Job ID、幂等键、数据库锁、单一 Scheduler
Agent 绕过业务权限	高	Agent 只调用受授权 Business API
内部服务路径外泄	高	网关级路径隔离与服务身份认证
第三方升级破坏 API	中高	Adapter、版本锁定、回归基线
数据迁移期间新旧表双写不一致	中高	禁止长期双写；短期 shadow-read + reconcile
一次性目录重构导致大爆炸	高	Strangler Migration，不直接移动全部文件
报表与审核链中断	高	把 /reports、/schedules、/autorisk 设为迁移阻断测试
1.  Recommended Wave Sequence
Wave 0：Architecture Understanding
本轮完成：

当前架构盘点
菜单、API、数据库和计算图
三方源码定位
许可与依赖风险识别
Current → Target 初步映射
本轮不实施任何改动。

Wave 1：Baseline Contracts and Characterization
目标：

冻结现有 API/OpenAPI。
建立菜单、路由、数据库查询和风险结果基线。
为 /reports、/schedules、/autorisk 建立阻断性回归测试。
建立 Golden Portfolio 与 Golden Market Snapshot。
明确数值容差和模型验证标准。
Gate：

所有现有功能可重复验证。
不改变 API 响应结构。
Wave 2：Licensing and Dependency Governance
目标：

完成 FinancePy GPL 法务决策。
明确三方源码获取方式、版本锁定和 SBOM。
补齐 ORE 子模块来源与版本。
确定 Riskfolio Solver 白名单。
禁止继续依赖本地 gitignored 源码作为隐式构建输入。
Gate：

三个项目均有版本、许可证、来源和构建策略。
Wave 3：Canonical Data Contracts
目标：

定义 Portfolio、Position、Market、Instrument、Scenario、Result 合同。
定义单位、币种、日期、时区、估值时点和数据质量语义。
不迁移算法，先让旧模块输出/接受统一合同。
Gate：

同一个组合在旧路径和合同路径可以完整对账。
Wave 4：RiskEngine Foundation
目标：

建立 3_riskengine 的 Contracts、Validation、Diagnostics、Lineage。
建立 Engine Registry 和 Adapter 接口。
原有算法仍通过兼容 Adapter 使用。
Gate：

RiskEngine 不依赖 Frontend、Backend 或 Agent。
第三方类不泄漏到业务 API。
Wave 5：Market and Portfolio Unification
目标：

建立单一 Portfolio Snapshot Loader。
建立单一 Market Data Adapter。
统一 DB、Wind、OpenBB、yfinance 和 proxy 的 fallback 政策。
消除前端持仓 fallback。
Gate：

Position、Risk Testing、Optimization 使用相同快照。
Wave 6：FinancePy Adapter Migration
目标：

将标准定价、曲线、Greeks、DV01/KRD 逐步转给 FinancePy Adapter。
保留 ARISK 场景、聚合、限额和治理。
旧 Risk Testing 与新 Adapter 双算。
Gate：

Golden Portfolio 在容差内一致。
License Gate 已通过。
Wave 7：Riskfolio Adapter and Portfolio Optimization
目标：

引入 Riskfolio Adapter。
保留现有 PyPortfolioOpt Adapter 作为对照和 fallback。
统一约束、风险度量、Solver Policy 与审计元数据。
Gate：

现有 /portfolio-opt 页面和 API 不改变。
相同输入结果可重现。
Wave 8：ORE Integration Proof of Concept
目标：

优先建立 ORE 独立进程 Adapter。
实现最小 Trade/Market XML 映射。
验证 Pricing、Scenario、Exposure、XVA 的一个 Golden Case。
不立即替换当前 XVA。
Gate：

QuantLib/ORE 构建可重复。
C++ 崩溃不会影响主 API。
结果和 ORE 官方 Example 对账。
Wave 9：Business Domain Extraction
顺序建议：

Portfolio Management
Investment Risk
Portfolio Optimization
Risk Testing
Trading
每个域采用：

禁止直接批量移动全部目录。

Wave 10：Workflow Consolidation
目标：

统一 Reports Job。
统一 Scheduler。
统一 Review State Machine。
建立 AutoRisk 与主风险结果的关联 ID。
保留 /reports、/schedules、/autorisk。
Wave 11：Frontend and AI Alignment
目标：

按业务域拆分 fsiClient。
子菜单独立权限与发布阶段。
Agent 只通过 Business API。
3_skills、aiagent、platform_agent 逐步归入 7_ai。
MCP 归入 5_integrations。
Wave 12：Hardening and Controlled Deprecation
目标：

删除已确认无调用的旧表路径。
收敛 Agent V1。
收敛双菜单系统。
禁止内部服务直接暴露。
性能、容量、审计、灾备和模型治理验收。
任何删除都必须在：

调用方为零；
合同测试通过；
数据已对账；
路由已有兼容期；
之后才能进行。

最终架构结论
ARISK 不应演变成“三个开源项目的简单集合”，也不应继续让各业务模块直接调用不同计算库。

正确边界是：
ARISK Business Domain
        ↓
ARISK RiskEngine
        ↓
Adapter / Model Governance / Validation
        ↓
FinancePy | Riskfolio-Lib | ORE

三套引擎职责应明确：

FinancePy：标准金融产品、曲线、定价和基础敏感度。
Riskfolio-Lib：组合风险、组合优化、约束和因子模型。
ORE：复杂衍生品、场景、Exposure、Counterparty、XVA、SIMM。
ARISK RiskEngine：统一合同、数据快照、风险因子、聚合、场景治理、限额、验证、审计与模型选择。
现有 MMF、数据管理、驾驶舱、持仓、估值、报表、调度、AutoRisk、Agent Chat、知识库、MCP、合规、规则、权限、审计和人工审核全部保留；迁移过程中现有路由尤其 /reports、/schedules、/autorisk 必须作为兼容性红线。

本 Wave 到此

##
现在执行 Wave 1。

目标：

> 将当前 ARISK 前端菜单从“功能平铺”升级为“核心业务域 + 平台能力”的结构。

---

# 一、重要原则

本 Wave：

> 主要修改 Frontend 菜单组织和页面业务归属。

不要进行大规模后端架构重构。

不要移动第三方源码。

不要修改数据库结构。

不要因为菜单变化删除现有功能。

---

# 二、三个核心业务域

一级核心业务必须为：

```text
投资风险分析
组合配置与优化
风险测试
```

---

# 三、最终一级菜单

建议调整为：

```text
仪表板
组合驾驶舱

投资风险分析
组合配置与优化
风险测试

数据管理中心
市场数据与指标
估值与损益
交易管理

风险治理

报表中心
定时任务
自动风控

Agent / AI

系统管理
```

---

# 四、必须保留的一级菜单

以下现有一级菜单继续保留：

```text
报表中心
定时任务
自动风控
```

对应：

```text
/reports
/schedules
/autorisk
```

不要隐藏。

不要删除。

不要合并成不可见后台功能。

---

# 五、投资风险分析

菜单：

```text
投资风险分析
├── 模块总览
├── 组合概况
├── 风险指标
├── 风险暴露
├── 因子风险
├── 市场风险
├── 利率与信用风险
├── 外汇与资产风险
├── 流动性风险
├── 集中度风险
├── 交易对手风险
├── 杠杆与衍生品风险
├── 绩效与 PnL 归因
├── 风险预算
├── 宏观与市场动态
└── 基本面因子与行为
```

---

# 六、组合配置与优化

名称由：

```text
组合优化
```

升级为：

```text
组合配置与优化
```

保留现有：

```text
/portfolio-opt
```

子菜单：

```text
模块总览
组合构建
SAA
TAA
风险预算
风险平价
Black-Litterman
HRP / HERC
CVaR 优化
因子约束
流动性约束
集中度约束
杠杆约束
换手率约束
模拟组合
组合验证
```

---

# 七、风险测试

保留：

```text
/risk-testing/*
```

继续：

```text
风险测试
├── 敏感度测试
├── 压力测试
├── 情景测试
├── 反向压力测试
├── 尾部风险测试
├── 关键利率久期 KRD
├── PnL 归因
├── 历史收益回测
├── VaR 回测
└── 估值调整 XVA
```

后续预留：

```text
流动性压力测试
赎回压力测试
保证金压力测试
交易对手压力测试
```

---

# 八、平台基础能力

保持：

```text
数据管理中心
市场数据与指标
估值与损益
交易管理
```

---

# 九、风险治理

将以下业务归入 Risk Governance：

```text
风险限额
风险预警
风险违规
例外管理
升级与处置
风险政策
模型验证
估值控制
流动性治理
合规核查
风险报告
```

原 route 保持兼容：

```text
/compliance
/risk-rules
/reports
```

---

# 十、AI

组织：

```text
Agent / AI
├── AI Risk Copilot
├── Investment Agent
├── Portfolio Agent
├── Risk Agent
├── Valuation Agent
├── Workflow Agent
├── Agent Chat
└── 专家知识库
```

现有 `/chat` 必须继续工作。

---

# 十一、权限

继续使用当前：

```text
menu_paths
menu_stages
```

以及已有角色和 portfolio authorization。

不要重新设计权限体系。

---

# 十二、route 兼容

必须保证：

```text
/investment-risk/*
/risk-testing/*
/portfolio-opt
/reports
/schedules
/autorisk
/valuation
/compliance
/risk-rules
```

继续可访问。

---

# 十三、实施

先修改：

```text
AppSidebar.tsx
```

然后根据真实 route tree 调整菜单映射。

不要大规模重命名页面文件。

---

# 十四、验收

测试：

* Sidebar；
* Navigation；
* Route；
* Deep Link；
* Refresh；
* Permission；
* Admin；
* Normal User；
* menu_paths；
* menu_stages；
* Beta。

并输出：

```text
Changed Files
New Files
Route Changes
Menu Changes
Permission Changes
Tests
Test Results
```
## WAVE2

现在执行 Wave 2。

目标：

> 将当前 ARISK 仓库逐步调整为 Target Architecture。

---

# 一、核心要求

采用：

> Incremental Migration / Strangler Pattern

禁止：

> 一次性移动、重命名、删除大量文件。

---

# 二、目标目录

逐步形成：

```text
arisk/
├── 1_datastorage/
├── 2_processing/
├── 3_riskengine/
├── 4_business/
│   ├── investment_risk/
│   ├── portfolio_optimization/
│   ├── risk_testing/
│   ├── portfolio_management/
│   └── trading/
├── 5_integrations/
├── 6_entry/
├── 7_ai/
├── backend/
├── frontend/
├── docs/
├── scripts/
├── tests/
└── artefacts/
```

---

# 三、建立 3_riskengine

创建：

```text
3_riskengine/
├── core/
├── adapters/
├── valuation/
├── instruments/
├── market/
├── risk/
├── stress/
├── scenario/
├── liquidity/
├── counterparty/
├── pnl/
├── limits/
├── validation/
└── tests/
```

这一 Wave：

> 先建立目录和 package skeleton。

不要把所有旧金融代码立即搬进去。

---

# 四、建立 4_business

创建：

```text
4_business/
├── investment_risk/
├── portfolio_optimization/
├── risk_testing/
├── portfolio_management/
└── trading/
```

建立 README / moduleinfo / package skeleton。

---

# 五、旧目录处理

当前：

```text
2_processing/tools/
```

暂时保留。

开始建立：

```text
legacy/
compatibility/
adapter/
```

或者使用其他清晰的兼容方式。

目标：

```text
Old
 ↓
Compatibility
 ↓
New
```

---

# 六、skills / agent

暂时不要删除：

```text
3_skills/
aiagent/
platform_agent/
```

先建立目标：

```text
7_ai/
├── agents/
├── skills/
├── tools/
├── workflows/
└── knowledge/
```

后续逐步迁移。

---

# 七、MCP

当前：

```text
4_mcp/
```

暂时保留。

目标以后逐步向：

```text
5_integrations/
```

演进。

但不要因为目录调整破坏现有 MCP。

---

# 八、autorisk

保留：

```text
autorisk/
```

暂时不要删除。

未来作为：

```text
Risk Workflow / Automation
```

逐步迁移。

---

# 九、Backend

保留：

```text
backend/
```

不进行大规模重构。

本 Wave 只建立目标业务目录接口，不把金融计算搬入 backend。

---

# 十、Frontend

保留：

```text
frontend/
```

按照 Wave 1 的新菜单结构逐步整理 modules。

重点：

```text
investment-risk/
portfolio-optimization/
risk-testing/
```

当前：

```text
portfolio-opt/
```

可以保留 route，内部逐步重组。

---

# 十一、必须保持兼容

以下不能因为移动文件而失效：

```text
API
imports
routes
reports
schedules
autorisk
agent
MCP
tests
```

必要时建立 compatibility imports。

---

# 十二、测试

每次文件迁移后执行：

```text
Import Test
Unit Test
API Test
Frontend Build
Route Test
```

不得在测试失败时继续大量迁移。

---

# 十三、文档

更新：

```text
docs/current_platform_directory_tree.md
```

但不要把 Current 和 Target 混在一起。

新增：

```text
docs/target_platform_directory_tree.md
docs/architecture_migration_map.md
```

完成本 Wave。

## WAVE 3
现在执行 Wave 3。

这是 ARISK 金融计算核心架构的第一阶段。

目标：

```text
第三方源码隔离
→ RiskEngine
→ Unified Valuation
→ Risk Testing
```

---

# 一、第三方项目隔离

项目当前已经存放：

```text
FinancePy
Riskfolio-Lib
OpenSourceRisk / ORE
```

源码。

必须明确识别：

```text
第三方源码
```

与：

```text
ARISK 自有源码
```

的边界。

---

# 二、第三方源码原则

默认：

> 不修改第三方源码。

优先使用：

* import
* composition
* subclass
* adapter
* plugin
* configuration
* wrapper

进行二次开发。

只有确实无法通过外部扩展实现，才可以修改第三方源码。

任何修改必须记录：

```text
Project
Version
File
Modification
Reason
Impact
Patch
```

建立：

```text
docs/third_party_patches.md
```

---

# 三、RiskEngine

正式启用：

```text
3_riskengine/
```

结构：

```text
3_riskengine/
├── core/
├── adapters/
│   ├── financepy/
│   ├── riskfolio/
│   └── ore/
├── valuation/
├── instruments/
├── market/
├── risk/
├── stress/
├── scenario/
├── liquidity/
├── counterparty/
├── pnl/
├── limits/
├── validation/
└── tests/
```

---

# 四、RiskEngine 定位

RiskEngine 是：

> ARISK 自主的统一 Quantitative Finance & Risk Engine。

它不是第三方库的简单 wrapper。

它负责：

```text
统一对象
统一接口
统一估值
统一风险因子
统一情景
统一风险结果
统一验证
```

---

# 五、Engine Adapter

建立：

```text
FinancePyAdapter
RiskfolioAdapter
OREAdapter
```

禁止业务模块直接散落：

```python
import financepy
import riskfolio
import ore
```

业务模块统一调用：

```python
riskengine
```

---

# 六、统一核心对象

至少定义：

```text
Instrument
Portfolio
Position
MarketSnapshot
ValuationContext
RiskFactor
Scenario
RiskResult
ValuationResult
StressResult
ValidationResult
```

---

# 七、统一估值接口

建立：

```python
valuation.price()
valuation.revalue()
valuation.greeks()
valuation.pnl()
```

不同资产根据支持能力调用：

```text
Market Price
FinancePy
ORE
```

---

# 八、固定收益

优先使用项目已经指定的 FinancePy：

```text
FlatDiscountCurve
```

兼容旧：

```text
DiscountCurveFlat
```

所有估值报告必须记录：

```text
Valuation Date
Market Data Date
Curve
Model
Assumption
Engine Version
```

---

# 九、统一 Risk Interface

建立：

```python
risk.calculate()
risk.exposure()
risk.sensitivity()
risk.stress()
risk.scenario()
```

---

# 十、Risk Testing

正式迁移到：

```text
4_business/risk_testing/
```

实现：

```text
sensitivity
stress
scenario
reverse_stress
tail_risk
krd
pnl_explain
historical_backtest
var_backtest
xva
```

严格按照：

```text
docs/risk-testing.md
```

实施。

不得无理由改变原业务需求。

---

# 十一、Risk Testing 引擎关系

```text
Risk Testing
     ↓
RiskEngine
     ↓
┌───────────────┬───────────────┐
│               │               │
FinancePy    Riskfolio-Lib      ORE
```

具体：

### Sensitivity

FinancePy + RiskEngine。

### Stress

FinancePy / ORE + RiskEngine。

### Scenario

RiskEngine Scenario Engine。

### Reverse Stress

RiskEngine numerical search。

### Tail Risk

RiskEngine + statistical library。

### KRD

FinancePy revaluation。

### PnL Explain

RiskEngine PnL。

### Historical Backtest

统一历史数据。

### VaR Backtest

Riskfolio + RiskEngine。

### XVA

ORE + RiskEngine。

---

# 十二、数据

继续使用现有：

```text
fsi.balance_*
fsi.mktdata_*
```

不得创建第二套 Portfolio / Position / Market Data 主数据。

---

# 十三、现有 API

必须保持兼容：

```text
/api/v1/fsi/risk-testing/*
```

如果内部实现变化，通过 adapter 保持 API contract。

---

# 十四、Validation

建立：

```text
riskengine/validation/
```

至少：

```text
Pricing Validation
Greeks Validation
Risk Validation
Regression
Reconciliation
```

每次结果必须能够说明：

```text
Engine
Engine Version
Model
Model Version
Parameters
Assumptions
Data Quality
```

---

# 十五、测试

必须建立：

* Unit Test
* Deterministic Test
* Regression Test
* API Test
* Data Quality Test
* Cross Engine Validation Test

尤其对：

```text
FinancePy
Riskfolio-Lib
ORE
```

各建立最小 deterministic sample。

---

# 十六、完成标准

只有满足以下条件才允许标记完成：

```text
RiskEngine can import
+
Adapters can initialize
+
Valuation API works
+
Risk Testing works
+
Existing API works
+
Existing routes work
+
Existing tests pass
```

否则继续修复，不进入下一 Wave。


## WAVE 4
现在执行 Wave 4。

目标：

建立 ARISK 第一大核心业务域：

> Investment Risk Analytics

目录：

```text
4_business/investment_risk/
```

---

# 一、模块

```text
investment_risk/
├── overview/
├── exposure/
├── market_risk/
├── factor_risk/
├── rates_credit/
├── fx/
├── liquidity/
├── concentration/
├── counterparty/
├── leverage/
├── pnl_attribution/
├── risk_budget/
├── macro_dynamics/
└── factor_behavior/
```

---

# 二、核心 Risk KPI

实现：

```text
VaR
CVaR
ES
Volatility
Drawdown
Beta
Tracking Error
Risk Contribution
Gross Exposure
Net Exposure
Factor Exposure
Duration
DV01
KRD
CS01
Liquidity
Concentration
Counterparty Exposure
PFE
EPE
Leverage
```

---

# 三、引擎

统一：

```text
Business
 ↓
RiskEngine
 ↓
FinancePy / Riskfolio / ORE
```

---

# 四、数据

继续使用现有统一 Portfolio / Position / Market Data。

---

# 五、当前 route

继续兼容：

```text
/investment-risk/*
```

---

# 六、测试

每个 Risk KPI 必须具备：

```text
Input
Calculation
Engine
Formula / Method
Result
Data Quality
```

并建立 regression tests。

## WAVE 5
现在执行 Wave 5。

建立：

```text
4_business/portfolio_optimization/
```

---

# 一、功能

```text
construction
SAA
TAA
risk_budget
risk_parity
black_litterman
hrp
herc
cvar
constraints
liquidity
turnover
simulation
validation
```

---

# 二、核心引擎

主要：

```text
Riskfolio-Lib
```

通过：

```text
riskengine.adapters.riskfolio
```

调用。

---

# 三、优化结果必须经过

```text
Optimization
↓
RiskEngine
↓
Valuation
↓
Investment Risk
↓
Risk Testing
↓
Limits
```

不得把优化结果直接作为交易指令。

---

# 四、Simulation Portfolio

支持：

```text
Live Portfolio
↓
Clone
↓
Simulation Portfolio
↓
Modify
↓
Optimize
↓
Stress
↓
Compare
```

未经授权不得修改 Live Portfolio。

---

# 五、测试

验证：

* Optimization
* Constraints
* Risk Budget
* Risk Contribution
* Simulation
* Validation
* Persistence
* Compare

## WAVE 6
现在执行 Wave 6。

目标：

建立：

```text
Risk Governance
+
Risk Limits
+
Pre-Trade Risk
```

---

# 一、Limits

统一由：

```text
3_riskengine/limits/
```

管理。

支持：

```text
Position
Issuer
Sector
Country
Currency
Counterparty
Gross Exposure
Net Exposure
Leverage
Liquidity
VaR
CVaR
Drawdown
Derivative Exposure
```

---

# 二、Limit States

```text
GREEN
WARNING
BREACH
HARD_BREACH
```

---

# 三、Governance

```text
4_business/risk_governance/
```

包括：

```text
Risk Policy
Risk Appetite
Risk Limits
Breach
Exception
Escalation
Action
Approval
Closure
Model Validation
Valuation Control
Audit
```

---

# 四、Pre-Trade

```text
POST /api/v1/risk/pre-trade
```

流程：

```text
Order
↓
Current Portfolio
+
Proposed Trade
↓
Valuation
↓
Risk
↓
Stress
↓
Liquidity
↓
Concentration
↓
Counterparty
↓
Limit
↓
APPROVE / WARNING / REJECT
```

---

# 五、必须接入

```text
Investment Risk
Portfolio Optimization
Risk Testing
```

三者使用同一个 Limit Engine。

---

# 六、测试

建立：

```text
Limit Tests
Boundary Tests
Breach Tests
Pre-Trade Tests
Authorization Tests
Audit Tests
```

# WAVE 7
现在执行 Wave 7。

目标：

让 ARISK 从 Risk Platform 向 Investment / Quant / Trading / Operations 延伸。

---

# 一、建立 Integration Layer

```text
5_integrations/
├── market_data/
├── pms/
├── oms/
├── ems/
├── broker/
├── custodian/
├── fund_admin/
├── accounting/
└── quant/
```

---

# 二、所有外部系统使用 Adapter

禁止 Business Domain 直接调用外部系统。

统一：

```text
External
↓
Adapter
↓
ARISK Data Contract
↓
RiskEngine / Business
```

---

# 三、Quant API

支持：

```python
risk.portfolio()
risk.exposure()
risk.var()
risk.cvar()
risk.stress()
risk.liquidity()
risk.counterparty()

portfolio.optimize()
portfolio.simulate()

valuation.price()

testing.run()
```

支持：

```text
Python
Jupyter
CLI
REST
```

---

# 四、Trading

支持：

```text
Order
Execution
Position
PreTrade Risk
PostTrade Risk
```

---

# 五、Operations

逐步连接：

```text
Valuation
NAV
PnL
Fund Accounting
Custodian
Fund Administrator
```

---

# 六、测试

验证：

* API Contract；
* Adapter；
* Auth；
* Permission；
* Data Integrity；
* Failure Handling；
* Retry；
* Audit。

## WAVE 7
现在执行 Wave 7。

目标：

让 ARISK 从 Risk Platform 向 Investment / Quant / Trading / Operations 延伸。

---

# 一、建立 Integration Layer

```text
5_integrations/
├── market_data/
├── pms/
├── oms/
├── ems/
├── broker/
├── custodian/
├── fund_admin/
├── accounting/
└── quant/
```

---

# 二、所有外部系统使用 Adapter

禁止 Business Domain 直接调用外部系统。

统一：

```text
External
↓
Adapter
↓
ARISK Data Contract
↓
RiskEngine / Business
```

---

# 三、Quant API

支持：

```python
risk.portfolio()
risk.exposure()
risk.var()
risk.cvar()
risk.stress()
risk.liquidity()
risk.counterparty()

portfolio.optimize()
portfolio.simulate()

valuation.price()

testing.run()
```

支持：

```text
Python
Jupyter
CLI
REST
```

---

# 四、Trading

支持：

```text
Order
Execution
Position
PreTrade Risk
PostTrade Risk
```

---

# 五、Operations

逐步连接：

```text
Valuation
NAV
PnL
Fund Accounting
Custodian
Fund Administrator
```

---

# 六、测试

验证：

* API Contract；
* Adapter；
* Auth；
* Permission；
* Data Integrity；
* Failure Handling；
* Retry；
* Audit。

## WAVE 8
现在执行 Wave 8。

目标：

让 Agent 成为 ARISK 的统一自然语言与 Workflow Interface。

---

# 一、Agent

建立：

```text
7_ai/
├── agents/
│   ├── investment_agent/
│   ├── portfolio_agent/
│   ├── risk_agent/
│   ├── valuation_agent/
│   └── workflow_agent/
├── skills/
├── tools/
├── workflows/
└── knowledge/
```

---

# 二、Agent 调用链

```text
User
↓
Agent
↓
Intent
↓
Tool
↓
Business API
↓
RiskEngine
↓
FinancePy / Riskfolio / ORE
↓
Result
↓
Agent Explanation
```

---

# 三、禁止

Agent 不得直接计算：

```text
NAV
VaR
PnL
Stress Loss
Valuation
Risk Limit
```

---

# 四、Portfolio Agent

所有组合修改：

```text
Live Portfolio
```

之前先：

```text
Simulation Portfolio
```

---

# 五、权限

Agent 不得绕过：

```text
JWT
Role
Portfolio Authorization
API Authorization
Audit
```

---

# 六、MCP

MCP 是：

> Tool Connectivity Layer

继续支持：

* Market Data
* Portfolio
* Risk
* Valuation
* SQL

不得取代 RiskEngine。

---

# 七、测试

验证：

```text
Agent
Tool Use
Streaming
Context
Permission
Risk Result
Audit
Failure Handling
```

## WAVE 9
现在执行 Wave 9。

目标：

把已经完成的后端能力统一呈现为 ARISK Institutional Investment & Risk Platfo--

# 一、一级菜单最终确认

```text
仪表板
组合驾驶舱

投资风险分析
组合配置与优化
风险测试

数据管理中心
市场数据与指标
估值与损益
交易管理

风险治理

报表中心
定时任务
自动风控

Agent / AI

系统管理
```

---

# 二、所有核心业务使用统一 UI

```text
Parameter
↓
Data / Table
↓
Charts / Analytics
↓
AI Copilot
```

---

# 三、Investment Risk

统一：

```text
Overview
Exposure
Factor
Market Risk
Rates / Credit
FX
Liquidity
Concentration
Counterparty
Leverage
PnL
Risk Budget
Macro
Factors
```

---

# 四、Portfolio Optimization

统一：

```text
Construction
Optimization
Constraints
Simulation
Comparison
Validation
```

---

# 五、Risk Testing

统一：

```text
Sensitivity
Stress
Scenario
Reverse Stress
Tail Risk
KRD
PnL Explain
Historical Backtest
VaR Backtest
XVA
```

---

# 六、AI Copilot

当前页面上下文至少包括：

```text
Portfolio
Date
Current Module
Current Result
Current Chart
Risk Metrics
```

Agent 根据上下文调用对应 API。

---

# 七、UI 不得承担金融计算

所有金融结果来自：

```text
RiskEngine
```

Frontend 只负责：

```text
Input
API
Visualization
Interaction
```

---

# 八、验收

检查：

* Responsive Layout
* Loading
* Error
* Empty State
* Permission
* Route
* Deep Link
* Chart
* Table
* Export
* AI Context

## WAVE 10 最終
现在执行最终 Wave。

目标：

确认 ARISK 已经形成：

> Institutional Investment & Risk Platform

---

# 一、完整业务链路

验证：

```text
Market Data
↓
Portfolio
↓
Position
↓
Valuation
↓
Investment Risk
↓
Portfolio Optimization
↓
Simulation
↓
Risk Testing
↓
Limits
↓
Pre-Trade
↓
Trading
↓
Position
↓
Valuation
↓
Continuous Risk
```

---

# 二、RiskEngine

全面测试：

```text
FinancePy Adapter
Riskfolio Adapter
ORE Adapter

Valuation
Risk
Stress
Scenario
Liquidity
Counterparty
PnL
Limits
Validation
```

---

# 三、三个核心业务

完整验证：

```text
Investment Risk Analysis
Portfolio Construction & Optimization
Risk Testing
```

---

# 四、数据

验证：

```text
Market
Portfolio
Position
Trade
Valuation
NAV
PnL
Risk
```

不存在重复主数据。

---

# 五、现有功能回归

必须保持：

```text
MMF
Data Management
Portfolio Cockpit
Positions
Valuation
Reports
Schedules
AutoRisk
Agent
MCP
Compliance
Risk Rules
Auth
Audit
Human Review
```

---

# 六、第三方源码

检查：

```text
FinancePy
Riskfolio-Lib
ORE
```

确认：

* 未进行无必要修改；
* 所有修改都有 patch；
* 所有修改都有 documentation；
* 所有版本都有记录。

---

# 七、API

验证：

* Existing API
* New API
* Compatibility
* Authentication
* Authorization

---

# 八、Frontend

验证：

* Sidebar
* Routes
* Permission
* Deep Link
* Refresh
* Beta
* ACTIVE / HIDDEN

---

# 九、测试

运行：

```text
Unit Tests
Integration Tests
Regression Tests
API Tests
Frontend Tests
Engine Tests
Data Tests
Security Tests
```

---

# 十、性能

至少检查：

```text
Valuation Time
Risk Calculation Time
Stress Time
Optimization Time
API Latency
Database Query
Memory
Background Jobs
```

---

# 十一、最终报告

生成：

```text
ARISK Platform V2 Final Validation Report
```

包括：

1. Architecture
2. Business Modules
3. RiskEngine
4. FinancePy
5. Riskfolio-Lib
6. ORE
7. Data
8. Valuation
9. Risk
10. Stress
11. Portfolio Optimization
12. Governance
13. API
14. Frontend
15. Agent
16. Integration
17. Security
18. Regression
19. Performance
20. Technical Debt
21. Remaining Work
22. Production Readiness

只有实际运行测试通过后，才允许标记：

```text
READY
```

不得根据源码阅读或静态分析直接宣布完成。
