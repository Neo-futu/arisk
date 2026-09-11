# investment_risk

| 项 | 说明 |
|---|---|
| 菜单 | `/investment-risk` |
| 兼容路由 | `/risk` → 投资风险指标；`/investment-risk/*` 保持可访问 |
| 业务层 | `4_business/investment_risk/` |
| KPI 引擎 | `3_riskengine.risk.kpis` → FinancePy / Riskfolio / ORE adapters |
| 页面 API | 经 `service.py` 调用原 `2_processing.tools.performance` payload |
| 新增 API | `GET /investment/kpi-catalog`、`GET /investment/kpis/{fund_id}` |
