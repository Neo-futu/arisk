<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 因子风险页业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/factor-risk`  
引擎入口：`RiskEngine().bind(snapshot).risk().factor_risk(meta=...)`  
实现：`3_riskengine/risk/factor_risk/`（**相对独立的模型包**）  
业务域：`4_business.investment_risk.factor_risk`

本文说明的是**资管因子风险业务能力**，不是工具栏 / 基准下拉 / 「计算」按钮。

模型在请求内实时计算，**不读取报表层缓存**；与 processing `compute_factor_risk` 同口径，但引擎侧自包含，不 import `2_processing`。基准收益经 `meta.fund_returns` / `meta.benchmark_returns`（交易日对齐后）注入。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **KPI 面板** | 组合 Beta、跟踪误差 + 公式 | `modules.kpi_panel` | KPI 表 |
| **摘要三卡** | 主导因子敞口 / Beta / TE | `modules.summary` | 顶部 MetricCard |
| **风险因子敞口** | 因子桶 %NAV | `modules.factor_exposure` | 「风险因子敞口」条形图 |
| **标准因子冲击 PnL** | 五类标准冲击损益 | `modules.factor_shocks` | 「标准因子冲击 PnL」表 |
| **因子风险贡献** | 按资产类别归一 | `modules.rc_by_asset_class` | 「因子风险贡献（按资产类别）」 |

```python
from importlib import import_module

RiskEngine = import_module("3_riskengine").RiskEngine

pack = RiskEngine().bind(snapshot).risk().factor_risk(
    meta={
        "benchmark_id": "HSI",
        "fund_returns": [...],      # 与基准交易日对齐
        "benchmark_returns": [...],
        "period_start": "2026-05-05",
        "period_end": "2026-11-02",
    },
)
assert pack["business_modules"] == [
    "kpi_panel", "summary", "factor_exposure", "factor_shocks", "rc_by_asset_class",
]
```

`pack["factor_risk"]` 与 HTTP `FactorRiskResult.factor_risk` **同形**，前端可直接消费。

---

## 2. KPI：Beta / Tracking Error

**组合 Beta**

\[
\beta=\frac{\mathrm{Cov}(R_p,R_b)}{\mathrm{Var}(R_b)}
\]

**跟踪误差（年化）**

\[
\mathrm{TE}=\mathrm{stdev}(R_p-R_b)\times\sqrt{252}
\]

- 收益序列须**交易日对齐**后注入；对齐观测数 \< 3 时结果为 `null` 并写入 `warnings`。  
- 货币基金对权益基准常见近零 Beta、较高 TE（样例页 TE≈132% 即属此类量级）。

---

## 3. 风险因子敞口（% NAV）

\[
\mathrm{FE}_f=\frac{\sum_{i\in f}|MV_i|}{\mathrm{NAV}}
\]

| 持仓资产类 | 因子桶 |
|---|---|
| BOND / CD / DEPOSIT / REPO … | `RATE_CREDIT` |
| EQUITY / STOCK / ETF … | `EQUITY` |
| 货币基金产品层 | `MMF` |
| 基金 | `FUND` |
| CASH | `CASH` |
| 币种 ≠ 报表币 | 叠加 `FX`（绝对市值计入 FX 桶） |

行按 `|pct_nav|` 降序；`summary.dominant_factor` = 首行因子。

---

## 4. 标准因子冲击 PnL

LOOK_THROUGH 统一再估值（FinancePy / ORE 适配器），标准冲击目录：

| 标签 | 因子 | 冲击 |
|---|---|---|
| `rate_1bp` | RATE | +1bp 绝对 |
| `equity_1pct` | EQUITY | +1% 相对 |
| `fx_1pct` | FX | +1% 相对 |
| `cs_1bp` | CREDIT_SPREAD | +1bp 绝对 |
| `vol_10pct` | VOLATILITY | +10% 相对 |

\[
\mathrm{PnL}_f=\mathrm{PV}(\mathrm{shock}_f)-\mathrm{PV}(\mathrm{base}),\quad
\%\mathrm{NAV}=\mathrm{PnL}_f/\mathrm{NAV}\times 100
\]

权威定义：`portfolio/measures.py` → `FACTOR_SHOCKS`。

---

## 5. 因子风险贡献（按资产类别）

跨五类标准冲击，将各持仓 `|PnL|` 累加后按资产类别归一：

\[
\mathrm{RC}_c=\frac{\sum_{i\in c}|PnL_i|}{\sum_j|PnL_j|}
\]

有收益面板时，`portfolio_risk` 可叠加 Riskfolio 统计 RC，再 roll-up 到资产类；缺面板时直接用因子冲击 `|PnL|` 归类（与页面条形图口径一致）。

---

## 6. 校验与域接入

```python
from 3_riskengine.risk.factor_risk import verify_business_modules

assert verify_business_modules(pack)["passed"]
```

```python
from 4_business.investment_risk.factor_risk import analyze

out = analyze(snapshot, benchmark_returns=[...])
# out["factor_risk"] → 五大模块打包；out["kpis"] → Factor Exposure / Beta / TE
```

---

## 7. 边界

- **不做**：前端自算 Beta/TE/冲击 PnL；把行为风格页（Momentum/HHI/拥挤）并入本页（见因子行为页）。  
- 冲击再估值依赖适配器；适配器不可用时冲击行可能为空，敞口与 Beta/TE 仍可算。  
- 权威持仓 / NAV / 指数行情由 processing 装入 snapshot / meta；引擎只做纯计算。  
- 结果是风险估计，不是会计估值或监管资本批复。
