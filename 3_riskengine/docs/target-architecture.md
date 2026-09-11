<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# RiskEngine 目标架构（调研结论）

权威输入：工作树 `FinancePy/`、`ORE/`、`Riskfolio-Lib/` 与已安装运行时（`financepy`、`ORE` SWIG、`riskfolio`）；平台表 `fsi.balance_*` / `fsi.mktdata_*` / `fsi.para_portfolio`。  
本文件只述目标态与当前落地差距。不改第三方源码。Phase A–J 已落地：统一对象、Product/Market/Model、ORE Trade、组合聚合、Risk Testing、流动性、交易对手、限额、交叉验证、SFC 口径、业务域委托 RiskEngine。

给人读的接口 / 代码 / 产品 / 开发细化说明见 [`README.md`](README.md)。

---

## 1. FinancePy Architecture Map

```
VALUATION = PRODUCT + MODEL + MARKET
```

```
financepy/
├── utils/      Date, Calendar, DayCount, Schedule, Frequency, Currency
├── market/
│   ├── curves/     DiscountCurve, FlatDiscountCurve, IborSingleCurve, OISCurve, CDSCurve
│   ├── volatility/ EquityVolSurface, FXVolSurface, IborCapVolCurve, SwaptionVolSurface
│   └── prices/     空占位
├── models/     BlackScholes, Black, SABR, Heston, HW/BK/BDT trees, LMM, copula/Merton
└── products/
    ├── bonds/      Bond, BondZero, BondFRN, BondFuture, BondConvertible
    ├── credit/     CDS, CDSBasket, CDSTranche, CDSOption
    ├── equity/     EquityVanilla/American/Barrier/Asian/…
    ├── fx/         FXForward, FXVanillaOption, FXBarrier/Digital/…
    ├── rates/      IborDeposit, IborFRA, IborFuture, IborSwap, CapFloor, Swaption, OIS
    └── inflation/  InflationBond, InflationSwap
```

| 合同 | 事实 |
|---|---|
| 衍生品 | `product.value(value_dt, market…, model)` |
| 债券 | `dirty_price_from_ytm` / `dirty_price_from_discount_curve` / `dv01`（`npv()` 未完成） |
| CDS | `value(issuer_curve)`，模型内嵌 |
| 曲线风险 | `IborCurveRiskEngine.par_rate_risk_report()` |
| IborFuture | 曲线工具（`to_fra`），不是独立 PV 产品 |
| CD / CP / MMF | **无**专用产品；存款最近似 `IborDeposit` |

**不做：** 组合 VaR/ES、XVA、CSA/净额、组合优化、交易生命周期。

**对 RiskEngine：** 产品目录、日期/日历/日算、曲线与波动面、单工具定价与 Greeks 的 Python 架构参考。Adapter 只暴露我们需要的调用，不把 FinancePy 类型漏出业务层。

---

## 2. ORE Architecture Map

```
QuantLib → QuantExt → OREData → OREAnalytics → App / ORE-SWIG
```

工作流：

```
XML/API 输入（portfolio / market / curveconfig / todaysmarket / pricingengine / simulation / netting）
        ↓
OREApp + InputParameters
        ↓
TradeFactory → QL instruments ； TodaysMarket → 曲线/波动面
        ↓
AnalyticsManager
        ↓
npv / cashflow / sensitivity / stress / simulation cube / xva / var / pnl / SIMM
```

| 层 | 职责 |
|---|---|
| QuantExt | 扩展工具、交叉资产模型、定价引擎 |
| OREData | Trade XML、市场、曲线配置、约定、脚本化产品 |
| OREAnalytics | 情景模拟、敞口立方、XVA、VaR、PnL explain、SIMM、监管资本 |
| ORE-SWIG | 单一 Python 模块 `import ORE`（`site-packages/ORE`） |

**Python 入口：** `OREApp`、`InputParameters`、`AnalyticsManager`、`Portfolio`、`XvaCalculator`、`ExposureCalculator`。Trade 类在 SWIG 中常加 `ORE` 前缀（`OREBond`、`OREFxOption`）。

**覆盖：** 130+ TradeType（Swap/IRS、Swaption、CapFloor、Bond 族、CDS 族、FX Forward/Option/Barrier、Equity、Commodity、ScriptedTrade）。Analytics：NPV、敏感度、压力、MC 立方、CVA/DVA/FVA/MVA、PFE、历史/参数 VaR、PnL explain、SIMM、SA-CCR。

**不做：** 组合优化、MMF WAM/WAL/SFC 合规、OMS/账务、实时行情接入。

**对 RiskEngine：** 机构级 Trade ≠ Instrument、净额/抵押、情景→立方→XVA 工作流。复杂 OTC 不在 RiskEngine 内重写。运行时只认 `site-packages/ORE`；工作区 `ORE/` 是参考源码。

---

## 3. Riskfolio-Lib Architecture Map

```
returns DataFrame
    ↓
Portfolio.assets_stats() 或 HCPortfolio
    ↓
optimization / rp_optimization / wc_optimization / …
    ↓
weights + RiskFunctions（VaR_Hist / CVaR_Hist / RC）
```

| 类 / 模块 | 职责 |
|---|---|
| `Portfolio` | 凸优化：Classic / BL / FM / EP；目标 MinRisk / MaxRet / Sharpe |
| `HCPortfolio` | HRP / HERC / HERC2 / NCO |
| `ParamsEstimation` | μ、Σ、BL、因子、熵池 |
| `ConstraintsFunctions` | 权重、基数、换手、跟踪误差、图约束 |
| `RiskFunctions` | 历史 VaR/CVaR、风险贡献、Brinson |

优化风险度量代码：`MV`、`CVaR`、`EVaR`、`WR`、`MDD`、`CDaR` 等。经典 `Portfolio.optimization(rm=…)` **不含** 独立 `VaR`（VaR 在 `HCPortfolio` 与 `VaR_Hist`）。

**输入合同：** 资产收益矩阵，不是成交/曲线/工具。  
**不做：** 工具定价、XVA、期限结构、交易账本。

**对 RiskEngine：** 组合层 VaR/CVaR/ES、风险贡献、HRP/HERC/BL/CVaR 优化。持仓须先变成收益面板。

---

## 4. Product Capability Matrix

| 产品 | FinancePy | ORE | Riskfolio | RiskEngine 自有模型 |
|---|---|---|---|---|
| Equity（现货） | 现货作市场输入；期权产品丰富 | EquityPosition / EquityOption | 仅收益序列 | 市值 + 冲击 |
| Bond | Bond dirty/clean、DV01、OAS | Bond / Callable / Convertible | — | 曲线再定价包装 |
| MMF | — | — | 组合层 | **NAV/WAM/WAL/流动性** |
| Deposit | IborDeposit | CashPosition | — | 应计 + 期限 |
| CD | 无专用；近 BondZero / Deposit | Bond 族 | — | 与存款同一 Product 族 |
| Repo | — | BondRepo | — | 后期 |
| FX Spot | FinFXRate / 曲线 | FX spot 市场 | — | 报表货币折算 |
| FX Forward | FXForward | FxForward / FxSwap | — | Adapter |
| FX Option | FXVanilla/Barrier… | FxOption 全套 | — | 路由 ORE 或 FinancePy |
| Future | BondFuture；IborFuture 非 PV | BondFuture | — | 路由 |
| Option（EQ） | EquityVanilla/American… | EquityOption | — | 路由 |
| IRS / Swap | IborSwap / OIS | Swap / XCcy | — | **ORE** |
| Swaption | IborSwaption | Swaption | — | **ORE** |
| CDS | CDS + CDSCurve | CreditDefaultSwap | — | **ORE** |
| Fund / ETF | — | EquityPosition 近似 | 收益 | NAV 持仓 |
| Structured / OTC | 部分奇异期权 | ScriptedTrade | — | **ORE** |
| Cash | — | CashPosition | — | 账面 |

---

## 5. Trade Capability Matrix

| 能力 | 权威 | 当前落地 |
|---|---|---|
| Instrument ≠ Trade | ORE Envelope（对手方、净额、CSA、条款） | 仅有 snapshot Position |
| 生命周期（成交→持仓） | `fsi.transact_*` | 未进 RiskEngine |
| 净额 / 抵押 | ORE netting.xml / collateral | XVA 用确定性 EPE/ENE |
| 对手方主数据 | 持仓 issuer 元数据 | `issuer_name()` |
| 申购赎回（MMF） | 业务交易 | 未建模为 Trade |

目标：`trade/` 持有 Trade DTO；复杂 OTC 的 Trade XML/对象由 `adapters/ore/trade.py` 生成，不在业务层拼 XML。

---

## 6. Portfolio Risk Capability Matrix

| 度量 | 层 | 引擎 |
|---|---|---|
| Gross / Net Exposure | 持仓聚合 | RiskEngine |
| Factor Exposure / Beta / TE | 收益 + 基准 | RiskEngine / Riskfolio |
| VaR / CVaR / ES / Vol / DD | 组合收益 | **Riskfolio**（回退 NumPy） |
| Risk Contribution | 权重 + 协方差 | **Riskfolio** |
| Duration / DV01 / KRD / CS01 | 固收再定价 | **FinancePy** |
| FX Greeks | 期权/远期 | FinancePy 或 ORE |
| PFE / EPE / XVA | 交易对手 | **ORE**（回退曲线积分） |
| 优化 HRP/HERC/BL/CVaR | 权重提案 | **Riskfolio** |
| 压力 / 情景 PnL | 冲击 + 再估值 | RiskEngine 调度 FinancePy/ORE |

---

## 7. MMF Capability Matrix

MMF 是与 Equity/Bond 平级的 Product，不是遗留旁路。SFC 阈值（WAM 60 日、WAL 120 日、影子价偏离）是 **Limits/Validation**，不是另一套引擎。

| 指标 | 数据 | 计算归属 |
|---|---|---|
| NAV / 七日收益 | `fsi.balance_portfolio_nav` / `balance_portfolio_mmf` | Product.value + market |
| Accrual / Yield | 持仓票息与存款 | money_market model |
| Maturity / WAM / WAL | `balance_bond/cd/deposit` 期限 | MMF risk model |
| DLA / WLA / Cash | 流动性桶 | liquidity engine |
| Issuer / Credit / Concentration | 发行人、评级 | concentration + credit |
| Deposit / CD / Repo | 同一组合内工具 | 各自 Product，再聚合 |
| Redemption | 申赎与流动性缓冲 | liquidity.redemption |
| 组合压力 | 利率/信用/赎回冲击 | scenario → valuation → aggregate |

当前 WAM/WAL 与 SFC 状态由 `products/money_market/` + `liquidity/mmf.py` + `limits/sfc.py` 计算；cockpit SQL 只提供输入，状态函数与 RiskEngine 同一口径。

---

## 8. ARISK → Third Party Mapping

```
fsi.para_portfolio                 → Portfolio（LIVE / SIMULATION / BENCHMARK）
fsi.balance_bond                   → BondPosition → Bond → FinancePy Bond
fsi.balance_cd / balance_deposit   → MoneyMarket instruments → FinancePy Deposit / BondZero
fsi.balance_stock                  → EquityPosition → 市值 / FinancePy 期权（若有）
fsi.balance_fund                   → Fund / MMF Product
fsi.balance_cash                   → Cash
fsi.balance_portfolio_nav          → NAV 收益面板 → Riskfolio
fsi.mktdata_quotes / fx_rate       → MarketSnapshot.prices / fx
fsi.mktdata_bond_risk              → duration / ytm 诊断；定价以曲线为准
fsi.mktdata_fund_nav               → 基金 NAV
fsi.transact_*                     → Trade（后期）
fsi.svc_risk_snapshot              → 结果落库，非主数据
```

不建第二套持仓主数据。Canonical 对象是计算 DTO。

| 业务域 | 只调用 |
|---|---|
| `4_business/investment_risk` | `RiskEngine.risk / liquidity / counterparty` |
| `4_business/portfolio_optimization` | `RiskEngine` → Riskfolio adapter |
| `4_business/risk_testing` | `RiskEngine.valuation / stress / scenario / pnl` |

业务代码禁止 `import financepy|ORE|riskfolio|QuantLib`。

---

## 9. RiskEngine Target Architecture

```
3_riskengine/
├── utils/          dates, calendars, schedules, conventions, day_count, currency, math
├── market/         prices, fx, curves, credit, volatility, macro, snapshot
├── models/         equity, rates, credit, fx, volatility, fixed_income, money_market
├── products/       equity, fixed_income, money_market, fx, futures, options, rates, credit, funds, structured
├── valuation/      price / revalue / greeks / pnl ；内部 resolve()
├── portfolio/      portfolio, position, exposure, aggregation, risk_contribution
├── trade/          trade, lifecycle, netting, collateral, counterparty
├── pnl/            explain, attribution, reconciliation
├── risk/           market, equity, rates, credit, fx, factor, concentration, leverage, liquidity, counterparty, portfolio
├── scenario/       base, historical, hypothetical, macro, combined, reverse
├── stress/         sensitivity, stress, reverse, tail, backtest
├── liquidity/      current, bucket, liquidation, redemption, funding, margin
├── counterparty/   exposure, ee, pfe, epe, netting, collateral, xva, wwr
├── limits/         engine, rules, breach, escalation
├── validation/     pricing, greeks, risk, scenario, cross_engine, regression
├── governance/     limits + validation review（非交易指令）
├── core/           RiskEngine facade, contracts, lineage, resolve
└── adapters/
    ├── financepy/  products, curves, valuation
    ├── ore/        trade, market, pricing, exposure
    └── riskfolio/  portfolio, risk, optimization
```

三个视角同一对象模型：Product View、Investment/Trading View、Risk Management View。

---

## 10. RiskEngine Object Model

```
MarketSnapshot(valuation_date, prices, fx, curves, credit_curves, volatility, macro)
Product          value / cashflows / sensitivity     （接口统一，风险模型按产品）
Instrument       合约规格（ISIN、期限、货币、payoff）
Trade            Instrument + Counterparty + CSA + 条款 + Portfolio
Position         持仓数量与账面；指向 Instrument / Trade
Portfolio        LIVE | SIMULATION | MODEL | BENCHMARK
RiskFactor / Shock / Scenario
ValuationContext + Result lineage（见 §33 字段）
```

`Instrument ≠ Trade ≠ Position`。MMF 份额是 Product；申购赎回是 Trade；账面是 Position。

每个 Result 必含：`portfolio_id`、`position_id`、`instrument_id`、`trade_id`、`valuation_date`、`market_data_date`、`calculation_time`、`engine`、`engine_version`、`model`、`model_version`、`parameters`、`assumptions`、`data_quality`、`result`、`validation_status`。

---

## 11. Engine Routing Design

业务不得选择底层库。唯一入口：

```python
engine.resolve(product, risk_type, valuation_context) -> AdapterCall
```

| Product / 问题 | 默认路由 | 回退 |
|---|---|---|
| Equity 现货 | Market / FinancePy | 市值 |
| Bond / Deposit / CD | FinancePy | 久期代理 |
| MMF | RiskEngine money_market + FinancePy 底层工具 | 现有 SQL 指标（过渡） |
| FX / FX Option | FinancePy；美式/障碍优先 ORE | QuantLib 路径 |
| IRS / Swaption / CDS / 复杂 OTC | **ORE** | 拒绝或标记 UNPRICED |
| Portfolio VaR/CVaR/优化 | **Riskfolio** | NumPy/SciPy |
| XVA / PFE / 净额模拟 | **ORE** cube | 确定性 EPE/ENE |
| 组合聚合 / 限额 / 血缘 | **始终 RiskEngine** | — |

`resolve` 输出写入 Result.engine，供交叉验证。

---

## 12. Unified Valuation Design

```python
valuation.price(snapshot)           # 无冲击
valuation.revalue(snapshot, shocks) # 情景市场
valuation.greeks(snapshot, shocks)
valuation.pnl(snapshot, previous=None)
```

内部：

```
Position → Product
        → resolve(product, PRICE, ctx)
        → adapter.value(product, market, model)
        → 报表货币 FX
        → Portfolio 加总
```

压力流：

```
Scenario → Market shock → valuation.revalue → PnL → 聚合 → Limits
```

PnL 分解：Position + Carry + Rates + FX + Credit + Equity + Volatility + Residual；残差超容差 → Validation 异常。

---

## 13. Migration Plan

约束：每 Phase 完成接口、测试、文档后再进入下一 Phase。不改 `FinancePy/` `ORE/` `Riskfolio-Lib/` 源码。HTTP `/api/v1/fsi/risk-testing/*` 与 `ProfessionalRiskEngine` 委托保持。

| Phase | 内容 | 完成判据 |
|---|---|---|
| **A** | Core：contracts 对齐、`resolve` 骨架、Result lineage、目录占位、禁止业务 import 厂商 | **完成**（`core/contracts.py`、`core/resolve.py`、`tests/test_phase_a_objects.py`） |
| **B** | Product/Market/Model 接口；平台表 → Canonical DTO | **完成**（Equity / Bond / MMF / Deposit / CD；PRODUCT + LOOK_THROUGH；`tests/test_phase_b_products.py`） |
| **C** | Unified valuation 路由；FinancePy 曲线/债券真正 `value` 包装 | **完成**（`valuation/pipeline.py`；Equity / Bond / MMF / Deposit / CD；`tests/test_phase_c_valuation.py`） |
| **D** | ORE Trade / 复杂产品：FX、FX Forward、FX Option、Future、Option、IRS、Swaption、CDS | **完成**（`adapters/ore/trade.py` + `pricing.py`；`tests/test_phase_d_ore_products.py`） |
| **E** | 组合聚合 + Riskfolio：Portfolio Risk / Fund Risk；VaR、CVaR、Risk Contribution、Optimize | **完成**（`portfolio/aggregate.py` + `measures.py`；`tests/test_phase_e_portfolio.py`） |
| **F** | Risk Testing：Sensitivity / Stress / Scenario / Reverse Stress / Tail Risk / KRD / PnL Explain / Historical Backtest / VaR Backtest / XVA | **完成**（`risk/testing.py`；`tests/test_phase_f_risk_testing.py`） |
| **G** | Liquidity / Counterparty 分产品再聚合 | **完成**（`liquidity/buckets.py` + `counterparty/aggregate.py`；`tests/test_phase_g_liquidity_counterparty.py`） |
| **H** | Limits / Validation / 交叉引擎 | **完成**（SFC WAM/WAL 限额；FinancePy vs ORE FlatForward；`tests/test_phase_h_limits_validation.py`） |
| **I** | MMF WAM/WAL 与 SFC 限额对账 cockpit | **完成**（`limits/sfc.py` 为 cockpit 口径；`tests/test_phase_i_mmf_sfc.py`） |
| **J** | 三大业务域只依赖 RiskEngine | **完成**（`4_business` 计算入口走 RiskEngine；HTTP PRE 仍委托 kernel；`tests/test_phase_j_business.py`） |

**当前差距（最新态）：** RiskEngine 1.0.0 已覆盖统一对象、路由、估值、组合聚合、Risk Testing、流动性、交易对手、限额、验证、Governance。`ProfessionalRiskEngine` / HTTP `/api/v1/fsi/risk-testing/*` 仍委托 `core/kernel` 以保持已发布数字。SQL 只提供输入。未跑 `OREApp` XML。

---

## 14. Phase A Implementation Plan

**范围（仅此）：** RiskEngine Core。不铺开产品定价、不迁 MMF SQL、不接 OREApp XML。

1. **对象合同**  
   扩展 `core/contracts.py`：`ProductKind`、`PortfolioKind`（LIVE/SIMULATION/MODEL/BENCHMARK）、完整 Result lineage 字段、`EngineRef`。现有 `Instrument/Position/Portfolio/MarketSnapshot` 与 `fsi.*` 对齐，不新开主数据。

2. **`core/resolve.py`**  
   静态路由表（§11）。输入 `product_kind + analytic`；输出 `{adapter, model, fallback}`。无厂商 import。

3. **目录占位**  
   创建 `utils/` `models/` `products/` `portfolio/` `trade/` 的 `__init__.py` + 模块说明；现有 `valuation/risk/scenario/…` 保持可 import。`products/money_market/` 先放接口，不算 WAM。

4. **Facade**  
   `RiskEngine.resolve(...)` 公开。`bind(snapshot)` 保留。`adapters_status` 继续报告三库。

5. **测试**  
   - 路由表：Bond→financepy、IRS→ore、VaR→riskfolio、MMF→riskengine  
   - Result lineage 必填键  
   - `4_business` / `2_processing/api` 不得出现厂商 import（已有护栏加强）  
   - 现有 3_riskengine 全量回归仍绿  

6. **文档**  
   本文件保持权威；`README.md` 链到本文；`moduleinfo.md` 只写最新态。

**Phase A 已完成。** Phase B 已完成（见 §15）。

**明确不做（本 Phase）：** 改 kernel 再定价公式、改 FinancePy/ORE/Riskfolio 源码、把 MMF SQL 搬进本 Phase、ORE Monte Carlo XML。

---

## 15. Phase B Implementation Plan

**范围（仅此）：** FinancePy 风格 Product / Market / Model。产品：Equity、Bond、MMF、Deposit、CD。不迁 MMF SQL、不接 OREApp XML、不改 kernel 公式（除非产品 `value` 需要）。

1. **从平台快照构造产品**  
   `products/assemble.py`：`fsi.balance_*` 行 → `Equity` / `Bond` / `Deposit` / `CertificateOfDeposit` / `MoneyMarketFund` / `Cash`。`FUND` 且 `fund_type`/`issuer`/`名称` 含 MMF → `ProductKind.MMF`。

2. **两种视角**  
   - `ViewMode.PRODUCT`：货币市场账本收成一只 `MoneyMarketFund`（NAV）；含股票的混合账本保持分产品。  
   - `ViewMode.LOOK_THROUGH`：穿透到 Bond / CD / Deposit / Cash / Equity 持仓。

3. **Market**  
   `market/build.py`：价格与 FX 来自 snapshot；`discount_factor` / `shocked_discount_factor` 绑定 FinancePy adapter。产品不 import 厂商。

4. **MMF 一等产品**  
   `MoneyMarketFund`：`value` 默认 NAV；`MMF_LOOK_THROUGH` 对 holdings 加总；`wam_days` / `wal_days` 按市值加权剩余天数；`sensitivity` 有 holdings 时走穿透。SFC 60/120 限额仍在 `2_processing`（Phase I）。

5. **测试**  
   `tests/test_phase_b_products.py`：PRODUCT vs LOOK_THROUGH、FI 零冲击 PV 恒等、Equity 相对冲击、`FUND`+MMF 提示映射为 MMF。

**Phase B 已完成。** Phase C 已完成（见 §16）。

**明确不做（本 Phase）：** 把 `2_processing/tools/mmf` SQL 搬进 RiskEngine、OREApp XML、改 FinancePy/ORE/Riskfolio 源码。

---

## 16. Phase C Implementation Plan

**范围（仅此）：** 统一估值入口 `price` / `revalue` / `greeks` / `cashflows` / `pnl`。先打通 Equity、Bond、MMF、Deposit、CD。不迁 MMF SQL、不接 OREApp XML。

1. **路由**  
   `valuation/pipeline.py`：snapshot → Product → `resolve` → `product.value/sensitivity/cashflows(market, model)`。默认 `LOOK_THROUGH`（一行一持仓，与 `fsi.balance_*` 对齐）；MMF 账本可 `view=PRODUCT`。

2. **FinancePy 包装**  
   `FinancePyAdapter.reprice_from_ytm` 经 `Market.curves` 供给 Bond / Deposit / CD。产品不 import `financepy`。零冲击 PV 与账面市值恒等，有冲击时与 `RevaluationKernel` 容差内一致。

3. **Greeks / Cashflows / PnL**  
   Greeks：中心差分再估值。Cashflows：固收票息+兑付，MMF NAV 或穿透现金流。PnL：冲击路径走 `revalue`；跨期 explain 仍用 kernel。组合层分解见 Phase E。

4. **测试**  
   `tests/test_phase_c_valuation.py`：五族产品入口、与 kernel 回归、MMF 双视角、Equity 相对冲击。

**Phase C 已完成。** Phase D 已完成（见 §17）。

**明确不做（本 Phase）：** 把 MMF SQL 搬进 RiskEngine、OREApp XML、改 FinancePy/ORE/Riskfolio 源码、改 kernel 公式。

---

## 17. Phase D Implementation Plan

**范围（仅此）：** ORE Trade / 复杂产品。FX、FX Forward、FX Option、Future、Option、IRS、Swaption、CDS。禁止 OREApp XML 半接入。

1. **产品**  
   `products/fx.py`、`futures.py`、`options.py`、`rates.py`、`credit.py`。从 snapshot `asset_class` / metadata 构造。`ProductKind.SWAPTION` 入合同。

2. **Trade 描述符**  
   `adapters/ore/trade.py` 生成 ORE 风格 descriptor 与 `contracts.Trade`。业务层不拼 XML。`bound.trades()` 导出。

3. **定价**  
   `adapters/ore/pricing.py`：ORE-SWIG `FxForward` / `MakeVanillaSwap` / `VanillaOption`；Swaption 用 `FlatForward` 年金 + `blackFormula`；CDS 用 `FlatHazardRate` 生存概率 + `FlatForward` 贴现（与 XVA 同源）。零冲击 PV = 平台市值；冲击增量由 ORE NPV 差给出。失败回退解析公式。`Market.curves["ore_reprice"]` 绑定 adapter，产品不 import ORE。不构造 `Swaption` / `CreditDefaultSwap` / `FixedRateBond` 工具对象。

4. **测试**  
   `tests/test_phase_d_ore_products.py`：八类产品组装与 `resolve→ore`、零冲击账面恒等、利率/FX/波动/信用冲击、美式 FX 期权回归、无 OREApp。

**Phase D 已完成。** Phase E 已完成（见 §18）。

**明确不做（本 Phase）：** OREApp / InputParameters XML、改 ORE 源码、把 MMF SQL 搬进 RiskEngine。

---

## 18. Phase E Implementation Plan

**范围（仅此）：** 把产品估值聚成 Portfolio Risk / Fund Risk，并接通 Riskfolio：VaR、CVaR、Risk Contribution、Optimize。不迁 MMF SQL、不接 OREApp XML。

1. **聚合**  
   `portfolio/aggregate.py`：`valuation.revalue` 的产品行按 `LOOK_THROUGH` 加总为组合账本（PV、权重、资产类、引擎）。`risk.exposure` 走同一账本。

2. **两层风险**  
   - Portfolio Risk：穿透持仓 + 因子冲击 PnL 贡献 + 统计 Euler RC。  
   - Fund Risk：`ViewMode.PRODUCT`（MMF 为一只基金）+ `fsi.balance_portfolio_nav` 历史 VaR/CVaR。

3. **Riskfolio**  
   `VaR_Hist` / `CVaR_Hist` / `Risk_Contribution`；优化 HRP/HERC/CVaR/RP 仍走 adapter，缺库或失败回退 NumPy。无按资产收益序列时，用 NAV × 资产类 beta 生成隐含收益面板。产品不 import `riskfolio`。

4. **测试**  
   `tests/test_phase_e_portfolio.py`：现金账本加总、MMF 基金一层 vs 穿透、OTC 资产类、RC 归一、HRP 提案。

**Phase E 已完成。** Phase F 已完成（见 §19）。

**明确不做（本 Phase）：** SFC cockpit、改 Riskfolio 源码、把 MMF SQL 搬进 RiskEngine、OREApp XML。

---

## 19. Phase F Implementation Plan

**范围（仅此）：** 把已有 Risk Testing 十项分析接到统一 RiskEngine：Sensitivity、Stress、Scenario、Reverse Stress、Tail Risk、KRD、PnL Explain、Historical Backtest、VaR Backtest、XVA。再估值走 Product + Market + Model；组合层走 Riskfolio；XVA 走 ORE Trade 映射。不迁 MMF SQL、不接 OREApp XML、不改 `ProfessionalRiskEngine` / `core/kernel` 公式。

1. **统一实现**  
   `risk/testing.py` 为唯一实现。`bound.risk()` / `bound.stress()` / `bound.scenario()` / `bound.pnl()` / `bound.counterparty()` 委托同一套函数。`EngineRouting` 把 STRESS/SCENARIO/REVERSE_STRESS 标为产品再估值；TAIL_RISK/VAR_BACKTEST 标 Riskfolio；KRD 标 FinancePy；XVA 标 ORE。

2. **再估值路径**  
   Sensitivity / Stress / Scenario / Reverse Stress / KRD 调用 `valuation.revalue`（中心差分 Greeks、情景冲击、二分临界尺度、tenor 过滤的 RATE 桶）。零冲击 PV 仍等于账面市值。PnL Explain 保持五路恒等：`carry + rates + fx + position + residual == total`；credit / equity / volatility 只是 leftover 标签。

3. **统计与对手方**  
   Tail Risk / VaR Backtest 用 NAV 收益面板走 Riskfolio adapter（缺库回退 NumPy）。Historical Backtest 默认 NAV 路径，可选 duck-typed `market.series`。XVA 用 `adapters/ore` 的 Trade 描述符 + FlatForward/FlatHazardRate EPE/ENE，`ore_app=False`。

4. **Governance**  
   `bound.governance().review()` = Limits + Validation，`is_trade_instruction=False`。

5. **测试**  
   `tests/test_phase_f_risk_testing.py`：路由、产品再估值压力/情景、反向压力打到目标损失、KRD 5Y PV01、PnL 恒等、XVA 无 OREApp、Governance 放行。

**Phase F 已完成。** Phase G–J 已完成（见 §20–§23）。

**明确不做（本 Phase）：** OREApp / InputParameters XML、改 kernel 以保持 HTTP 数字、把 MMF SQL 文件搬进 RiskEngine、改 FinancePy/ORE/Riskfolio 源码。

---

## 20. Phase G Implementation Plan

**范围（仅此）：** Liquidity 与 Counterparty 按产品计算再聚合。MMF 赎回走流动性瀑布。XVA 按 Trade 权重分到对手方 / 净额集。不迁 MMF SQL、不接 OREApp XML。

1. **流动性**  
   `liquidity/buckets.py`：每个 Product 落入 T0/1W/1M/3M/6M/ILLIQUID；再按资产类加总。`redemption(pct)` 从最流动桶开始覆盖赎回。`ratio()` 保持原 KPI 公式（现金+存款+短久期）。

2. **交易对手**  
   `counterparty/aggregate.py`：产品 PV + ORE Trade 描述符 → 对手方 / 净额集。组合 XVA 按 |PV| 权重分摊，总额与 `xva()` 一致。`ore_app=False`。

3. **测试**  
   `tests/test_phase_g_liquidity_counterparty.py`。

**Phase G 已完成。** Phase H 已完成（见 §21）。

**明确不做（本 Phase）：** OREApp Monte Carlo 净额立方、改 kernel。

---

## 21. Phase H Implementation Plan

**范围（仅此）：** Limits 纳入 SFC WAM/WAL/影子偏离；Validation 增加 FinancePy vs ORE 交叉引擎。不构造 `FixedRateBond` / `Swaption` / `CreditDefaultSwap`。

1. **限额**  
   非 MMF 账本 WAM/WAL=0（样本组合保持 GREEN）。MMF 账本用 look-through 加权天数，对照 60/120 日。

2. **交叉引擎**  
   同一利率、同一年期：FinancePy `FlatDiscountCurve.df_t` vs ORE `FlatForward.discount`。零冲击 PV 与 kernel 恒等；利率上移符号一致。

3. **Governance**  
   `review()` = Limits + `validation.run()` + MMF SFC 状态。

4. **测试**  
   `tests/test_phase_h_limits_validation.py`。

**Phase H 已完成。** Phase I 已完成（见 §22）。

**明确不做（本 Phase）：** 构造 QL 债券工具对象、OREApp XML。

---

## 22. Phase I Implementation Plan

**范围（仅此）：** MMF WAM/WAL 与 SFC 限额对账。cockpit 状态函数与 RiskEngine 同一口径。SQL 仍只读输入。

1. **口径**  
   `limits/sfc.py`：WAM 60 日、WAL 120 日、影子偏离 50bp（预警 40bp / 90% 期限）。`2_processing` cockpit `_compliance_status` 委托该函数。

2. **计算**  
   `liquidity.mmf()`：PRODUCT 视角 `MoneyMarketFund.wam_days/wal_days`，与 cockpit 传入的同一组数字对账。

3. **测试**  
   `tests/test_phase_i_mmf_sfc.py` 与既有 `2_processing/test/test_portfolio_cockpit.py`。

**Phase I 已完成。** Phase J 已完成（见 §23）。

**明确不做（本 Phase）：** 把 MMF 指标 SQL 文件搬进 RiskEngine。

---

## 23. Phase J Implementation Plan

**范围（仅此）：** `investment_risk` / `portfolio_optimization` / `risk_testing` 的计算入口只调用 RiskEngine。删除业务层重复定价/VaR。HTTP `/api/v1/fsi/risk-testing/*` 仍走 `ProfessionalRiskEngine` → kernel，以保持已发布数字。

1. **investment_risk**  
   流动性 / 交易对手域附加 `bound.liquidity().report()` / `bound.counterparty().report()`。

2. **risk_testing**  
   `service.run(snapshot, analytic)` 走 `bound.risk()`；`execute_risk_test` 不变。Quant `testing.run` 委托 `service.run`。

3. **portfolio_optimization**  
   已走 Riskfolio adapter + Limit Engine，保持。

4. **测试**  
   `tests/test_phase_j_business.py`。

**Phase J 已完成。** 目标架构落地为 RiskEngine 1.0.0。

**明确不做（本 Phase）：** 改 HTTP 数字、OREApp XML、改 FinancePy/ORE/Riskfolio 源码。
