<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# arisk 目标平台目录树

本文档描述 **Target Architecture** 下的目标目录结构，供 Strangler 迁移对照。当前仓库实际布局见 [`current_platform_directory_tree.md`](current_platform_directory_tree.md)；迁移映射见 [`architecture_migration_map.md`](architecture_migration_map.md)。

## 目标主目录树

```text
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
│   └── compatibility/          # Processing 内 Facade → 新层
├── 3_riskengine/               # 统一量化与风险引擎
│   ├── core/
│   ├── adapters/               # FinancePy / Riskfolio / ORE
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
├── 4_business/                 # 业务用例层
│   ├── investment_risk/
│   ├── portfolio_optimization/
│   │   ├── construction/ saa/ taa/ risk_budget/ risk_parity/
│   │   ├── black_litterman/ hrp/ herc/ cvar/
│   │   ├── constraints/ liquidity/ turnover/ simulation/ validation/
│   ├── risk_testing/
│   ├── risk_governance/
│   ├── portfolio_management/
│   ├── trading/
│   ├── operations/
│   └── shared/                 # 后续：compliance / reporting / scheduling / audit / review
├── 5_integrations/             # 外部系统 Adapter + Quant API
│   ├── market_data/
│   ├── pms/
│   ├── oms/
│   ├── ems/
│   ├── broker/
│   ├── custodian/
│   ├── fund_admin/
│   ├── accounting/
│   └── quant/
├── 6_entry/
│   ├── web/
│   ├── cli/
│   └── excel/
├── 7_ai/
│   ├── agents/
│   │   ├── investment_agent/
│   │   ├── portfolio_agent/
│   │   ├── risk_agent/
│   │   ├── valuation_agent/
│   │   └── workflow_agent/
│   ├── skills/
│   ├── tools/
│   ├── workflows/
│   └── knowledge/
├── backend/
├── frontend/
├── docs/
├── scripts/
├── tests/
├── artefacts/
├── iac/
├── legacy/                     # 遗留登记（非运行时）
├── compatibility/              # 平台级 Facade
└── adapter/                    # 旧新 DTO 适配
```

## 目标分层职责

| 层 | 职责 |
|---|---|
| `frontend/` + `backend/` | 身份、RBAC、API 兼容网关 |
| `6_entry/` | Web / CLI / Excel / Agent 入口 |
| `4_business/` | 业务用例编排 |
| `3_riskengine/` | 统一计算与验证 |
| `5_integrations/` | 外部系统 Adapter、Quant API |
| `1_datastorage/` | 持久化与缓存 |
| `7_ai/` | Agent NL / Workflow Interface（不计算） |

## 过渡期并存（Wave 2 起）

以下旧目录在迁移完成前**保留为运行时权威**：

| 旧目录 | 目标 |
|---|---|
| `3_skills/` | `7_ai/skills/` |
| `4_mcp/` | `5_integrations/mcp/` |
| `aiagent/` | `7_ai/agents/` |
| `platform_agent/` | `7_ai/agents/`（平台子域） |
| `autorisk/` | Risk Workflow / `7_ai/workflows/` |
| `2_processing/tools/` | `3_riskengine/` 各子模块 |

## 原则

1. 第三方库仅通过 `3_riskengine/adapters/` 接入
2. 外部系统只经 `5_integrations` Adapter → ARISK Data Contract → RiskEngine / Business
3. Agent 只走 User → Intent → Tool → Business API → RiskEngine；不得自行计算 NAV / VaR / PnL / Stress / Valuation / Limit
4. MCP 是 Tool Connectivity Layer（`4_mcp/`），不得取代 RiskEngine
5. 现有 HTTP 路由通过 Facade 保持稳定
6. Frontend 模块名逐步对齐 `4_business` 域（如 `portfolio-opt` 路由可保留）
