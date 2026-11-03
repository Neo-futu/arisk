<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 组合概况业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/overview`  
引擎入口：`RiskEngine().bind(snapshot).portfolio().overview()`  
实现：`3_riskengine/portfolio/overview.py`  
业务域：`4_business.investment_risk.overview`

本文说明的是**资管业务能力**，不是工具栏 / CSV / 卡片壳。

取前十大个股的调用方式、`module_top_stocks` 实现，以及 `bound.products` 与 `2_processing` 库表数据流，见 [`data-flow-bound-products.md`](data-flow-bound-products.md)。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **组合** | 组合身份、AUM、单位/累计净值、日收益 | `modules.portfolio` | 顶部四卡：基金 / 净资产 / 单位净值 / 当日收益 |
| **区间收益** | 1日·1月·3月·YTD·1年·成立以来 | `modules.performance` | 「业绩」表 + 累计收益趋势图 |
| **资产配置结构** | LOOK_THROUGH 资产类别权重 | `modules.asset_allocation` | 配置结构条形图 + 配置表 |
| **前十大个股** | EQUITY/ETF 市值 Top 10 | `modules.top_stocks` | 前十大个股表 |
| **前十大个券** | BOND/CD 市值 Top 10 | `modules.top_bonds` | 前十大个券表（YTM/久期/票息） |
| **股票行业配置** | 个股按 sector 汇总 | `modules.stock_sectors` | 股票行业配置表 |

```python
from 3_riskengine import RiskEngine

bound = RiskEngine().bind(snapshot)
pack = bound.portfolio().overview(
    meta={"port_name": "组合A", "portfolio_type": "MIXED", "unit_nav": 1.02},
)
assert pack["business_modules"] == [
    "portfolio", "performance", "asset_allocation",
    "top_stocks", "top_bonds", "stock_sectors",
]
```

---

## 2. 模块口径

### 2.1 组合 `portfolio`

| 字段 | 口径 | 权威 |
|---|---|---|
| `fund_id` / `port_name` | 组合代码 / 名称 | `fsi.para_portfolio` |
| `portfolio_type` | 产品线 | `port_type` |
| `base_currency` | 报表货币 | snapshot |
| `net_asset` | AUM | `balance_portfolio_nav` |
| `unit_nav` / `acc_unit_nav` | 单位 / 累计净值 | 同上 |
| `day_return` | 日收益率（小数） | NAV.day_return 或收益序列末日 |
| `data_date` | 估值日 | as_of |

### 2.2 区间收益 `performance`

| 区间 | 起点规则 |
|---|---|
| 1日 | 上一交易日 NAV |
| 1月 / 3月 / 1年 | 目标日 ≤ as_of 的最近 NAV |
| 年初至今 | 上年年末 NAV |
| 成立以来 | 序列首点 |

$$
\mathrm{return\_pct} = \left(\frac{\mathrm{NAV}_{end}}{\mathrm{NAV}_{start}} - 1\right) \times 100
$$

累计收益曲线 `timeseries[].cumulative_return_pct`：首日 = 0%。

### 2.3 资产配置结构 `asset_allocation`

- 视图：**LOOK_THROUGH**（货基先穿透）
- ProductKind → 页面资产类：`EQUITY→STOCK`，`BOND→BOND_CORP`，`CASH/DEPOSIT/CD/REPO…` 见 `_KIND_TO_PLATFORM`
- `weight_pct = market_value_base / AUM × 100`

平台表 `fsi.balance_portfolio_asset` 为列表权威摘要；引擎用持仓再定价对账。

### 2.4 前十大个股 / 个券

| | 个股 | 个券 |
|---|---|---|
| 范围 | EQUITY、ETF | BOND、CD |
| 排序 | \|市值\| 降序 | 同左 |
| 条数 | Top 10 | Top 10 |
| 关键字段 | code/name/sector/weight/未实现损益 | + issuer/rating/ytm/duration/coupon/maturity |

### 2.5 股票行业配置 `stock_sectors`

按 `metadata.sector`（或 `industry`）汇总市值、权重、持仓只数。  
线上可与 `fsi.v_mktdata_stock_industry_current`（GICS）对齐后写入持仓 metadata。

---

## 3. 数据流

```
fsi.para_portfolio              → 组合身份
fsi.balance_portfolio_nav       → AUM / 净值 / 日收益 / 区间业绩
fsi.balance_portfolio_asset     → 页面资产配置摘要（SQL）
fsi.balance_stock / balance_bond→ 页面 Top10 / 行业（SQL）
fsi.balance_* + mktdata_*       → RiskEngine snapshot 穿透配置与估值
        ↓
RiskEngine.bind(snapshot).portfolio().overview()
        ↓
六大业务模块（可与 HTTP overview 字段对账）
```

HTTP：`GET /api/v1/fsi/investment/overview/{fund_id}`（processing `compute_portfolio_overview`）。  
引擎包用于：单测、Agent、域分析 `4_business.investment_risk.overview.analyze`、与 SQL 结果对账。

---

## 4. 验证

```bash
python 3_riskengine/scripts/run_tests.py tests/test_investment_risk_overview.py -q
```

断言：

- `verify_business_modules` 通过
- 配置权重和 ≈ 100%
- Top 股/债按市值降序；行业覆盖个股 sector
- 区间表含 1日 / 1月 / 成立以来

夹具：`3_riskengine.tests.fixtures.sample_overview_snapshot`。

---

## 5. 边界

- 不另建持仓主数据；SQL 列表与引擎穿透是同一业务事实的两条路径。
- 厂商库仅 `adapters/`；概况业务不直接 import FinancePy/ORE/Riskfolio。
- 行业缺省为「未分类」；生产应补 GICS / 内部行业主数据。
- 业绩区间是 NAV 相对收益，不是会计期间损益表。
