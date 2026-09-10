<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 5_integrations — 外部系统接入层

```
External
    ↓
Adapter（本层）
    ↓
ARISK Data Contract
    ↓
RiskEngine / Business
```

业务域（`4_business`）**不得**直接调用外部系统或 vendor SDK。行情、PMS/OMS/EMS、券商、托管、基金行政、会计均经 Adapter。`4_mcp/` 仍为 MCP 运行时权威，本层不搬迁。

Quant API（Python / Jupyter / CLI / REST）也放在 `quant/`，只编排 RiskEngine 与 Business，不直连外部。
