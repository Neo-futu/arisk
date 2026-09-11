<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 4_business.risk_testing

Risk Testing 业务用例层。菜单与 API 合同见 [`docs/risk-testing.md`](../../docs/risk-testing.md)。

编排：`4_business.risk_testing.service` → RiskEngine。`service.run(snapshot, analytic)` 走统一引擎。HTTP `execute_risk_test` 仍委托 `ProfessionalRiskEngine` → `core/kernel`，以保持已发布数字。
