<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 产品压力测试 Tab 业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/indicators` → **产品压力测试** Tab（域签 key=`liquidity`）  
引擎入口：`RiskEngine().bind(snapshot).liquidity().product_stress(meta=...)`  
实现：`3_riskengine/liquidity/product_stress/`（业务打包）+ `lqa_fields` / `lqap`（**相对独立的计算核**）  
业务域：`4_business.investment_risk.liquidity` → `product_stress`

本文说明的是**资管组合变现压力（Bloomberg LQAP）业务能力**，不是工具栏 / 情景下拉壳 / CSV 按钮。

模型在请求内实时计算，**不读取报表层缓存、不 import `2_processing`**。持仓与市数经 `meta.holdings` + ADTV/价差/阶梯，或已 enrich 的 `meta.lqa_positions` 注入。与 processing `lqa_portfolio_analytics` 同口径。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **变现假设** | 赎回%、Bid-Ask 倍数、Incl Curr Day、情景因子 | `modules.assumptions` | Portfolio Liquidation Assumptions / Scenario |
| **组合概览** | 市值、价差、波动、Pct of EDV、Horizon、Score | `modules.overview` | Portfolio Overview |
| **赎回情景** | Nominal / Cost / Value / Residual | `modules.redemption` | Redemption Scenario |
| **期限分析** | 1d…>25d / Not Covered 分桶 | `modules.horizon_analysis` | Horizon Analysis |
| **个券压力明细** | 情景天数、成本、板块分 | `modules.stress_details` | Stress Details |
| **LQA 字段覆盖** | 15 个 LQA_* 有值只数与口径 | `modules.field_coverage` | 底部字段说明 |

```python
from importlib import import_module

RiskEngine = import_module("3_riskengine").RiskEngine

pack = RiskEngine().bind(snapshot).liquidity().product_stress(
    meta={
        "fund_id": "BHMMF001",
        "currency": "USD",
        "holdings": [...],
        "bid_ask_bps_by_asset": {"BOND_CORP": 3.0, "BOND_GOVT": 1.0},
        "adtv_by_code": {},
        "fi_horizon_ladder": [(10.0, 1.0), (50.0, 3.0), (150.0, 10.0), (None, 40.0)],
    },
    scenario_code="SEVERE",
    redemption_pct=100.0,
    cost_multiple=0.5,
    include_current_day=True,
)
assert pack["business_modules"] == [
    "assumptions", "overview", "redemption",
    "horizon_analysis", "stress_details", "field_coverage",
]
```

顶层字段与 HTTP `LqaPortfolioAnalytics` / `GET /api/v1/fsi/investment/lqa-portfolio/{fund_id}` **同形**。

底层亦可直接：`bound.liquidity().lqap(enriched_positions, ...)`（无业务模块壳）。

---

## 2. 变现假设与情景

| 参数 | 默认 | 作用 |
|---|---|---|
| `redemption_pct` | 100 | 赎回占组合市值比例 → Nominal / 个券 Cost |
| `cost_multiple` | 0.5 | Target Cost = Bid-Ask × 倍数 |
| `include_current_day` | true | `false` 时变现天数整体 +1 |
| `scenario_code` | `SEVERE` | 拉伸 `day_factor` / `cost_factor` / 股票 `volume_scale` |

权威情景表：`liquidity/lqap.py` → `SCENARIOS`（含 SEVERE、UKRAINE22、BANKRUN23 等）。

| 因子 | SEVERE | 作用对象 |
|---|---|---|
| `day_factor` | 1.4 | 变现天数 |
| `cost_factor` | 1.5 | Bid-Ask 成本 |
| `volume_scale` | 0.6 | **仅**股票类参与率路径的日容量 |

---

## 3. 组合概览

| 字段 | 口径 |
|---|---|
| `market_value` | Σ 持仓市值 |
| `positions` | 只数 |
| `bid_ask_bps` | 市值加权价差 × 10000 |
| `annual_volatility` / `daily_volatility` | 市值加权 `price_volatility`（久期×1%）；日波动 ≈ 年化/√252 |
| `pct_of_edv` | 组合市值 / Σ EDV ×100 |
| `liq_horizon_days` | 市值加权变现天数 |
| `global_score` | 市值加权 `sector_score`（1–100） |

---

## 4. 赎回情景

\[
\begin{aligned}
\mathrm{Nominal} &= \mathrm{MV}\times r \\
\mathrm{Cost} &= \sum_i MV_i\times \mathrm{spread}_i\times m\times c\times r \\
\mathrm{Value} &= \mathrm{Nominal}-\mathrm{Cost} \\
\mathrm{Residual} &= \mathrm{MV}-\mathrm{Nominal}
\end{aligned}
\]

其中 \(r\)=赎回比，\(m\)=`cost_multiple`，\(c\)=情景 `cost_factor`，`spread`=bid-ask（价格分数）。

---

## 5. 期限分析（Horizon）

| id | 标签 |
|---|---|
| `le1` | ≤ 1 day |
| `d1_3` … `d15_25` | 分段 |
| `gt25` | > 25 days |
| `not_covered` | 无有效天数（如债券无报价） |

每桶：`mv_weight_pct`、`positions`、`trade_size`（Σ EDV）、加权 `liq_horizon_days`、`sector_score`、`sector`。

### 5.1 债股分流（变现天数）

| 资产 | 模型 | 说明 |
|---|---|---|
| 现金 / 隔夜存款 | 合约 | 0 天 |
| 定期存款 / 回购 | 合约 | 剩余期限（天） |
| 债券 / CD | **Bid-Ask 阶梯** | 不用 ADTV×参与率 |
| 股票 / ETF 等 | 参与率×ADTV | \(MV/(EDV\times 10\%\times volume\_scale)\) |

**方案 A 阶梯**（`fsi.lqa_fi_horizon_ladder` / `DEFAULT_FI_HORIZON_LADDER`）：

| max_bid_ask_bps | horizon_days |
|---|---|
| ≤10 | 1 |
| ≤50 | 3 |
| ≤150 | 10 |
| >150（开放上沿） | 40 |

无报价 → **Not Covered**。再 × 情景 `day_factor`（+ optional settlement shift）。

---

## 6. 个券压力明细

`securities[]`：证券、市值/%、情景天数、Scenario/Base Class、冲击成本分数、Bid-Ask bp、EDV、赎回 Cost、Sector Score/Sector。按情景天数降序。

---

## 7. LQA 字段覆盖（15 类）

| 字段 | 口径摘要 |
|---|---|
| `LQA_PRICE_VOLATILITY` | 久期 × 1% 收益率波动 |
| `LQA_EXPECTED_DAILY_VOLUME` | 股票=ADTV；现金/存款/逆回购=市值；债券不驱动天数 |
| `LQA_BID_ASK_SPREAD` | 债券成本与指示天数；`sfc_liquidity_bucket_def.bid_ask_cost_bps` |
| `LQA_SECTOR_SCORE` | 资产类得分 − 变现天数 |
| `LQA_LIQUIDITY_SECTOR` | 债券板块，否则资产类别 |
| `LQA_HK_SFC_PORT_LQDTY_CLASS` | 由变现天数归类 |
| `LQA_EMPIRICAL_*` | ADTV 样本统计（股票类为主） |

页面：「有值 N/15 类 · M 只已计算」。

---

## 8. 校验与域接入

```python
from 3_riskengine.liquidity.product_stress import verify_business_modules

assert verify_business_modules(pack)["passed"]
```

```python
from 4_business.investment_risk.liquidity import analyze

out = analyze(snapshot)
# out["product_stress"] → 六大模块；out["liquidity"] → 通用桶/赎回/MMF
```

---

## 9. 边界

- **不做**：前端自算 Horizon；债券套用 ADTV×10% 作主口径；把 SFC DLA/WLA 结果直接当 LQAP。  
- FI 阶梯为方案 A；接入券级 Market Depth / 冲击曲线后可演进为 Target Cost 约束下反推日容量。  
- 权威持仓 / ADTV / 价差 / 阶梯表仍由 processing 装入 meta；引擎只做纯计算。  
- 架构与库表细则见同目录历史权威说明的交叉引用：阶梯表 `025_lqa_fi_horizon_ladder.sql`，LQA 快照 `024*.sql`。
