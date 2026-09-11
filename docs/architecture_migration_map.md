<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# arisk 架构迁移映射

Strangler Pattern：Old → Compatibility → New。本文档维护 **Current → Target** 映射与兼容要求；不描述历史过程。

## 迁移链

```text
Old（当前权威代码路径）
        ↓
Compatibility（compatibility/、2_processing/compatibility/、adapter/）
        ↓
New（3_riskengine、4_business、7_ai、5_integrations）
```

## 目录映射

| Current | Target | Wave 2 状态 | 兼容要求 |
|---|---|---|---|
| `2_processing/tools/risk` | `3_riskengine/risk` | skeleton | 保留 `/api/v1/fsi/risk/*` |
| `2_processing/tools/risk_testing` | `4_business/risk_testing` + `3_riskengine` | Wave 3：业务编排已切到 `4_business.risk_testing.service`；算法仍在 tools | 保留 `/api/v1/fsi/risk-testing/*` |
| `2_processing/tools/performance/portfolio_optimizer.py` | `4_business/portfolio_optimization` + Riskfolio adapter | Wave 5：编排已切到 `4_business.portfolio_optimization.service`；`/analyze` 仍走 PyPortfolioOpt | 保留 `/portfolio-opt` |
| Investment routers | `4_business/investment_risk` | skeleton | 保留 `/investment/*` |
| `data_management` / `positions` / `valuation` | `4_business/portfolio_management` | skeleton | 保留持仓与估值 API |
| 模拟交易 / 前置风控 | `4_business/trading` + `risk_governance` | Wave 6：Pre-Trade 走统一 Limit Engine | 保留 Data Management API；新增 `POST /api/v1/risk/pre-trade` |
| `3_skills` | `7_ai/skills` | Wave 8：目录索引；文件仍在 `3_skills/` | 技能调用兼容 |
| `aiagent` | `7_ai/agents` | Wave 8：五个业务 Agent 内核在 `7_ai`；Chat 仍在 `aiagent/` | Agent Chat 不删 |
| `platform_agent` | `7_ai/agents` | 目标 skeleton | Platform API 保留 |
| `4_mcp` | `5_integrations/mcp` | MCP 仍在 `4_mcp/`，Wave 8 定为 Tool Connectivity Layer | MCP 工具名兼容 |
| `autorisk` | Workflow / `7_ai/workflows` | Wave 8：工作流目录；`autorisk/` 仍为自动化运行时 | `/autorisk` 必须存在 |
| 报表 / 调度 | `4_business/shared/reporting` 等 | 后续 Wave | `/reports`、`/schedules` |
| `backend/` | `backend/` | 不重构 | JWT / RBAC / 代理 |
| `frontend/modules/portfolio-opt` | 对齐 `portfolio_optimization` | 路由保留 | 内部逐步重组 |

## 3_riskengine 子模块映射（计划）

| 子目录 | 承接自 Current |
|---|---|
| `core` | 引擎注册、执行上下文（新建） |
| `adapters` | FinancePy / Riskfolio / ORE / 遗留算法 |
| `valuation` | `2_processing/tools/` 估值相关 |
| `instruments` | 工具定义、定价合同 |
| `market` | 行情、曲线、FX |
| `risk` | VaR、暴露、`tools/risk` |
| `stress` / `scenario` | `risk_testing` 情景与压力 |
| `liquidity` | MMF 流动性、投资风险管理 |
| `counterparty` | XVA 等 |
| `pnl` | 归因、估值损益 |
| `limits` | 统一 Limit Engine：Position/Issuer/…/VaR 与 GREEN–HARD_BREACH |
| `validation` | 数据与结果验证 |

## 4_business 与 Frontend

| 业务域 | Frontend 模块 | 路由 |
|---|---|---|
| `investment_risk` | `modules/investment-risk/` | `/investment-risk` |
| `portfolio_optimization` | `modules/portfolio-opt/` | `/portfolio-opt` |
| `risk_testing` | `modules/risk-testing/` | `/risk-testing` |
| `portfolio_management` | `data-management`、`valuation-pnl` 等 | 各现有路径 |
| `trading` | 数据管理 — 模拟交易 | 现有 API + `/api/v1/risk/pre-trade` |
| `operations` | 估值 / NAV / 托管 | 经 `5_integrations` Adapter |
| `risk_governance` | `/risk-rules#limits` | 限额与治理 |

## 兼容层位置

| 路径 | 角色 |
|---|---|
| `legacy/` | 遗留路径登记与文档 |
| `compatibility/` | 迁移链文档入口（不作为 Python 包名，避免与第三方包冲突） |
| `adapter/` | DTO 与语义转换 skeleton |
| `2_processing/compatibility/` | 可导入 Facade：`load` / `load_target` |
| `4_business/*/compat.py` | 业务域解析到当前 `2_processing.tools` 实现 |

## Wave 2 完成项

- [x] `3_riskengine/` 目录与 package skeleton
- [x] `4_business/` 五域 README / moduleinfo / skeleton
- [x] `7_ai/` 目标 skeleton（不删 `3_skills`、`aiagent`、`platform_agent`）
- [x] `legacy/`、`compatibility/`、`adapter/`、`2_processing/compatibility/`
- [x] 兼容 import：`2_processing.compatibility.load`、`4_business.*.compat`
- [x] Frontend modules 归属说明（不重命名 `portfolio-opt/`）
- [x] 保留 `4_mcp/`、`autorisk/`、`backend/`、`frontend/`、`2_processing/tools/`
- [x] 文档：`target_platform_directory_tree.md`、本文件；更新 `current_platform_directory_tree.md`

## Wave 3 完成项

- [x] 第三方源码与 ARISK 自有源码边界：`docs/third_party_patches.md`
- [x] `FinancePyAdapter` / `RiskfolioAdapter` / `OREAdapter`；业务层不直接 import 第三方库
- [x] 统一对象与 `valuation.price/revalue/greeks/pnl`、`risk.calculate/exposure/sensitivity/stress/scenario`
- [x] Risk Testing 用例进入 `4_business/risk_testing/service.py`，HTTP 合同不变
- [x] `validation`：Pricing / Greeks / Risk / Regression / Reconciliation
- [x] FinancePy / Riskfolio / ORE 最小确定性样例

## Wave 4 完成项

- [x] `4_business/investment_risk/` 十四个业务域模块
- [x] 21 项 Risk KPI（Input / Calculation / Engine / Formula / Result / Data Quality）
- [x] `GET /investment/kpis/{fund_id}` 与 `GET /investment/kpi-catalog`；原 `/investment-risk/*` 与 investment API 兼容
- [x] KPI regression tests

## Wave 5 完成项

- [x] `4_business/portfolio_optimization/` 功能模块（construction / SAA / TAA / risk_budget / risk_parity / BL / HRP / HERC / CVaR / constraints / liquidity / turnover / simulation / validation）
- [x] 优化只经 `3_riskengine.adapters.riskfolio`；结果过闸 Optimization → RiskEngine → Valuation → Investment Risk → Risk Testing → Limits，不得作为交易指令
- [x] Simulation Portfolio：Live → Clone → Modify → Optimize → Stress → Compare；未授权不得改 Live
- [x] 保留 `/portfolio-opt`；新增 catalog / governed-optimize / simulate / live/apply
- [x] Optimization / Constraints / Risk Budget / Risk Contribution / Simulation / Validation / Persistence / Compare 测试

## Wave 6 完成项

- [x] 统一 Limit Engine：`3_riskengine/limits/`（Position / Issuer / Sector / Country / Currency / Counterparty / Gross / Net / Leverage / Liquidity / VaR / CVaR / Drawdown / Derivative）
- [x] 状态 GREEN / WARNING / BREACH / HARD_BREACH
- [x] `4_business/risk_governance/`（Policy / Appetite / Limits / Breach / Exception / Escalation / Action / Approval / Closure / Model Validation / Valuation Control / Audit）
- [x] `POST /api/v1/risk/pre-trade`：Order → Valuation/Risk/Stress/Liquidity/Concentration/Counterparty/Limit → APPROVE / WARNING / REJECT
- [x] Investment Risk、Portfolio Optimization、Risk Testing 共用同一 Limit Engine
- [x] Limit / Boundary / Breach / Pre-Trade / Authorization / Audit 测试

## Wave 7 完成项

- [x] `5_integrations/`：market_data / pms / oms / ems / broker / custodian / fund_admin / accounting / quant
- [x] 外部系统只经 Adapter → ARISK Data Contract → RiskEngine / Business
- [x] Quant API：`risk.*` / `portfolio.optimize|simulate` / `valuation.price` / `testing.run`（Python / Jupyter / CLI / REST）
- [x] Trading：Order / Execution / Position / PreTrade / PostTrade
- [x] Operations：Valuation / NAV / PnL / Fund Accounting / Custodian / Fund Admin
- [x] API Contract / Adapter / Auth / Permission / Integrity / Failure / Retry / Audit 测试

## Wave 8 完成项

- [x] `7_ai/agents/`：investment / portfolio / risk / valuation / workflow
- [x] 调用链 User → Agent → Intent → Tool → Business API → RiskEngine → FinancePy/Riskfolio/ORE → Result → Explanation
- [x] Agent 不得直接计算 NAV / VaR / PnL / Stress Loss / Valuation / Risk Limit
- [x] Portfolio Agent：Live 变更前必须先走 Simulation Portfolio
- [x] 不得绕过 JWT / Role / Portfolio Authorization / API Authorization / Audit
- [x] MCP 为 Tool Connectivity Layer（Market Data / Portfolio / Risk / Valuation / SQL），不取代 RiskEngine；运行时仍为 `4_mcp/`
- [x] Agent / Tool Use / Streaming / Context / Permission / Risk Result / Audit / Failure Handling 测试

## Wave 9 完成项

- [x] 一级菜单：仪表板 / 驾驶舱 / 投资风险 / 组合优化 / 风险测试 / 数据 / 市场数据 / 估值 / 交易 / 治理 / 报表 / 定时 / 自动风控 / Agent / 系统管理
- [x] 核心业务统一 UI：Parameter → Data/Table → Charts → AI Copilot
- [x] Investment Risk 十四域、Portfolio Optimization 六步、Risk Testing 十项
- [x] AI Copilot 页面上下文：Portfolio / Date / Module / Result / Chart / Risk Metrics
- [x] Frontend 不承担金融计算；结果来自 RiskEngine
- [x] Responsive / Loading / Error / Empty / Permission / Route / Deep Link / Chart / Table / Export / AI Context 验收

## Wave 10 完成项

- [x] 机构业务链路在样例快照上实测：Market Data → … → Continuous Risk
- [x] RiskEngine Adapter / Valuation / Risk / Stress / Limits / Validation 实测
- [x] 三核心业务、主数据表名唯一、Processing API key、Agent 闸门实测
- [x] `2_processing/test` + `3_riskengine/tests` 259 passed；Frontend menu Playwright 5 passed
- [x] 最终报告：[`ARISK-Platform-V2-Final-Validation-Report.md`](ARISK-Platform-V2-Final-Validation-Report.md)
- [ ] Production Readiness READY（Riskfolio/ORE 运行时、Redis、Backend 全绿、登录 E2E 未齐）

## 后续 Wave（参考）

- Canonical Data Contracts → Facade 内切换合同
- RiskEngine Foundation → 迁入算法与 Engine Registry
- Frontend 模块目录重命名（路由不变）
- 生产运行时：Riskfolio-Lib / QuantLib-ORE / Redis / Backend 测试与种子对齐

详细 Wave 序列见 [`migrate_move0.md`](migrate_move0.md) 蓝图；实施顺序以各 Wave PR 为准。
