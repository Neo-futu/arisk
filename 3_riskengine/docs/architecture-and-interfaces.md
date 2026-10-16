<!-- 更新时间：2026-10-16（北京时间）｜生成模型：Cursor Composer -->

# RiskEngine 架构和接口

权威补充：三库能力与路由见 [`target-architecture.md`](target-architecture.md)。代码地图见 [`codebase-guide.md`](codebase-guide.md)。产品与报表见 [`products-and-business.md`](products-and-business.md)。平台切片开发（枚举资产/产品/指标/情景/估值，单格实现）见 [`platform-incremental-verification.md`](platform-incremental-verification.md)。

---

## 1. 一句话

**RiskEngine** 是 ARISK 自己的统一量化与风险引擎：统一对象、路由、估值、组合聚合、流动性、压力/情景、交易对手、限额、验证与治理。FinancePy / ORE / Riskfolio 只是 adapter，不是业务 API。

```
FinancePy  →  Product / Market / Model
ORE        →  Trade / Investment Risk Workflow（无 OREApp XML）
Riskfolio  →  Portfolio Risk / Optimization
MMF        =  与 Equity / Bond / FX / Option / Future 同级产品
```

```
4_business / 5_integrations.quant / HTTP
        ↓
   RiskEngine.bind(snapshot)
        ↓
   products + market + models + resolve()
        ↓
   adapters/financepy | adapters/ore | adapters/riskfolio
        ↓
   fsi.balance_* / fsi.mktdata_* / fsi.para_portfolio
```

版本：`3_riskengine.core.lineage.RISKENGINE_VERSION`（当前 **1.0.0**），引擎名 `ARISK RiskEngine`。

---

## 2. 对象模型

计算 DTO 在 `core/contracts.py`。**不**另建主数据。

| 对象 | 含义 | 与平台表 |
|---|---|---|
| `Instrument` | 合约规格（代码、货币、到期、产品类型） | 持仓行的静态字段 |
| `Product` | `value / cashflows / sensitivity` | 一行持仓或一只 MMF |
| `Trade` | Instrument + 对手方 + 净额/CSA | `fsi.transact_*` 后期；现由 snapshot 导出描述符 |
| `Position` | 账面数量与市值 | `fsi.balance_*` |
| `Portfolio` | LIVE / SIMULATION / MODEL / BENCHMARK | `fsi.para_portfolio` |
| `Market` / `MarketSnapshot` | 价格、FX、曲线、NAV 收益 | `fsi.mktdata_*`、`fsi.balance_portfolio_nav` |
| `Model` | 数学模型身份（不是组合对象） | `models/catalog.py` |
| `Shock` / `Scenario` | 风险因子冲击 | `scenario/catalog.py` |
| `EngineRef` | `{adapter, model, fallback}` | `core/resolve.py` |

`Instrument ≠ Trade ≠ Position`。MMF **份额**是 Product；申购赎回是 Trade；账面是 Position。

两种估值视角 `ViewMode`：

| 视角 | 用途 |
|---|---|
| `PRODUCT` | MMF 账本收成一只基金（NAV） |
| `LOOK_THROUGH` | 穿透到 Bond / CD / Deposit / Cash / Equity / OTC（默认再估值） |

---

## 3. 引擎路由

业务不得选择底层库。唯一入口：

```python
from 3_riskengine import RiskEngine

engine = RiskEngine()
ref = engine.resolve("BOND", "PRICE")   # EngineRef(adapter="financepy", ...)
ref = engine.resolve("IRS", "XVA")      # adapter="ore"
ref = engine.resolve("EQUITY", "VAR")   # adapter="riskfolio"
```

`SENSITIVITY` 与 `GREEKS` 同路由。组合级分析（VaR、Stress、KRD、XVA 等）按分析类型选 adapter，不按单券再选一次厂商。

完整表见 [`target-architecture.md`](target-architecture.md) §11 与 `core/resolve.py`。

---

## 4. 绑定接口（主 API）

所有计算绑定到一份已加载的平台快照：

```python
bound = RiskEngine().bind(snapshot)
```

| 入口 | 职责 | 典型调用 |
|---|---|---|
| `products(view)` | 快照 → Product | `bound.products("LOOK_THROUGH")` |
| `trades(view)` | 快照 → Trade DTO | `bound.trades()` |
| `market()` | 价格 / FX / 曲线 callable | `bound.market()` |
| `valuation()` | 定价 / 再估值 / Greeks / 现金流 / PnL | `price` `revalue` `greeks` `cashflows` `pnl` |
| `portfolio()` | 组合/基金聚合、VaR/CVaR/RC/优化 | `aggregate` `risk` `fund_risk` `optimize` |
| `risk()` | 风险测试十项 + KPI + 组合风险 | `sensitivity` `krd` `var` `kpis` `calculate` |
| `stress()` / `scenario()` | 多因子压力、命名情景 | `run` `reverse` `named("gfc_2008")` |
| `liquidity()` | 流动性桶、赎回、MMF SFC、LQAP 产品压力测试 | `report` `redemption` `mmf` `lqap`（详见 [`product-stress-lqap.md`](product-stress-lqap.md)） |
| `counterparty()` | 对手方、PFE/EPE、XVA 分摊 | `exposure` `xva` `report` |
| `pnl()` | 跨期解释 | `explain(previous)` |
| `limits()` | 限额引擎 | `evaluate` `catalog` `check` |
| `validation()` | 定价/Greeks/回归/交叉引擎 | `pricing` `cross_engine` `run` |
| `governance()` | 限额 + 验证 + MMF SFC（非交易指令） | `review` |
| `kernel()` | 兼容 `ProfessionalRiskEngine` 的再定价核 | 仅 HTTP / 回归使用 |

零冲击 `valuation.price()` 的 PV 等于平台账面市值。有冲击时走 Product 再估值（FinancePy 曲线或 ORE 增量）。

---

## 5. 对业务层的接口

| 业务域 | 应调用 | 不要做 |
|---|---|---|
| `4_business.investment_risk` | `bound.risk().kpis()`、`liquidity().report()`、`counterparty().report()`、`limits().evaluate()` | 自写 VaR / 定价 |
| `4_business.portfolio_optimization` | `bound.portfolio().optimize`、`RiskEngine().riskfolio`、Limit Engine | `import riskfolio` |
| `4_business.risk_testing` | `service.run(snapshot, analytic)` → `bound.risk()` | 在业务层拼 ORE XML |
| `5_integrations.quant` | 同上 + `valuation.price` | 直连厂商 |
| 驾驶舱 SFC 状态 | `3_riskengine.limits.sfc.compliance_status` | 另写一套 WAM/WAL 规则 |

HTTP 风险测试（已发布数字）仍走：

```
/api/v1/fsi/risk-testing/*
  → 4_business.risk_testing.service.execute_risk_test
  → ProfessionalRiskEngine → 3_riskengine.core.kernel
```

新 Python / Jupyter / Agent 路径走 `RiskEngine.bind`。

---

## 6. 结果合同

报告至少带血缘（`RESULT_LINEAGE_KEYS`）：`portfolio_id`、`valuation_date`、`market_data_date`、`engine`、`engine_version`、`model`、`assumptions`、`data_quality`、`validation_status`。

统一 `stamp()` 还会写 `analytic`、`fund_id`、`as_of_date`、`reporting_currency`、`adapters`。XVA / Stress / 流动性报告含 `ore_app: False`。

PnL Explain 五路恒等：

```
carry + rates + fx + position + residual == total
```

credit / equity / volatility 是 leftover 的标签，不从恒等中再减一次。

Governance：`is_trade_instruction=False`。限额状态 `GREEN | WARNING | BREACH | HARD_BREACH`。

---

## 7. 数据入口

快照由 `2_processing.tools.risk_testing.loader.load_portfolio_snapshot` 从现有表加载；`3_riskengine.market.load_portfolio_snapshot` 再导出。RiskEngine **不**开第二套库连接、**不**写 `fsi.balance_*`。

内置情景：`gfc_2008`、`fed_hike_75`、`covid_2020`、`stagflation`（`scenario/catalog.py`）。
