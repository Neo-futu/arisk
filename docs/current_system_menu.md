<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# 当前系统菜单与全部子菜单

本文档描述 arisk **当前**前端侧边栏的实际结构（Current）。目标架构目录见 [`target_platform_directory_tree.md`](target_platform_directory_tree.md)，不要与本文混读。

判定口径：

1. 以 `frontend/src/components/Sidebar/AppSidebar.tsx` 中的菜单定义为准。
2. 实际用户可见菜单，还会受到 `my-access-context` 返回的 `menu_paths` 与 `menu_stages` 过滤。
3. 超级管理员可预览除 `HIDDEN` 之外的菜单；普通用户只能看到已授权路径。
4. 权限仍按现有 route 路径（如 `/portfolio-opt`、`/chat`）判定，不按菜单显示名判定。
5. `1_datastorage/postgres/schema/011_user_menu.sql` 中的 `fsi.para_menu` 属于另一套历史/数据侧菜单配置，不等同于当前 React 侧边栏。

## 一、业务菜单（FSI Section）

| 一级菜单 | 路径 | 子菜单 | 子菜单路径 | 说明 |
|---|---|---|---|---|
| 仪表板 | `/` | - | - | 系统首页 |
| 组合驾驶舱 | `/portfolio-cockpit` | - | - | 组合总览与驾驶舱 |
| 投资风险分析 | `/investment-risk` | 模块总览 | `/investment-risk` | 父级点击展开 |
| 投资风险分析 | `/investment-risk` | 组合概况 | `/investment-risk/overview` |  |
| 投资风险分析 | `/investment-risk` | 风险指标 | `/investment-risk/indicators` |  |
| 投资风险分析 | `/investment-risk` | 风险暴露 | `/investment-risk/indicators#risk-exposure` | 锚点，页面文件未拆分 |
| 投资风险分析 | `/investment-risk` | 因子风险 | `/investment-risk/factor-behavior#factor-risk` |  |
| 投资风险分析 | `/investment-risk` | 市场风险 | `/investment-risk/macro-dynamics#market-risk` |  |
| 投资风险分析 | `/investment-risk` | 利率与信用风险 | `/investment-risk/rates-credit` |  |
| 投资风险分析 | `/investment-risk` | 外汇与资产风险 | `/investment-risk/overview#asset-risk` |  |
| 投资风险分析 | `/investment-risk` | 流动性风险 | `/investment-risk/liquidity-stress` |  |
| 投资风险分析 | `/investment-risk` | 集中度风险 | `/investment-risk/rates-credit#concentration-risk` |  |
| 投资风险分析 | `/investment-risk` | 交易对手风险 | `/investment-risk/rates-credit#counterparty-risk` |  |
| 投资风险分析 | `/investment-risk` | 杠杆与衍生品风险 | `/investment-risk/indicators#leverage-derivatives-risk` |  |
| 投资风险分析 | `/investment-risk` | 绩效与 PnL 归因 | `/investment-risk/attribution` |  |
| 投资风险分析 | `/investment-risk` | 风险预算 | `/investment-risk/pretrade-budget#risk-budget` |  |
| 投资风险分析 | `/investment-risk` | 宏观与市场动态 | `/investment-risk/macro-dynamics` |  |
| 投资风险分析 | `/investment-risk` | 基本面因子与行为 | `/investment-risk/factor-behavior` |  |
| 组合配置与优化 | `/portfolio-opt` | 模块总览 | `/portfolio-opt#overview` | 路由仍为 `/portfolio-opt` |
| 组合配置与优化 | `/portfolio-opt` | 组合构建 | `/portfolio-opt#parameters` |  |
| 组合配置与优化 | `/portfolio-opt` | SAA | `/portfolio-opt#return-models` |  |
| 组合配置与优化 | `/portfolio-opt` | TAA | `/portfolio-opt#return-models` |  |
| 组合配置与优化 | `/portfolio-opt` | 风险预算 | `/portfolio-opt#asset-metrics` |  |
| 组合配置与优化 | `/portfolio-opt` | 风险平价 | `/portfolio-opt#portfolios` |  |
| 组合配置与优化 | `/portfolio-opt` | Black-Litterman | `/portfolio-opt#return-models` |  |
| 组合配置与优化 | `/portfolio-opt` | HRP / HERC | `/portfolio-opt#portfolios` |  |
| 组合配置与优化 | `/portfolio-opt` | CVaR 优化 | `/portfolio-opt#asset-metrics` |  |
| 组合配置与优化 | `/portfolio-opt` | 因子约束 | `/portfolio-opt#parameters` |  |
| 组合配置与优化 | `/portfolio-opt` | 流动性约束 | `/portfolio-opt#parameters` |  |
| 组合配置与优化 | `/portfolio-opt` | 集中度约束 | `/portfolio-opt#parameters` |  |
| 组合配置与优化 | `/portfolio-opt` | 杠杆约束 | `/portfolio-opt#parameters` |  |
| 组合配置与优化 | `/portfolio-opt` | 换手率约束 | `/portfolio-opt#parameters` |  |
| 组合配置与优化 | `/portfolio-opt` | 模拟组合 | `/portfolio-opt#user-weights` |  |
| 组合配置与优化 | `/portfolio-opt` | 组合验证 | `/portfolio-opt#charts` |  |
| 风险测试 | `/risk-testing` | 敏感度测试 | `/risk-testing/sensitivity` |  |
| 风险测试 | `/risk-testing` | 压力测试 | `/risk-testing/stress` |  |
| 风险测试 | `/risk-testing` | 情景测试 | `/risk-testing/scenario` |  |
| 风险测试 | `/risk-testing` | 反向压力测试 | `/risk-testing/reverse-stress` |  |
| 风险测试 | `/risk-testing` | 尾部风险测试 | `/risk-testing/tail-risk` |  |
| 风险测试 | `/risk-testing` | 关键利率久期 KRD | `/risk-testing/krd` |  |
| 风险测试 | `/risk-testing` | PnL 归因 | `/risk-testing/pnl-explain` |  |
| 风险测试 | `/risk-testing` | 历史收益回测 | `/risk-testing/historical-backtest` |  |
| 风险测试 | `/risk-testing` | VaR 回测 | `/risk-testing/var-backtest` |  |
| 风险测试 | `/risk-testing` | 估值调整 XVA | `/risk-testing/xva` |  |
| 风险测试 | `/risk-testing` | 流动性压力测试 | - | 规划中，disabled |
| 风险测试 | `/risk-testing` | 赎回压力测试 | - | 规划中，disabled |
| 风险测试 | `/risk-testing` | 保证金压力测试 | - | 规划中，disabled |
| 风险测试 | `/risk-testing` | 交易对手压力测试 | - | 规划中，disabled |
| 数据管理中心 | `/data-management` | 数据工作台 | `/data-management` | permissionPaths 含 `/positions` |
| 数据管理中心 | `/data-management` | 持仓明细 | `/positions` |  |
| 市场数据与指标 | `/indicator-explorer` | 市场数据 | `/data-management?section=market` |  |
| 市场数据与指标 | `/indicator-explorer` | 指标探索 | `/indicator-explorer` |  |
| 市场数据与指标 | `/indicator-explorer` | SQL 资产库 | `/sql-library` |  |
| 估值与损益 | `/valuation` | - | - |  |
| 交易管理 | `/data-management?section=trades` | - | - | 权限路径仍为 `/data-management` |
| 风险治理 | `/risk-governance` | 风险限额 | `/risk-rules#limits` | 父路径无独立页面；权限用现有 route |
| 风险治理 | `/risk-governance` | 风险预警 | `/autorisk#alerts` |  |
| 风险治理 | `/risk-governance` | 风险违规 | `/compliance#breaches` |  |
| 风险治理 | `/risk-governance` | 例外管理 | `/risk-rules#exceptions` |  |
| 风险治理 | `/risk-governance` | 升级与处置 | `/autorisk#workflow` |  |
| 风险治理 | `/risk-governance` | 风险政策 | `/risk-rules#policy` |  |
| 风险治理 | `/risk-governance` | 模型验证 | `/investment-risk/validation` |  |
| 风险治理 | `/risk-governance` | 估值控制 | `/valuation#control` |  |
| 风险治理 | `/risk-governance` | 流动性治理 | `/investment-risk/liquidity-stress` |  |
| 风险治理 | `/risk-governance` | 合规核查 | `/compliance` | 一级入口仍可直达 `/compliance` |
| 风险治理 | `/risk-governance` | 风险报告 | `/reports` | `/reports` 仍为独立一级菜单 |
| 报表中心 | `/reports` | - | - | 必须保留的一级菜单 |
| 定时任务 | `/schedules` | - | - | 必须保留的一级菜单 |
| 自动风控 | `/autorisk` | - | - | 必须保留的一级菜单 |
| Agent / AI | `/chat` | AI Risk Copilot | `/chat?agent=general` | `/chat` 必须继续工作 |
| Agent / AI | `/chat` | Investment Agent | `/chat?agent=market-researcher` |  |
| Agent / AI | `/chat` | Portfolio Agent | `/chat?agent=fund-reporter` |  |
| Agent / AI | `/chat` | Risk Agent | `/chat?agent=risk-analyst` |  |
| Agent / AI | `/chat` | Valuation Agent | `/chat?agent=valuation-reviewer` |  |
| Agent / AI | `/chat` | Workflow Agent | `/chat?agent=month-end-closer` |  |
| Agent / AI | `/chat` | Agent Chat | `/chat` |  |
| Agent / AI | `/chat` | 专家知识库 | `/expert` |  |

## 二、系统管理菜单（System Management）

| 一级菜单 | 路径 | 子菜单 | 子菜单路径 | 说明 |
|---|---|---|---|---|
| 系统管理 | `/system-management` | 用户与权限管理 | `/admin` | 父路径无独立页面 |
| 系统管理 | `/system-management` | 系统配置 | `/system-config` |  |
| 系统管理 | `/system-management` | API Key 管理 | `/api-keys` |  |
| 系统管理 | `/system-management` | 通知中心 | `/notifications` |  |
| 系统管理 | `/system-management` | 设置 | `/settings` |  |

## 三、当前菜单树

```text
阿雷斯 · 智能风控和投资分析系统
├── 仪表板 (/)
├── 组合驾驶舱 (/portfolio-cockpit)
├── 投资风险分析 (/investment-risk)
│   ├── 模块总览 (/investment-risk)
│   ├── 组合概况 (/investment-risk/overview)
│   ├── 风险指标 (/investment-risk/indicators)
│   ├── 风险暴露 (/investment-risk/indicators#risk-exposure)
│   ├── 因子风险 (/investment-risk/factor-behavior#factor-risk)
│   ├── 市场风险 (/investment-risk/macro-dynamics#market-risk)
│   ├── 利率与信用风险 (/investment-risk/rates-credit)
│   ├── 外汇与资产风险 (/investment-risk/overview#asset-risk)
│   ├── 流动性风险 (/investment-risk/liquidity-stress)
│   ├── 集中度风险 (/investment-risk/rates-credit#concentration-risk)
│   ├── 交易对手风险 (/investment-risk/rates-credit#counterparty-risk)
│   ├── 杠杆与衍生品风险 (/investment-risk/indicators#leverage-derivatives-risk)
│   ├── 绩效与 PnL 归因 (/investment-risk/attribution)
│   ├── 风险预算 (/investment-risk/pretrade-budget#risk-budget)
│   ├── 宏观与市场动态 (/investment-risk/macro-dynamics)
│   └── 基本面因子与行为 (/investment-risk/factor-behavior)
├── 组合配置与优化 (/portfolio-opt)
│   ├── 模块总览
│   ├── 组合构建
│   ├── SAA
│   ├── TAA
│   ├── 风险预算
│   ├── 风险平价
│   ├── Black-Litterman
│   ├── HRP / HERC
│   ├── CVaR 优化
│   ├── 因子约束
│   ├── 流动性约束
│   ├── 集中度约束
│   ├── 杠杆约束
│   ├── 换手率约束
│   ├── 模拟组合
│   └── 组合验证
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
│   ├── 估值调整 XVA
│   ├── 流动性压力测试（规划中）
│   ├── 赎回压力测试（规划中）
│   ├── 保证金压力测试（规划中）
│   └── 交易对手压力测试（规划中）
├── 数据管理中心 (/data-management)
│   ├── 数据工作台
│   └── 持仓明细 (/positions)
├── 市场数据与指标 (/indicator-explorer)
│   ├── 市场数据
│   ├── 指标探索
│   └── SQL 资产库 (/sql-library)
├── 估值与损益 (/valuation)
├── 交易管理 (/data-management?section=trades)
├── 风险治理
│   ├── 风险限额 (/risk-rules#limits)
│   ├── 风险预警 (/autorisk#alerts)
│   ├── 风险违规 (/compliance#breaches)
│   ├── 例外管理 (/risk-rules#exceptions)
│   ├── 升级与处置 (/autorisk#workflow)
│   ├── 风险政策 (/risk-rules#policy)
│   ├── 模型验证 (/investment-risk/validation)
│   ├── 估值控制 (/valuation#control)
│   ├── 流动性治理 (/investment-risk/liquidity-stress)
│   ├── 合规核查 (/compliance)
│   └── 风险报告 (/reports)
├── 报表中心 (/reports)
├── 定时任务 (/schedules)
├── 自动风控 (/autorisk)
├── Agent / AI (/chat)
│   ├── AI Risk Copilot
│   ├── Investment Agent
│   ├── Portfolio Agent
│   ├── Risk Agent
│   ├── Valuation Agent
│   ├── Workflow Agent
│   ├── Agent Chat
│   └── 专家知识库 (/expert)
└── 系统管理
    ├── 用户与权限管理 (/admin)
    ├── 系统配置 (/system-config)
    ├── API Key 管理 (/api-keys)
    ├── 通知中心 (/notifications)
    └── 设置 (/settings)
```

## 四、菜单显示规则

1. 菜单定义来源：`getFsiItems()` 与 `getAdminItems()`。
2. 鉴权来源：`fsiApi.getMyAccessContext()`。
3. 过滤规则：
   - 普通用户：仅显示 `menu_paths` 中存在的路径（父级用 `permissionPaths` 或 `path`）。
   - 超级管理员：显示所有 `menu_stages != HIDDEN` 的路径。
4. 菜单分组：业务菜单在 `fsiSection`；管理菜单在 `systemManagement`。
5. 发布阶段：当 `menu_stages[path] === BETA` 时，一级菜单展示 `Beta` 标记。
6. 兼容路由：`/investment-risk/*`、`/risk-testing/*`、`/portfolio-opt`、`/reports`、`/schedules`、`/autorisk`、`/valuation`、`/compliance`、`/risk-rules`、`/chat` 均可直接访问。

## 五、源码依据

1. `frontend/src/components/Sidebar/AppSidebar.tsx`
2. `frontend/src/i18n/resources/zh-CN.ts`
3. `frontend/src/routeTree.gen.ts`
4. `frontend/tests/menu-architecture.spec.ts`
