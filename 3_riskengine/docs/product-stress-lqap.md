<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 产品压力测试（Bloomberg LQAP）— 架构与配置

业务模块说明（Tab 功能、公式、引擎入口）见 **[`investment-risk-product-stress.md`](investment-risk-product-stress.md)**。

本文只保留架构分层、库表与阶梯配置（权威配置面）。

---

## 架构

```
Frontend LqapPortfolioLiquidity.tsx
  → GET /api/v1/fsi/investment/lqa-portfolio/{fund_id}
  → 2_processing.lqa_portfolio_analytics（DB I/O）
  → 3_riskengine.liquidity
       lqa_fields.enrich_book
       lqap.analyze
       product_stress.fundamentals（业务模块打包）
```

| 层 | 路径 | 职责 |
|---|---|---|
| UI | `frontend/.../LqapPortfolioLiquidity.tsx` | 参数草稿/应用、Horizon / Stress |
| Orchestration | `2_processing/.../lqa_portfolio_analytics.py` | 读持仓/ADTV/价差/阶梯 → 调引擎 |
| Engine | `3_riskengine/liquidity/{lqa_fields,lqap,product_stress}` | **无 DB** |
| Schema | `024*.sql`、`025_lqa_fi_horizon_ladder.sql` | LQA 快照与 FI 阶梯 |

---

## 方案 A：Bid-Ask → Horizon 阶梯

**表**：`fsi.lqa_fi_horizon_ladder`（`ladder_id=DEFAULT`）  
缺表时回退 `DEFAULT_FI_HORIZON_LADDER`。

| band_seq | max_bid_ask_bps | horizon_days |
|---|---|---|
| 1 | 10 | 1 |
| 2 | 50 | 3 |
| 3 | 150 | 10 |
| 4 | NULL | 40 |

资产类价差：`fsi.sfc_liquidity_bucket_def`（`scenario=NORMAL` 的 `bid_ask_cost_bps`）。

---

## API

| 入口 | 说明 |
|---|---|
| `GET .../lqa-portfolio/{fund_id}` | 前端正式入口 |
| Query | `scenario`, `redemption_pct`, `cost_multiple`, `include_current_day` |
| RiskEngine | `liquidity().product_stress(...)` / `liquidity().lqap(positions, ...)` |

单测：`test_investment_risk_product_stress.py`、`test_lqap.py`、`test_lqa_fields.py`。
