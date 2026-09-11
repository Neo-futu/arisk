<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# investment_risk — 投资风险分析

第一大核心业务域：当前组合有什么风险？

```
Business (本层)
    ↓
RiskEngine
    ↓
FinancePy / Riskfolio / ORE
```

## 模块

overview / exposure / market_risk / factor_risk / rates_credit / fx / liquidity / concentration / counterparty / leverage / pnl_attribution / risk_budget / macro_dynamics / factor_behavior

## KPI

VaR、CVaR、ES、Volatility、Drawdown、Beta、Tracking Error、Risk Contribution、Gross/Net/Factor Exposure、Duration、DV01、KRD、CS01、Liquidity、Concentration、Counterparty Exposure、PFE、EPE、Leverage。

每项报告含：Input、Calculation、Engine、Formula / Method、Result、Data Quality。

数据仍使用 `fsi.balance_*` / `fsi.mktdata_*`。前端路由 `/investment-risk/*` 保持兼容。
