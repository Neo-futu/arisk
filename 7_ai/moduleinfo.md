<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 7_ai — AI 能力层

## 模块定位

```
6_entry / Backend Chat / /api/v1/agents
        ↓
【7_ai】  ← NL / Workflow Interface
  agents | tools | skills | workflows | knowledge
        ↓
4_business / 5_integrations.quant / 4_mcp（连通）
        ↓
3_riskengine → FinancePy / Riskfolio / ORE
```

| 项 | 说明 |
|---|---|
| 调用链 | User → Agent → Intent → Tool → Business → RiskEngine → Explanation |
| 计算 | Agent 不计算；MCP 不取代 RiskEngine |
| Chat | `aiagent/` |
| MCP 运行时 | `4_mcp/` |
