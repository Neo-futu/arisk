<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 4_business — 业务用例层

## 定位

业务域回答「用户要解决什么问题」，编排 `3_riskengine` 计算、`5_integrations` 外部数据与 `1_datastorage` 持久化。API 路由与 Frontend 模块逐步与本层对齐，对外 URL 通过兼容 Facade 保持不变。

## 业务域

| 目录 | 对应 Frontend / API | 当前实现位置（Wave 2 未迁移） |
|---|---|---|
| `investment_risk/` | `/investment-risk` | Wave 4：KPI + 域模块；页面 API 经 `4_business.investment_risk.service` |
| `portfolio_optimization/` | `/portfolio-opt` | Wave 5：Riskfolio 过闸优化 + 仿真仓 |
| `risk_testing/` | `/risk-testing` | Wave 3：业务编排在 `4_business.risk_testing.service` |
| `risk_governance/` | `/risk-rules#limits` | Wave 6：统一 Limit Engine + Pre-Trade |
| `portfolio_management/` | 数据管理、持仓、估值 | `2_processing/api/routers/data_management.py` 等 |
| `trading/` | 模拟交易、前置风控 | Pre-Trade：`POST /api/v1/risk/pre-trade`；OMS/EMS 经 Adapter |
| `operations/` | 运营对接 | Valuation / NAV / PnL / 托管 / FA |

## Wave 4 状态

`investment_risk/` 已启用统一 KPI 与域模块；页面原有 payload 仍由 `2_processing/tools/performance` 计算，经本层 Facade 保持 `/investment-risk/*` 与 `/api/v1/fsi/investment/*` 兼容。
