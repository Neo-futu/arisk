<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# risk_governance — 风险治理

Risk Policy / Appetite / Limits / Breach / Exception / Escalation / Action / Approval / Closure / Model Validation / Valuation Control / Audit。

限额统一由 `3_riskengine.limits` 计算，状态为 GREEN / WARNING / BREACH / HARD_BREACH。

Pre-Trade：`POST /api/v1/risk/pre-trade`。HARD_BREACH 不可例外放行。Investment Risk、Portfolio Optimization、Risk Testing 共用同一 Limit Engine。
