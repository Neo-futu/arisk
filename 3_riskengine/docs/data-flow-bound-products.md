<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 数据流：从库表到 `bound.products` / 前十大个股

本文回答三件事，并钉死 RiskEngine 的数据流：

1. 怎么用 `3_riskengine` 取某组合**前十大个股**  
2. `module_top_stocks` **怎么实现**  
3. `bound.products(view="LOOK_THROUGH")` 的持仓是不是从 **`2_processing` 读库表**转来的  

配套业务口径见 [`investment-risk-overview.md`](investment-risk-overview.md)。

---

## 1. 总数据流（权威）

```
fsi.para_portfolio
fsi.balance_bond / balance_stock / balance_fund / balance_cash / balance_cd / balance_deposit …
fsi.balance_portfolio_nav
fsi.mktdata_*（报价 / 债风险 / FX / 指数）
        │
        ▼
2_processing.tools.risk_testing.loader.load_portfolio_snapshot
        │  读库 → PortfolioSnapshot
        │  positions: list[Position]
        │  net_asset / nav_returns / data_quality
        ▼
3_riskengine.market.load_portfolio_snapshot
        │  再挂 market_panel、指数基准（可选）
        ▼
RiskEngine().bind(snapshot)  →  BoundRiskEngine（即 bound）
        │
        ├─ bound.products(view="LOOK_THROUGH")
        │     Position → Product（Bond / Equity / …；货基穿透）
        │
        └─ bound.portfolio().overview()["top_stocks"]
              或 module_top_stocks(bound, limit=10)["rows"]
```

要点：

- **权威持仓在 `fsi.balance_*`**，不在 RiskEngine 内另建主数据。  
- **`bound` 不直接查库**；它只绑定已经装好的 `PortfolioSnapshot`。  
- **连库路径**才经过 `2_processing` loader；**夹具/单测**可直接 `bind(sample_snapshot())`，不经过 DB。

---

## 2. 怎么取某组合前十大个股

### 2.1 已有 snapshot（夹具或上游已加载）

```python
from 3_riskengine import RiskEngine

bound = RiskEngine().bind(snapshot)
top_stocks = bound.portfolio().overview(top_n=10)["top_stocks"]

# 或只调模块
from 3_riskengine.portfolio.overview import module_top_stocks
rows = module_top_stocks(bound, limit=10)["rows"]
```

### 2.2 真实组合（连库）

```python
from datetime import date
from 3_riskengine import RiskEngine
from 3_riskengine.market import load_portfolio_snapshot

snapshot = await load_portfolio_snapshot("BHMMF001", date(2026, 6, 25), db)
rows = RiskEngine().bind(snapshot).portfolio().overview(top_n=10)["top_stocks"]
```

`load_portfolio_snapshot` 内部调用 `2_processing.tools.risk_testing.loader.load_portfolio_snapshot` 读持仓与 NAV，再由 RiskEngine market 层挂行情/指数。

每行典型字段：`security_code`、`security_name`、`sector`、`market_value_base`、`weight_pct`、`unrealized_pnl`。

---

## 3. `module_top_stocks` 怎么实现

文件：`3_riskengine/portfolio/overview.py`。

```text
module_top_stocks(bound, limit=10)
        │
        ▼
_holding_rows(bound, EQUITY_KINDS)   # EQUITY + ETF
        │  1. products = bound.products(view="LOOK_THROUGH")
        │  2. 过滤 kind ∈ {EQUITY, ETF}
        │  3. weight_pct = market_value_base / NAV × 100
        │  4. sector ← metadata.sector | industry |「未分类」
        │  5. 按 |市值| 降序
        ▼
rows[:limit]
```

实现要点：

- **不二次查库**；输入是 `bound.snapshot` 里已有持仓。  
- **LOOK_THROUGH**：货基等先穿透到底层券再筛股票。  
- **不 import FinancePy / ORE**；Top10 是持仓聚合，不是定价引擎调用。  
- 同文件还有 `module_top_bonds`（BOND/CD），共用 `_holding_rows`。

---

## 4. `bound.products(...)` 与库表的关系

| 问题 | 答案 |
|---|---|
| `bound` 是什么？ | `BoundRiskEngine`：引擎 + 一份 `PortfolioSnapshot` |
| 持仓从哪来？ | **连库时**：`2_processing` loader 读 `fsi.balance_*` → `Position` 列表装进 snapshot |
| `products()` 做什么？ | 把 snapshot 的 `Position` **在内存中**映射为 `Product`（`products/assemble.py`） |
| `bound` 自己扫表吗？ | **否**；bind 之后只读 snapshot |

对应代码位置：

| 步骤 | 模块 |
|---|---|
| 读库拼快照 | `2_processing/tools/risk_testing/loader.py` |
| 持仓行加载 | 同包 `portfolio_data.load_positions` |
| 引擎再导出 + 行情 | `3_riskengine/market/platform.py` → `load_portfolio_snapshot` |
| bind | `3_riskengine/core/engine.py` → `RiskEngine.bind` |
| Position → Product | `3_riskengine/products/assemble.py` |
| Top10 股 | `3_riskengine/portfolio/overview.py` → `module_top_stocks` |

两种来源对比：

| 来源 | 路径 |
|---|---|
| 生产 / 联调 | DB → `2_processing` loader → `3_riskengine.market.load_portfolio_snapshot` → `bind` → `products` / `overview` |
| 单测 / 夹具 | `tests/fixtures.sample_*` → `bind` → 同上（无 DB） |

---

## 5. 与页面 HTTP 的关系

页面 `http://localhost:5173/investment-risk/overview` 的「前十大个股」也可走 processing SQL（`balance_stock` Top 10）。  
引擎路径与 SQL 路径是**同一业务事实的两条通道**：

- SQL：列表页快速供数  
- RiskEngine：`bind` 后统一对象、穿透视图、与估值/风险模块共用 snapshot  

对账时比较两边的 `security_code` / 市值排序 / 权重即可。

---

## 6. 边界

- 不在 RiskEngine 再建一套持仓主数据。  
- 业务代码依赖 `bound` / `overview`，不要直接 `import financepy`。  
- 行业缺省「未分类」；生产应把 GICS / 内部行业写入持仓 metadata 或经行情视图对齐。
