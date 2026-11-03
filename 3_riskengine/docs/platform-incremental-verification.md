<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 在平台上按切片开发完善 RiskEngine

用平台 **持仓 + 市场数据** 完善引擎：一次只做 **一类资产 × 一个产品 × 一种估值 × 一个风险指标 × 一个测试情景**。

配套：接口 [`architecture-and-interfaces.md`](architecture-and-interfaces.md)、已实现清单 [`products-and-business.md`](products-and-business.md)、改文件清单 [`development-playbook.md`](development-playbook.md)、代码地图 [`codebase-guide.md`](codebase-guide.md)。

```
第 1 节枚举  →  选定一格
第 2 节索引  →  打开对应文件 / 表
第 3 节示例  →  按「固收 × BOND × PRICE/RATE × DV01 × fed_hike_75」抄改
```

数据只来自现有 `fsi.balance_*` / `fsi.mktdata_*` / `fsi.para_portfolio`。加载：

```python
from 3_riskengine import RiskEngine
from 3_riskengine.market import load_portfolio_snapshot

snapshot = await load_portfolio_snapshot(fund_id, as_of_date, db)
bound = RiskEngine().bind(snapshot)
```

不连库时用 `3_riskengine/tests/fixtures.py` 的 `sample_snapshot` / `sample_mmf_snapshot` / `sample_otc_snapshot`。

---

## 1. 枚举

权威枚举在代码里：改代码以枚举为准，本文与代码冲突时回写本文。

### 1.1 资产类（工作切片的「类」）

引擎用 `instruments/classify.py` 的 `factor_family` 归类，不是另造一张资产主数据。

| 资产类（切片名） | 含哪些 ProductKind | 主要风险因子 |
|---|---|---|
| 现金 | `CASH` | 无；非报表货币加 `FX` |
| 权益 | `EQUITY` | `EQUITY`，非本币加 `FX`，期权加 `VOLATILITY` |
| 基金 | `FUND` `ETF` | NAV / 权益代理 |
| 货币基金 | `MMF`（一等产品） | look-through 后的 RATE；赎回 |
| 固收 | `BOND` `CD` `DEPOSIT` `REPO` | `RATE` `CREDIT_SPREAD` |
| 外汇 | `FX` `FX_FORWARD` `FX_OPTION` | `FX` `VOLATILITY` |
| 上市衍生 | `FUTURE` `OPTION` | `EQUITY` `VOLATILITY` |
| 利率 OTC | `IRS` `SWAP` `SWAPTION` | `RATE` `VOLATILITY` |
| 信用 | `CDS` | `CREDIT_SPREAD` |
| 结构化 | `STRUCTURED` | 条款 metadata |

平台持仓字段 `Position.asset_class` 必须能映射到上表（见 §2.1）。未映射 → 当作 `CASH`。

### 1.2 产品（`ProductKind`）

枚举：`3_riskengine/core/contracts.py` → `ProductKind`。

| 产品 | 平台持仓来源 | 定价 adapter | 产品类文件 |
|---|---|---|---|
| `CASH` | `fsi.balance_cash` | riskengine `cash_balance` | `products/cash.py` |
| `EQUITY` | `fsi.balance_stock` | financepy `equity_spot` | `products/equity.py` |
| `ETF` | `fsi.balance_fund` / stock | financepy `equity_spot` | 通用 `Product` |
| `FUND` | `fsi.balance_fund` | riskengine `fund_nav` | 通用 `Product` |
| `BOND` | `fsi.balance_bond` | financepy `bond_discount_curve` | `products/fixed_income.py` `Bond` |
| `CD` | `fsi.balance_cd` | financepy `bond_zero_or_deposit` | 同上 `CertificateOfDeposit` |
| `DEPOSIT` | `fsi.balance_deposit` | financepy `ibor_deposit` | 同上 `Deposit` |
| `REPO` | metadata / 持仓 | financepy `repo_carry` | `products/fixed_income.py` `Repo` |
| `MMF` | 货币账本或 FUND+MMF 提示 | riskengine `mmf_nav_yield` | `products/money_market/fund.py` |
| `FX` | metadata `asset_class=FX` | ore `fx_spot` | `products/fx.py` |
| `FX_FORWARD` | metadata | ore `fx_forward` | 同上 |
| `FX_OPTION` | metadata `exercise` | ore `fx_option` | 同上 |
| `FUTURE` | metadata | ore `future` | `products/futures.py` |
| `OPTION` | metadata | ore `equity_option` | `products/options.py` |
| `IRS` / `SWAP` | metadata `notional` `pay_fixed` | ore `irs` / `swap` | `products/rates.py` |
| `SWAPTION` | metadata | ore `swaption`（不构造 Swaption 对象） | 同上 |
| `CDS` | metadata `hazard_rate` | ore `cds`（不构造 CDS 对象） | `products/credit.py` |
| `STRUCTURED` | metadata | ore `scripted_or_otc` | `products/structured.py` `StructuredNote` |

夹具证券代码（轨道 A）：

| 夹具 | 产品 |
|---|---|
| `sample_snapshot` | `BOND5Y` `US_EQ` `CASH` |
| `sample_mmf_snapshot` | `TBILL90` `CD180` `DEP30` `CASH`（PRODUCT 收成一只 MMF） |
| `sample_otc_snapshot` | `FXSPOT` `FXFWD` `FXOPT` `EQFUT` `EQOPT` `IRS5Y` `SWPT` `CDS5Y` |
| `sample_repo_structured_snapshot` | `REPO7D` `STRUCT1` |

### 1.3 估值定价（对「这一个产品」要做的定价动作）

合同：`AnalyticKind` 中的定价族 + `ValuationAPI`。

| 估值动作 | API | 含义 |
|---|---|---|
| 零冲击定价 | `bound.valuation().price(view=...)` | PV = 平台 `market_value_base` |
| 单因子再定价 | `revalue((Shock(...),))` | 只动对本产品有意义的因子 |
| Greeks | `greeks(shocks)` / `risk.sensitivity` | 中心差分 delta/gamma |
| 现金流 | `cashflows(view=...)` | 票息+兑付；现金=balance；MMF PRODUCT=nav |
| 冲击 PnL | `pnl(shocks)` | 与 `revalue` 的 pnl 同一数字 |
| 产品自身 | `product.value(market)` / `product.sensitivity(market, shocks)` | 管道按行调用的实现 |

`view`：`LOOK_THROUGH`（默认，按持仓行）或 `PRODUCT`（MMF 收成一只基金）。

冲击因子（`RiskFactorType`，每种可单独做成「一个估值格子」）：

| 因子 | 模式 | 典型幅度 | 谁应该动 |
|---|---|---|---|
| `RATE` | `ABSOLUTE` | `0.0001` = 1bp | 债 / CD / 存款 / IRS / MMF 穿透 |
| `CREDIT_SPREAD` | `ABSOLUTE` | `0.0001` | 固收、CDS |
| `EQUITY` | `RELATIVE` | `-0.01` | 股票、部分基金、期货/期权 |
| `FX` | `RELATIVE` | `0.01` | 非报表货币 |
| `VOLATILITY` | `RELATIVE` | `0.10` | 期权 / Swaption |

### 1.4 风险指标

**A. 投资风险 KPI**（`risk/kpis.py` `KPI_IDS`）

VaR, CVaR, ES, Volatility, Drawdown, Beta, Tracking Error, Risk Contribution, Gross Exposure, Net Exposure, Factor Exposure, Duration, DV01, KRD, CS01, Liquidity, Concentration, Counterparty Exposure, PFE, EPE, Leverage。

业务页映射：`4_business/investment_risk/domains.py` `MODULE_KPIS`。

**B. Risk Testing 十项**（`risk/testing.py` `TESTING_ANALYTICS`）

SENSITIVITY, STRESS, SCENARIO, REVERSE_STRESS, TAIL_RISK, KRD, PNL_EXPLAIN, HISTORICAL_BACKTEST, VAR_BACKTEST, XVA。

**C. 产品/账本指标**（不在 KPI_IDS 里，但是独立格子）

| 指标 | API |
|---|---|
| WAM / WAL / 影子偏离 | `bound.liquidity().mmf()` |
| 流动性分桶 | `bound.liquidity().buckets()` |
| 赎回覆盖 | `bound.liquidity().redemption(20.0)` |
| 组合敞口 | `bound.risk().exposure()` |
| 组合/基金 VaR | `bound.risk().var()` / `portfolio.risk` / `fund_risk` |
| 限额 | `bound.limits().evaluate()` |
| 治理 | `bound.governance().review()` |

**D. 限额目录**（`limits/policy.py` `LIMIT_IDS`）

Position, Issuer, Sector, Country, Currency, Counterparty, Gross/Net Exposure, Leverage, Liquidity, VaR, CVaR, Drawdown, Derivative Exposure, WAM, WAL, Shadow NAV Deviation。

单产品切片优先选 **对该产品有经济含义的指标**（债→DV01/KRD；股→Gross Exposure；MMF→WAM；CDS→CS01/XVA）。组合层 VaR 等放到「该类产品单券已绿」之后。

### 1.5 测试情景

内置目录：`3_riskengine/scenario/catalog.py` `SCENARIOS`（`2_processing.tools.risk_testing.scenarios` 再导出）。

| scenario_id | 类型 | 冲击 |
|---|---|---|
| `gfc_2008` | historical | 股 -37%、利差 +350bp、波动 +120%、FX 8% |
| `fed_hike_75` | hypothetical | 利率 +75bp、股 -6%、波动 +20% |
| `covid_2020` | historical | 股 -30%、利差 +200bp、波动 +150%、利率 -100bp |
| `stagflation` | hypothetical | 利率 +150bp、利差 +100bp、股 -18%、FX 5% |

自定义一格：构造 `Scenario` + `bound.scenario().run(mine)`，或只跑一个 `Shock`（那是估值格，不是情景格）。

### 1.6 平台持仓与市场字段（接到引擎的输入）

快照：`2_processing/tools/risk_testing/models.py` `PortfolioSnapshot` / `Position`。

持仓表：`fsi.balance_bond` `cd` `deposit` `stock` `fund` `cash` + `fsi.balance_portfolio_nav`。  
行情表：`fsi.mktdata_quotes` `fund_nav` `bond_risk` `fx_rate`。  
组合头：`fsi.para_portfolio`。

`Position` 字段：`security_code` `security_name` `asset_class` `currency` `market_value` `market_value_base` `duration` `convexity` `ytm` `coupon_rate` `maturity_date` `fx_rate` `metadata`。

OTC 放进 `metadata`：`notional` `strike` `volatility` `pair` `pay_fixed` `hazard_rate` `counterparty` `exercise` `option_type` `spot` `tenor_years`。

### 1.7 推荐切片顺序（开发 backlog）

按行做，一行未绿不换产品。

| # | 资产类 | 产品 | 估值格 | 指标格 | 情景格 |
|---|---|---|---|---|---|
| 1 | 现金 | `CASH` | 零冲击=账面 | Liquidity T0 | 无冲击 |
| 2 | 权益 | `EQUITY` | EQUITY -1% | Gross Exposure | `gfc_2008` 股市腿 |
| 3 | 固收 | `BOND` | RATE +1bp | DV01 | `fed_hike_75` |
| 4 | 固收 | `DEPOSIT` `CD` | RATE +1bp | Liquidity 短端 | 利率上移 |
| 5 | 货币基金 | `MMF` | PRODUCT=LOOK_THROUGH | WAM/WAL | 赎回 20% |
| 6 | 外汇 | `FX` `FX_FORWARD` `FX_OPTION` | FX / VOL | Factor Exposure | FX 相对冲击 |
| 7 | 上市衍生 | `FUTURE` `OPTION` | EQUITY / VOL | Derivative Exposure | 波动冲击 |
| 8 | 利率 OTC | `IRS` `SWAPTION` | RATE / VOL | DV01 | `fed_hike_75` |
| 9 | 信用 | `CDS` | CREDIT_SPREAD | CS01 / XVA | 利差扩大 |
| 10 | 组合 | 全产品账本 | 加总 PV≈NAV | VaR/CVaR、Limits | 四个内置情景 |

`REPO` / `STRUCTURED`：组装 + 零冲击账面 + FinancePy `repo_carry` / ORE scripted analytic 已接通。

---

## 2. 枚举去哪里索引

同一事实只在下列权威源维护。文档是目录，代码是数字。

### 2.1 资产类 / 产品

| 要查什么 | 打开 |
|---|---|
| `ProductKind` 列表 | `3_riskengine/core/contracts.py` |
| `asset_class` → 产品 | `instruments/classify.py` `_KIND_BY_ASSET` `product_kind_of` |
| 因子族 | `classify.factor_family` |
| 持仓 → Product | `products/assemble.py` `product_from_holding` |
| 产品定价公式 | `products/<family>.py` 的 `value` / `sensitivity` / `cashflows` |
| 路由 adapter | `core/resolve.py` `_PRODUCT_PRICE` |
| 业务含义一行表 | `docs/products-and-business.md` §1 |
| 加新产品改哪些文件 | `docs/development-playbook.md` §1 |
| 夹具一行持仓 | `tests/fixtures.py` |

### 2.2 持仓 / 市场数据

| 要查什么 | 打开 |
|---|---|
| 表名清单 | `market/platform.py` `HOLDING_TABLES` `MARKET_TABLES` |
| 加载实现（SQL） | `2_processing/tools/risk_testing/loader.py` |
| 再导出 | `3_riskengine.market.load_portfolio_snapshot` |
| Position / Snapshot 字段 | `2_processing/tools/risk_testing/models.py` |
| Market 对象（曲线、FX、价格） | `market/build.py` |
| 债券 YTM / duration | `fsi.mktdata_bond_risk` → loader 填进 Position |
| 汇率 | `fsi.mktdata_fx_rate` |
| 行情 / NAV | `fsi.mktdata_quotes` `mktdata_fund_nav` |

### 2.3 估值定价

| 要查什么 | 打开 |
|---|---|
| `price` `revalue` `greeks` `cashflows` `pnl` | `valuation/api.py` → `valuation/pipeline.py` |
| `AnalyticKind` | `core/contracts.py` |
| `Shock` / `RiskFactorType` | `core/contracts.py`（测试夹具再导出 processing 同名类型） |
| 冲击过滤（谁吃哪个因子） | `instruments/shocks.py` |
| FinancePy DF / bump | `adapters/financepy/` |
| ORE 再定价 / Trade 描述符 | `adapters/ore/pricing.py` `trade.py` |
| HTTP 已发布数字（勿改公式） | `core/kernel.py` |

### 2.4 风险指标

| 要查什么 | 打开 |
|---|---|
| KPI 名单与公式 | `risk/kpis.py` `KPI_IDS` / `kpi_*` |
| KPI 打包 | `compute_kpi_pack`；调用 `bound.risk().kpis()` |
| 业务页 → KPI | `4_business/investment_risk/domains.py` `MODULE_KPIS` |
| Testing 十项 | `risk/testing.py`；门面 `risk/api.py` |
| KRD 桶边界 | `instruments/classify.py` `KRD_BUCKETS` |
| 流动性桶 | `liquidity/buckets.py` |
| MMF WAM/WAL | `liquidity/mmf.py`；SFC 口径 **只** `limits/sfc.py` |
| 限额 | `limits/policy.py` `LIMIT_IDS`；度量 `limits/metrics.py` |
| 加新 KPI 改哪些文件 | `development-playbook.md` §2 |

### 2.5 测试情景

| 要查什么 | 打开 |
|---|---|
| 内置四情景 | `scenario/catalog.py` |
| 运行 | `bound.scenario().named("fed_hike_75")` 或 `.run(scenario)` |
| 压力（同一套冲击，analytic 不同） | `bound.stress().run(SCENARIOS["gfc_2008"])` |
| 前端/HTTP 目录 | processing 再导出；HTTP 仍走 kernel |

### 2.6 绑定入口一览

```
bound.products(view) / .trades() / .market()
bound.valuation().price|revalue|greeks|cashflows|pnl
bound.risk().kpis|krd|sensitivity|var|exposure|...
bound.scenario().named|run|catalog
bound.stress().run|reverse
bound.liquidity().mmf|buckets|redemption|report
bound.counterparty().xva|report
bound.limits().evaluate
bound.validation().pricing|cross_engine
bound.governance().review
```

定义：`core/engine.py` `BoundRiskEngine`。

---

## 3. 单切片示例：固收 × `BOND` × RATE 再定价 × `DV01` × `fed_hike_75`

这一节是 **一个格子** 的完整开发过程。换产品时只换「类 / 产品 / 冲击 / 指标 / 情景」五元组，步骤相同。

### 3.1 选定五元组

| 维 | 本例取值 | 索引 |
|---|---|---|
| 资产类 | 固收 | `classify.FIXED_INCOME` / `factor_family` → `RATE_CREDIT` |
| 产品 | `BOND` | `ProductKind.BOND`；`assemble` 第 83 行附近 |
| 持仓+行情 | 一只债的 YTM、久期、到期、账面 | `fsi.balance_bond` + `mktdata_bond_risk` |
| 估值 | 零冲击 PRICE + `RATE` +1bp | `Bond.sensitivity`；`valuation.revalue` |
| 指标 | `DV01` | `risk/kpis.py` `kpi_dv01` |
| 情景 | `fed_hike_75` | `scenario/catalog.py` |

先夹具 `BOND5Y`，再换平台真实 `fund_id`。

### 3.2 步骤（按序，一步未过不跳）

**第 1 步 — 确认平台行能进快照**

夹具已有：

```python
# tests/fixtures.py sample_snapshot() 中
# security_code=BOND5Y, asset_class=BOND, currency=HKD
# market_value_base=600_000, duration=4.5, ytm=0.035, coupon_rate=0.03
# maturity_date = as_of + 5y
```

平台：`load_portfolio_snapshot` 后应看到 `asset_class=="BOND"`，且 `ytm` / `duration` / `maturity_date` 非空。缺字段去补 `fsi.mktdata_bond_risk`，不要在 Product 里写死。

**第 2 步 — 组装与分类（产品格）**

索引：`classify.product_kind_of`、`assemble.product_from_holding` → `Bond`。

若 `asset_class` 新别名：只改 `_KIND_BY_ASSET`。若新产品：按 playbook §1 加枚举、类、assemble 分支、resolve。

本例 `BOND` 已存在，此步只断言：

```python
from importlib import import_module
from 3_riskengine.tests.fixtures import sample_snapshot

engine = import_module("3_riskengine").RiskEngine()
bound = engine.bind(sample_snapshot())
bond = next(p for p in bound.products("LOOK_THROUGH") if p.kind.value == "BOND")
assert bond.instrument.instrument_id == "BOND5Y"
assert bond.ytm == 0.035
assert engine.resolve(bond, "PRICE").adapter == "financepy"
```

**第 3 步 — 零冲击估值（估值格 1）**

索引：`Bond.value` → `_reprice(..., rate_shift=0)`；管道 `valuation/pipeline.py`。

恒等：该行 `base_pv == market_value_base`（1e-4）。禁止为对齐去改账面。

```python
priced = bound.valuation().price()  # 默认 LOOK_THROUGH
row = next(r for r in priced.trade_values if r["security_code"] == "BOND5Y")
assert abs(row["base_pv"] - 600_000.0) < 1e-4
assert row["engine"] == "financepy"
```

方向不对时只改 `products/fixed_income.py` 或 `adapters/financepy`，**不改** `core/kernel.py`。

**第 4 步 — 单因子再定价（估值格 2）**

索引：`Bond.sensitivity`；`instruments/shocks.applicable_shocks`。利率 +1bp，债券 PV 下降；权益冲击对该行 ≈0。

```python
from 3_riskengine.tests.fixtures import Shock, RiskFactorType, ShockMode

rate = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="rate +1bp")
eq = Shock(RiskFactorType.EQUITY, -0.10, ShockMode.RELATIVE)

rate_row = next(
    r for r in bound.valuation().revalue((rate,)).trade_values
    if r["security_code"] == "BOND5Y"
)
eq_row = next(
    r for r in bound.valuation().revalue((eq,)).trade_values
    if r["security_code"] == "BOND5Y"
)
assert rate_row["pnl"] < 0.0
assert abs(eq_row["pnl"]) < 1.0
```

实现落点（已有，完善时改这里）：

```python
# products/fixed_income.py
def sensitivity(self, market, shocks=()):
    base = self.value(market)
    shocked = _reprice(self, market, _rate_shift(self, market, shocks))
    shocked *= _fx_multiplier(self, market, shocks)
    return {"base_pv": base, "shocked_pv": shocked, "pnl": shocked - base}
```

**第 5 步 — 一个指标 DV01（指标格）**

索引：`risk/kpis.py` `kpi_dv01`；门面 `bound.risk().kpis()` 或 `compute_selected(snapshot, ("DV01",))`。

公式（当前实现）：再估值 PnL（RATE+1bp）+ 久期代理 `Σ MV × D × 0.0001`。

```python
from 3_riskengine.risk.kpis import kpi_dv01

pack = kpi_dv01(bound.snapshot)
assert pack["kpi"] == "DV01"
assert pack["result"]["reval_pnl"] < 0.0          # 加息亏钱
assert pack["result"]["duration_proxy"] > 0.0     # 代理为正的金额尺度
```

若指标不存在：按 playbook §2 在 `KPI_IDS` 加 id、写 `kpi_*`、纳入 `compute_kpi_pack`、需要进页则改 `MODULE_KPIS`、要进限额则改 `LIMIT_IDS`。

KRD 是相邻格子（仍是固收×BOND），不要和 DV01 绑在同一次提交里硬混：

```python
krd = bound.risk().krd(1.0)
fivey = next(b for b in krd["buckets"] if b["tenor"] == "5Y")
assert fivey["pv01"] < 0.0
```

**第 6 步 — 一个情景 `fed_hike_75`（情景格）**

索引：`scenario/catalog.py`；`bound.scenario().named`。再估值必须走 `valuation.revalue`，不要在情景里手写第二套债券 PV。

```python
hike = bound.scenario().named("fed_hike_75")
assert hike["analytic"] == "SCENARIO"
assert hike["pnl"] < 0.0   # 样本账本有 60% 债券 + 股票下跌腿
```

自定义只加息（仍是这一产品的情景格）：

```python
from 3_riskengine.core.contracts import Scenario, Shock, RiskFactorType, ShockMode

only_rates = Scenario(
    "bond_hike_75",
    "仅利率+75bp",
    "hypothetical",
    (Shock(RiskFactorType.RATE, 0.0075, ShockMode.ABSOLUTE, label="curve +75bp"),),
)
print(bound.scenario().run(only_rates)["pnl"])
```

**第 7 步 — 测试文件**

`3_riskengine/tests/test_slice_bond_dv01.py`：

```python
from importlib import import_module
import pytest
from .fixtures import Shock, RiskFactorType, ShockMode, sample_snapshot


def test_fixed_income_bond_rate_dv01_fed_hike():
    engine = import_module("3_riskengine").RiskEngine()
    bound = engine.bind(sample_snapshot())
    bond = next(p for p in bound.products("LOOK_THROUGH") if p.kind.value == "BOND")

    assert bond.instrument.instrument_id == "BOND5Y"
    assert engine.resolve(bond, "PRICE").adapter == "financepy"

    priced = bound.valuation().price()
    row = next(r for r in priced.trade_values if r["security_code"] == "BOND5Y")
    assert row["base_pv"] == pytest.approx(600_000.0)

    bump = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
    pnl = next(
        r for r in bound.valuation().revalue((bump,)).trade_values
        if r["security_code"] == "BOND5Y"
    )["pnl"]
    assert pnl < 0.0

    dv01 = bound.risk().kpis()["kpis"]["DV01"]["result"]
    assert dv01["reval_pnl"] < 0.0

    hike = bound.scenario().named("fed_hike_75")
    assert hike["analytic"] == "SCENARIO"
    assert hike["pnl"] < 0.0
```

```bash
python -m pytest 3_riskengine/tests/test_slice_bond_dv01.py -q --tb=short
```

改引擎后全量：

```bash
python -m pytest 3_riskengine/tests 2_processing/test/test_professional_risk_engine.py -q
```

**第 8 步 — 平台真实组合（同一五元组）**

```python
from datetime import date
from 3_riskengine import RiskEngine
from 3_riskengine.core.contracts import RiskFactorType, Shock, ShockMode
from 3_riskengine.market import load_portfolio_snapshot
from 3_riskengine.risk.kpis import kpi_dv01

snapshot = await load_portfolio_snapshot("你的组合代码", date(2026, 9, 1), db)
bound = RiskEngine().bind(snapshot)
bonds = [p for p in snapshot.positions if p.asset_class == "BOND"]
assert bonds, "该日无债券：先补 fsi.balance_bond / mktdata_bond_risk"

priced = bound.valuation().price(view="LOOK_THROUGH")
by_code = {r["security_code"]: r for r in priced.trade_values}
for pos in bonds:
    assert abs(by_code[pos.security_code]["base_pv"] - pos.market_value_base) < 1e-4

bump = Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE)
revalued = bound.valuation().revalue((bump,))
for pos in bonds:
    pnl = next(r for r in revalued.trade_values if r["security_code"] == pos.security_code)["pnl"]
    assert pnl <= 0.0, pos.security_code

print(kpi_dv01(snapshot)["result"])
print(bound.scenario().named("fed_hike_75")["pnl"])
```

失败先看 `snapshot.data_quality` 和 `asset_class` 映射，再改公式。

**第 9 步 — 记入产品文档**

在 [`products-and-business.md`](products-and-business.md) 该产品行注明平台已按「PRICE + RATE + DV01 + fed_hike_75」验过。不要在代码注释里写过程。

### 3.3 本切片会动到的文件（完善时）

| 情况 | 改哪里 |
|---|---|
| 分类错 | `instruments/classify.py` |
| 组装错 | `products/assemble.py` |
| 定价/冲击方向错 | `products/fixed_income.py`；必要时 `adapters/financepy` |
| 路由错 | `core/resolve.py` `_PRODUCT_PRICE["BOND"]` |
| DV01 公式/单位错 | `risk/kpis.py` `kpi_dv01` |
| 情景参数 | `scenario/catalog.py`（改内置会影响全平台，优先自定义 `Scenario`） |
| 缺 YTM | loader / `fsi.mktdata_bond_risk`，不造新表 |

不改：`FinancePy/` `ORE/` `Riskfolio-Lib/` 源码树；业务层不 `import financepy`；HTTP kernel 公式。

---

## 4. 换下一格时怎么抄

保持「一次一格」。例如下一格 **权益 × EQUITY × EQUITY -10% × Gross Exposure × gfc_2008**：

1. 枚举：§1.1 权益、§1.2 `EQUITY`、§1.3 `EQUITY` 相对冲击、§1.4 Gross Exposure、§1.5 `gfc_2008`。
2. 索引：`products/equity.py`、`kpi_gross_exposure`、夹具 `US_EQ`。
3. 把 §3.2 测试里的 `kind=="BOND"` 换成 `"EQUITY"`，`RATE` 换成 `EQUITY` -0.10，`kpi_dv01` 换成 `kpis()["kpis"]["Gross Exposure"]`，`fed_hike_75` 换成 `gfc_2008`。
4. 断言：`shocked_pv == 270_000`（夹具市值 300_000）；债券行在权益冲击下 PnL≈0。

OTC 下一格 **利率 × IRS × RATE +1bp × DV01**：夹具 `IRS5Y`，`resolve` adapter 为 `ore`，`ore_app is False`，实现落在 `products/rates.py` + `adapters/ore/pricing.py`。

MMF 下一格：`view="PRODUCT"` 与 `LOOK_THROUGH` PV 相等；指标用 `liquidity().mmf()` 的 WAM/WAL，不是 DV01；情景用 `redemption(20.0)`。

组合层格子（VaR、Governance）只在表 §1.7 第 1–9 行产品格已绿之后做。

---

## 5. 可独立运行的闭环脚本

路径：

- 引擎包（人工开发）：`3_riskengine/scripts/riskengine/`
  - `config.py` — 引入、参数、夹具 / **DB 真实组合**（`load_portfolio_snapshot`）
  - `objects.py` — `Engine` / `BoundEngine` / `SliceSpec`
  - `main.py` — BoundEngine 示例运行
- 启动器：`3_riskengine/scripts/run_riskengine.py`
- 闭环（嵌入引擎）：`3_riskengine/scripts/platform_workflow.py`

```bash
# 夹具
python 3_riskengine/scripts/run_riskengine.py
python 3_riskengine/scripts/run_riskengine.py --check
python 3_riskengine/scripts/run_riskengine.py --book otc

# 平台 DB 真实组合（与线上同一 loader）
python 3_riskengine/scripts/run_riskengine.py --list-funds
python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01
python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01 --check
python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01 --market-source db
python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01 --market-source openbb
# 需要时才开回退（默认 false，便于排查缺失行情）
python 3_riskengine/scripts/run_riskengine.py --fund-id BHMMF001 --as-of-date 2026-09-01 --market-source db --market-fallback --market-fallback-source openbb

# 闭环
python 3_riskengine/scripts/platform_workflow.py
python 3_riskengine/scripts/platform_workflow.py --fund-id BHMMF001 --as-of-date 2026-09-01
```

`book.market()` 返回 **单位行情**（主源 `--market-source db|openbb`），不是持仓市值。默认 **`fallback=false`**，缺失行情原样暴露在 `missing` / `[MARKET]`；仅当显式 `--market-fallback` 时用 `--market-fallback-source` 补齐。OpenBB 经 `5_integrations`，不进 RiskEngine 内核。

改定价/指标/情景：改 `riskengine/objects.py` 的 `BoundEngine`。`platform_workflow` 通过 `import riskengine` 嵌入。

