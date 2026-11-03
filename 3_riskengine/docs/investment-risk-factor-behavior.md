<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 基本面因子与行为风险页业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/factor-behavior`  
引擎入口：`RiskEngine().bind(snapshot).risk().factor_behavior(meta=...)`  
实现：`3_riskengine/risk/factor_behavior/`（**相对独立的模型包**）  
业务域：`4_business.investment_risk.factor_behavior`

本文说明的是**资管风格因子与交易行为监测能力**，不是工具栏 / 搜索框 / 导出按钮。

模型在请求内实时计算，**不读取报表层缓存**；与 processing `compute_factor_behavior_risk` 同口径，但引擎侧自包含，不 import `2_processing`。股票持仓、区间行情、换手与风格分桶经 `meta` 注入。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **摘要四卡** | Momentum / LowVol / Size / Sector HHI | `modules.summary` | 顶部 MetricCard |
| **风格因子暴露** | 三因子 + Coverage + 价值/成长/大小盘 | `modules.style_exposure` | 风格条形图 + 风格权重卡 |
| **行业集中度** | HHI 与行业权重 | `modules.sector_concentration` | 「行业集中度结构」 |
| **交易行为** | 换手率 + 拥挤度 Top | `modules.trading_behavior` | 拥挤度表 / 换手明细 |
| **方法论** | 实现步骤与公式 | `modules.methodology` | 底部逻辑卡 |

```python
from importlib import import_module

RiskEngine = import_module("3_riskengine").RiskEngine

pack = RiskEngine().bind(snapshot).risk().factor_behavior(
    meta={
        "holdings": [...],          # 区间末股票持仓
        "quotes": [...],            # mktdata_quotes 收盘价/成交量
        "turnover_pct": 0.0,
        "value_weight_pct": 0.0,
        "growth_weight_pct": 100.0,
        "large_weight_pct": 100.0,
        "small_weight_pct": 0.0,
        "period_start": "2026-05-05",
        "period_end": "2026-11-02",
    },
)
assert pack["business_modules"] == [
    "summary", "style_exposure", "sector_concentration",
    "trading_behavior", "methodology",
]
```

顶层 `style_exposure` / `sector_concentration` / `trading_behavior` / `warnings` / `logic` / `formulas` 与 HTTP `FactorBehaviorResult` **同形**。

---

## 2. 风格因子暴露

市值权重 \(w_i=MV_i/\sum MV\)。仅当个券同时有区间收益与日波动时计入覆盖：

| 因子 | 公式 |
|---|---|
| **Momentum** | \(\sum_i w_i\cdot(P_{\mathrm{end}}/P_{\mathrm{start}}-1)\) |
| **LowVol** | \(\sum_i w_i/(1+\sigma_i)\)，\(\sigma_i\) 为区间日收益标准差 |
| **Size** | \(\sum_i w_i\cdot\ln(\max(MV_i,1))\) |
| **Coverage** | 有行情覆盖的权重合计 ×100 |

可选风格分桶（`mktdata_equity_style`）：`value_weight_pct` / `growth_weight_pct` / `large_weight_pct` / `small_weight_pct`。

---

## 3. 行业集中度

\[
\mathrm{HHI}=\sum_s w_s^2\times 10\,000
\]

- 行业优先 GICS（`mktdata_stock_industry`），缺省持仓 `sector`。  
- **HHI > 1800** → 警告「行业集中度偏高」。单行业 100% 时 HHI=10000。

---

## 4. 交易行为与拥挤

**拥挤比**

\[
\mathrm{Crowding}_i=\frac{\mathrm{quantity}_i}{\mathrm{avg\_daily\_volume}_i}
\]

按拥挤比降序取 Top（默认 20）。头部拥挤比 **> 0.25** → 踩踏风险警告。

**换手率**：区间股票买卖单边较小值 / 平均持仓市值 ×100。  
**> 120%** → 拥挤交易风险警告。

---

## 5. 警告规则

| 条件 | 文案 |
|---|---|
| 无股票持仓 | 区间末无股票持仓，风格暴露与拥挤度为空 |
| 覆盖权重=0 | 持仓缺少可用行情，风格暴露无法计算 |
| HHI > 1800 | 行业集中度偏高（HHI > 1800） |
| 换手 > 120% | 股票换手率偏高，存在拥挤交易风险 |
| 头部拥挤 > 0.25 | 头部持仓相对日均成交量偏高，可能存在踩踏风险 |

---

## 6. 校验与域接入

```python
from 3_riskengine.risk.factor_behavior import verify_business_modules

assert verify_business_modules(pack)["passed"]
```

```python
from 4_business.investment_risk.factor_behavior import analyze

out = analyze(snapshot)
# out["factor_behavior"] → 五大模块；out["kpis"] → Factor Exposure / Concentration / Beta
```

纯函数入口（无 bind）：`analyze_book(holdings, prices_by_security=..., volumes_by_security=...)`。

---

## 7. 边界

- **不做**：前端自算风格/HHI/拥挤；把因子风险页（标准冲击 PnL / Beta·TE）并入本页。  
- 本页**不依赖基准指数**；`benchmark_id` 参数在 processing 层保留兼容但不参与计算。  
- 权威持仓 / 行情 / 风格分桶 / 换手由 processing 装入 meta；引擎只做纯计算。  
- 结果用于风格漂移与踩踏监测，不是会计估值或监管资本批复。
