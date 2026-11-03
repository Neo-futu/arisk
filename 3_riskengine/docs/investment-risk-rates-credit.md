<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 利率信用 Tab 业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/indicators` → **利率信用** Tab（`#risk-exposure` 同页域签）  
引擎入口：`RiskEngine().bind(snapshot).risk().rates_credit()`  
实现：`3_riskengine/risk/rates_credit/`（**相对独立的模型包**）  
业务域：`4_business.investment_risk.rates_credit`

本文说明的是**资管利率与信用敏感度业务能力**，不是工具栏 /「查看 SQL」/ 导出按钮。

模型在请求内实时计算，**不读取报表层缓存**；与 processing `investment_analysis_rates_credit` 同口径，但引擎侧自包含，不 import `2_processing`。债券账本与多机构评级经 snapshot 持仓或 `meta.bonds` / `meta.agency_rows` 注入。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **债券账本** | 债市值、只数、占 NAV | `modules.bond_book` | 「债券持仓」KPI |
| **利率/信用敏感度** | 加权久期、DV01、CS01 | `modules.sensitivity` | 久期 / DV01 / CS01 卡 |
| **期限结构分桶** | 1M·3M·6M·1Y·1Y+ 久期加权 | `modules.krd_buckets` | 「期限结构分桶（KRD）」 |
| **评级分布** | 主体/债项 IG% 与占比 | `modules.rating_distribution` | IG% 卡 + 评级分布 + 明细表 |
| **按券多家机构评级** | 中诚信/联合/标普/穆迪/惠誉/内评 | `modules.bond_agency_ratings` | 按券·主体 / 债项表 |
| **评级等级对照** | 投资级/投机级符号表 | `modules.rating_scale` | 「各机构评级等级对照」 |
| **发行人集中度** | Top10 + HHI | `modules.issuer_concentration` | 「发行人集中度 Top10」 |

```python
from importlib import import_module

RiskEngine = import_module("3_riskengine").RiskEngine

pack = RiskEngine().bind(snapshot).risk().rates_credit(
    meta={"bonds": [...], "agency_rows": [...], "net_asset": nav},
    rating_source="all",
    top_n=10,
)
assert pack["business_modules"] == [
    "bond_book", "sensitivity", "krd_buckets", "rating_distribution",
    "bond_agency_ratings", "rating_scale", "issuer_concentration",
]
```

顶层字段与 HTTP `RatesCreditResult` / `GET /api/v1/fsi/investment/rates-credit/{fund_id}` **同形**，前端可直接消费。

---

## 2. 债券账本

| 字段 | 口径 |
|---|---|
| `total_bond_market_value` | 债类持仓市值合计（含 `treat_as_bond` 的债基 ETF） |
| `bond_count` | 债只数 |
| `bond_exposure_pct_nav` | 债市值 / NAV ×100 |

债识别：`asset_class ∈ {BOND, CD, DEPOSIT, REPO, REV_REPO}`，或 ETF/FUND 且 `fund_asset_class/underlying` 为债，或 `metadata.treat_as_bond`。

---

## 3. 利率与信用敏感度

**加权久期**

\[
D_w=\frac{\sum_i MV_i\,D_i}{\sum_i MV_i}
\]

**DV01**（利率上升 1bp 时组合市值变动）

\[
\mathrm{DV01}=\sum_i MV_i\,D_i\times 10^{-4}
\]

**CS01**（信用利差敏感度 / Spread DV01 近似）

无完整 spread duration 时，保守代理：

\[
\mathrm{CS01}=\sum_i MV_i\,(0.8\,D_i)\times 10^{-4}
\]

即 \(\mathrm{CS01}\approx 0.8\times\mathrm{DV01}\)。页面文案：「信用利差上升 1bp 时组合市值变动的近似」。

---

## 4. 期限结构分桶（KRD）

按**剩余期限天数**分桶（非 FinancePy 关键利率久期键率）：

| 桶 | 条件（天） |
|---|---|
| `1M` | ≤ 30 |
| `3M` | ≤ 90 |
| `6M` | ≤ 180 |
| `1Y` | ≤ 365 |
| `1Y+` | > 365 |

桶权重 = 该桶 \(\sum MV\times D\) 占全债 \(\sum MV\times D\) 的百分比。无到期日时用 \(D\times 365\) 近似剩余天数（下限推入长端）。

---

## 5. 评级分布与来源过滤

投资级下沿：**BBB- / Baa3**；**BB+ / Ba1** 起为投机级。

| 字段 | 含义 |
|---|---|
| `issuer_investment_grade_pct` / `debt_investment_grade_pct` | 主体 / 债项投资级市值占比 |
| `issuer_rating_distribution` / `debt_rating_distribution` | 评级 → 市值 / 占债% / 是否 IG |
| `rating_distribution` | 兼容旧前端：债项优先、缺省主体的合成分布 |
| `rating_source` | `all` / `domestic` / `csci` / `lianhe` / `foreign` / `sp` / `moody` / `fitch` / `internal` |
| `rating_matched_bond_count` | 当前来源匹配只数（页面「当前来源匹配 N / M 只债券」） |

- 来源 `all` / 国内 / 标普 / 惠誉：分布桶统一 **AAA·AA+** 符号。  
- 来源 `moody`：分布桶用 **Aaa·Aa1**，避免与 AAA 拆成两档。  
- 内地 ↔ 国际无官方换算；对照表仅为量级参考。

---

## 6. 按券·多家机构评级

列：`CSCI`（中诚信）、`LIANHE`（联合）、`SP`、`MOODY`、`FITCH`、`INTERNAL`。

数据源优先 `fsi.balance_bond_agency_rating`（经 `meta.agency_rows` 注入）；缺省回填持仓单机构列与 `internal_rating`。

| 机构 | 显示符号 |
|---|---|
| 中诚信 / 联合 / 标普 / 惠誉 / 内评 | AAA · AA+ · … · BBB- |
| 穆迪 | Aaa · Aa1 · … · Baa3 |

返回行含 `issuer_ratings` / `debt_ratings` 两套字典，前端分别渲染「按券·主体评级」「按券·债项评级」。

---

## 7. 评级等级对照

`rating_scale_legend`：投资级 10 档 + 投机级 8 档（最高 → 接近违约），列国内 / 标普·惠誉 / 穆迪。  
`rating_scale_note` 固定提示投资级下沿与无官方换算声明。

---

## 8. 发行人集中度

\[
\mathrm{HHI}=10\,000\sum_j w_j^2,\quad w_j=\frac{MV_j}{\sum MV}
\]

`top_issuers` 默认前 10：发行人、市值、占债%。页面「发行人集中度 Top10」。

---

## 9. 校验与域接入

```python
from 3_riskengine.risk.rates_credit import verify_business_modules

check = verify_business_modules(pack)
assert check["passed"]
```

业务域：

```python
from 4_business.investment_risk.rates_credit import analyze

out = analyze(snapshot)
# out["rates_credit"] → 七大模块打包；out["kpis"] → Duration/DV01/KRD/CS01
```

---

## 10. 边界

- 本包**不**调用 FinancePy KRD bump / ORE；页面「KRD」实为剩余期限分桶的久期加权占比。  
- CS01 在缺 spread duration 时为 0.8×修正久期代理，非完整 OAS 敏感度。  
- 多机构评级符号对照**非**监管或评级机构官方映射。  
- 权威持仓表仍为 `fsi.balance_bond` / `fsi.balance_bond_agency_rating`；引擎只消费已装入的 snapshot / meta。
