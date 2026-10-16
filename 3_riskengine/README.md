<!-- 更新时间：2026-10-16（北京时间）｜生成模型：Grok 4.7 -->

# 3_riskengine — 统一量化与风险计算平台

## 定位

RiskEngine 是 ARISK **自主**的统一 Quantitative Finance & Risk Engine，不是第三方库的薄封装。它负责统一对象、接口、估值、风险因子、情景、结果与验证。FinancePy / Riskfolio / ORE 只通过 `adapters/` 接入。

目标架构与三库能力矩阵、路由表、分阶段计划见 [`docs/target-architecture.md`](docs/target-architecture.md)。给人用的说明见 [`docs/README.md`](docs/README.md)。开发用引擎包：[`scripts/riskengine/`](scripts/riskengine/)（`config` / `objects` / `main`）；启动器 [`scripts/run_riskengine.py`](scripts/run_riskengine.py)；闭环 [`scripts/platform_workflow.py`](scripts/platform_workflow.py)。

```
4_business
        ↓
   3_riskengine (RiskEngine)
        ↓
┌───────────────┬───────────────┬───────────────┐
│ FinancePy     │ Riskfolio-Lib │ ORE           │
│ Adapter       │ Adapter       │ Adapter       │
└───────────────┴───────────────┴───────────────┘
        ↓
   fsi.balance_* / fsi.mktdata_* / fsi.para_portfolio
```

## 目录

| 子目录 | 职责 |
|---|---|
| `core/` | `RiskEngine`、`RevaluationKernel`、合同对象、`resolve` 路由、版本与血缘 |
| `utils/` / `models/` / `products/` / `portfolio/` / `trade/` / `governance/` | 产品含 Equity / Bond / MMF / Deposit / CD / FX / IRS / Swaption / CDS 等；`portfolio` 聚合 Portfolio Risk / Fund Risk；`trade.build` 从 snapshot 构造 Trade；`governance.review` = Limits + Validation |
| `adapters/financepy/` | FlatDiscountCurve / `df_t` / `bump_parallel` / 修正久期 |
| `adapters/riskfolio/` | VaR/CVaR、HRP/HERC/CVaR/RP 优化（缺库时回退 NumPy） |
| `adapters/ore/` | 持仓→ORE Trade 描述符；FX/IRS/Swaption/CDS/期权定价；XVA；美式外汇期货期权。无 OREApp XML |
| `instruments/` | 平台持仓分类、KRD 桶、固收再定价 |
| `market/` | 平台表权威清单；NAV 收益 / 波动从 snapshot 读取 |
| `valuation/` | `price` / `revalue` / `greeks` / `cashflows` / `pnl`（Product + Market + Model） |
| `risk/` | `calculate` / `exposure` / Sensitivity / Stress / Scenario / Reverse Stress / Tail Risk / KRD / PnL Explain / Historical Backtest / VaR Backtest / XVA / KPI |
| `stress/` | 多因子压力测试 |
| `scenario/` | 内置情景目录与再估值 |
| `liquidity/` | 产品流动性桶、赎回瀑布、MMF WAM/WAL / SFC、彭博 LQAP |
| `counterparty/` | 产品敞口再聚合、XVA 分摊、净额集 |
| `pnl/` | 快照间 PnL explain |
| `limits/` | Limit Engine + SFC 60/120/50bp 口径 |
| `validation/` | Pricing / Greeks / Risk / Regression / Reconciliation / Cross-engine |
| `tests/` | 单元、确定性、回归、跨引擎样例 |

## 数据

只消费已有平台快照，不创建第二套 Portfolio / Position / Market Data 主数据。

| 对象 | 权威表 |
|---|---|
| 组合 | `fsi.para_portfolio`、`fsi.balance_portfolio_nav` |
| 持仓 | `fsi.balance_bond` / `cd` / `deposit` / `stock` / `fund` / `cash` |
| 市场 | `fsi.mktdata_quotes` / `fund_nav` / `bond_risk` / `fx_rate` |

加载入口仍为 `2_processing.tools.risk_testing.loader.load_portfolio_snapshot`（`3_riskengine.market.load_portfolio_snapshot` 再导出）。

## 绑定 API

```python
bound = RiskEngine().bind(snapshot)
bound.products()                 # PRODUCT：MMF 账本 → 一只基金；混合账本 → 分产品
bound.products(view="LOOK_THROUGH")
bound.trades()
bound.market()                   # FinancePy 曲线 + ORE reprice 绑定，产品不 import 厂商
bound.valuation().price()
bound.valuation().revalue(shocks)
bound.valuation().greeks(shocks)
bound.valuation().cashflows()
bound.valuation().pnl(shocks)
bound.portfolio().aggregate()
bound.portfolio().risk()            # Portfolio Risk（LOOK_THROUGH）
bound.portfolio().fund_risk()       # Fund Risk（PRODUCT + NAV）
bound.risk().var() / .cvar()
bound.risk().contribution()
bound.risk().optimize("hrp")
bound.risk().kpis()
bound.risk().sensitivity(shocks)
bound.risk().tail_risk(sigma_levels, capital_buffer)
bound.risk().krd()
bound.risk().historical_backtest()
bound.risk().var_backtest()
bound.stress().run(scenario)
bound.stress().reverse(scenario, target_loss_pct_nav)
bound.scenario().named("gfc_2008")
bound.liquidity().ratio()
bound.liquidity().report()
bound.liquidity().redemption(20.0)
bound.liquidity().mmf()
bound.liquidity().lqap(positions)   # 彭博 LQAP，输入为 mktdata_lqa 连接后的持仓
bound.counterparty().xva()
bound.counterparty().report()
bound.pnl().explain(previous)
bound.limits().evaluate()
bound.validation().pricing()
bound.validation().cross_engine()
bound.governance().review()
```

## 兼容

`2_processing.tools.risk_testing.ProfessionalRiskEngine` 委托 `3_riskengine.core.kernel`。HTTP 合同仍为 `/api/v1/fsi/risk-testing/*`。
