<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 7_ai — 自然语言与 Workflow Interface

## 定位

Agent 是 ARISK 的统一 NL / Workflow 入口。计算全部下沉到 Business API → RiskEngine → FinancePy / Riskfolio / ORE。Chat 运行时仍为 `aiagent/`。

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

## 禁止

Agent 不得自行计算 NAV / VaR / PnL / Stress Loss / Valuation / Risk Limit。

## 子目录

| 目录 | 职责 | 当前运行时权威 |
|---|---|---|
| `agents/` | investment / portfolio / risk / valuation / workflow | Chat：`aiagent/` |
| `skills/` | 技能名索引 | `3_skills/` |
| `tools/` | Tool 注册；调用 4_business / Quant / MCP | — |
| `workflows/` | 确定性步骤 | `autorisk/` |
| `knowledge/` | 知识入口索引 | `/api/v1/knowledge` |

## 权限

每次调用必须经过 JWT、Role、Portfolio Authorization、API Authorization，并写 Audit。Portfolio Agent 修改 Live 之前必须先有 Simulation Portfolio。

## MCP

MCP（`4_mcp/`）是 Tool Connectivity Layer：Market Data / Portfolio / Risk / Valuation / SQL。不得取代 RiskEngine。

## HTTP

- Processing：`/agents/catalog`、`/agents/invoke`（API Key）
- Backend JWT：`/api/v1/agents/*`（现有 Chat 仍在 `/api/v1/fsi/agent`）
