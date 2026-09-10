<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# RiskEngine 代码和说明

包根：`arisk/3_riskengine/`。对外类型：`RiskEngine` / `BoundRiskEngine`（`core/engine.py`）。版本与假设：`core/lineage.py`。

接口总表见 [`architecture-and-interfaces.md`](architecture-and-interfaces.md)。加产品/指标的步骤见 [`development-playbook.md`](development-playbook.md)。

---

## 1. 目录

```
3_riskengine/
├── core/           RiskEngine 门面、合同、路由、kernel、血缘
├── adapters/
│   ├── financepy/  FlatDiscountCurve、df_t、bump、修正久期
│   ├── ore/        Trade 描述符、OTC 定价、XVA、FlatForward DF
│   ├── riskfolio/  VaR/CVaR/RC、HRP/HERC/CVaR/RP 优化
│   └── vendor.py   探测，不把厂商类型漏出
├── products/       Equity / FI / MMF / FX / Future / Option / IRS / CDS
├── models/         按 EngineRef 取 Model
├── market/         从 snapshot 建 Market；NAV 序列
├── instruments/    资产分类、KRD 桶、冲击过滤、固收再定价
├── valuation/      price / revalue / greeks / cashflows / pnl
├── portfolio/      LOOK_THROUGH 账本、Fund Risk、Riskfolio 度量
├── trade/          snapshot → Trade DTO
├── risk/           testing 十项、KPI、backtest
├── stress/         委托 testing.stress / reverse_stress
├── scenario/       目录 + named 再估值
├── liquidity/      桶、赎回瀑布、MMF SFC
├── counterparty/   敞口聚合、XVA 分摊
├── pnl/            explain
├── limits/         限额引擎 + sfc 口径
├── validation/     定价/Greeks/回归/交叉引擎
├── governance/     review = limits + validation + MMF
├── utils/          日期/日历占位
└── tests/          phase A–J + wave 回归
```

禁止：业务代码 `import financepy|ORE|QuantLib|riskfolio`。禁止改工作树 `FinancePy/` `ORE/` `Riskfolio-Lib/`（参考源码，不是运行时）。运行时 ORE 只认 `site-packages/ORE`。

---

## 2. 核心模块

| 文件 | 职责 |
|---|---|
| `core/contracts.py` | `ProductKind` `AnalyticKind` `Shock` `Product.value/sensitivity` `Trade` `ValidationResult` |
| `core/resolve.py` | `resolve(product, analytic) → EngineRef` |
| `core/engine.py` | `RiskEngine` 持有三个 adapter；`bind` 得到 `BoundRiskEngine` |
| `core/lineage.py` | `RISKENGINE_NAME` `RISKENGINE_VERSION` `DEFAULT_ASSUMPTIONS` |
| `core/kernel.py` | `RevaluationKernel`：HTTP / `ProfessionalRiskEngine` 数字；**不要改公式** |

`BoundRiskEngine` 的每个 `valuation()` / `risk()` … 都是懒加载 API 对象，内部只拿 `self.engine` 与 `self.snapshot`。

---

## 3. 产品组装与估值

`products/assemble.py`

- `product_from_holding(position)`：按 `instruments.classify.product_kind_of` 构造具体 Product。
- `products_from_snapshot(snapshot, view)`：`LOOK_THROUGH` 展开 MMF holdings；纯货币账本在 `PRODUCT` 视角收成一只 `MoneyMarketFund`。

各产品文件：

| 文件 | 类 |
|---|---|
| `equity.py` | `Equity`（现货 + EQUITY/FX/VOL 相对冲击） |
| `fixed_income.py` | `Bond` `Deposit` `CertificateOfDeposit`（YTM + FinancePy DF） |
| `cash.py` | `Cash` |
| `money_market/fund.py` | `MoneyMarketFund`（NAV 或穿透；`wam_days` / `wal_days`） |
| `fx.py` | `FxSpot` `FxForward` `FxOption` |
| `futures.py` / `options.py` | `Future` `EquityOption` |
| `rates.py` / `credit.py` | `InterestRateSwap` `Swaption` `CreditDefaultSwap` |
| `otc.py` | OTC 共用条款字段 |

估值管道 `valuation/pipeline.py`：

1. `products_from_snapshot` → 每个 Product `resolve` → `model_for_ref`
2. `applicable_shocks` 按货币 / KRD tenor 过滤
3. 有冲击：`product.sensitivity`；无冲击：`product.value`
4. Greeks：中心差分（`flip_shock`）
5. 零冲击 PV = 账面市值

`valuation/api.py`：`pnl(previous=...)` 走 PnL Explain；否则走 `revalue`。

---

## 4. Adapter

| Adapter | 关键方法 | 失败回退 |
|---|---|---|
| FinancePy | `discount_factor` `shocked_discount_factor` `reprice_from_ytm` `modified_duration` | 解析 DF `exp(-r t)` |
| ORE | `map_snapshot` `price_product` `xva` `discount_factor`；美式 FX 期货期权 CRR | 解析公式 / 确定性 EPE |
| Riskfolio | `historical_var_cvar` `optimize` `risk_contribution` | NumPy 分位数 / 简易权重 |

ORE 定价：**零冲击 PV = 平台市值**，冲击增量来自 ORE NPV 差。Swaption 用 FlatForward 年金 + `blackFormula`；CDS 用 FlatHazardRate 生存概率 + FlatForward 贴现。不构造债券/Swaption/CDS 工具对象。

`Market.curves` 绑定 `discount_factor` / `reprice_from_ytm` / `ore_reprice`，产品文件不 import 厂商。

---

## 5. 风险与组合

| 文件 | 说明 |
|---|---|
| `risk/testing.py` | 十项分析的**唯一实现**；`stamp` 写血缘 |
| `risk/backtest.py` | NAV 路径；可选 duck-typed `market.series` |
| `risk/kpis.py` | 投资风险 KPI 包（VaR…Leverage） |
| `risk/api.py` | `calculate(name)` 按小写方法名分发 |
| `portfolio/aggregate.py` | 产品行加总、按资产类/引擎分组 |
| `portfolio/measures.py` | VaR/CVaR/RC；无单券收益时用 NAV×资产类 beta 隐含面板 |
| `scenario/catalog.py` | 四个内置情景 |
| `liquidity/buckets.py` | T0 / 1W / 1M / 3M / 6M / ILLIQUID + haircut |
| `liquidity/redemption.py` | 从最流动桶覆盖赎回 |
| `liquidity/mmf.py` | WAM/WAL + SFC 状态 |
| `counterparty/aggregate.py` | 按对手方/净额集聚合，XVA 按 \|PV\| 分摊 |
| `limits/engine.py` | 利用率 → GREEN/WARNING/BREACH/HARD_BREACH |
| `limits/sfc.py` | WAM 60 / WAL 120 / 偏离 50bp（预警 40bp） |
| `validation/cross_engine.py` | FinancePy DF vs ORE FlatForward |

`ProfessionalRiskEngine` 继续调用 `kernel()`，与 `risk/testing.py` **并行存在**。改统一路径时不要改 kernel 公式。

---

## 6. 测试怎么跑

在 `arisk/` 根目录：

```bash
python -m pytest 3_riskengine/tests 2_processing/test/test_professional_risk_engine.py 2_processing/test/test_portfolio_cockpit.py -q
```

| 测试 | 覆盖 |
|---|---|
| `test_phase_a_objects.py` … `test_phase_j_business.py` | 合同 → 业务委托 |
| `test_wave*.py` | HTTP / Quant / 限额 / 优化回归 |
| `test_imports.py` | 包可 import；`4_business` / `2_processing/api` 无厂商 import |

新功能：加 `3_riskengine/tests/test_*.py`，用 `tests/fixtures.py` 的内存 snapshot，不要连库。

---

## 7. 与外层的衔接

| 外层 | 文件 | 关系 |
|---|---|---|
| 加载快照 | `2_processing/tools/risk_testing/loader.py` | 唯一读库入口 |
| HTTP 风险测试 | `4_business/risk_testing/service.py` `execute_risk_test` | kernel |
| Python 风险测试 | 同文件 `run(snapshot, analytic)` | `bound.risk()` |
| 投资风险页 | `4_business/investment_risk/service.py` | KPI + limits |
| 优化 | `4_business/portfolio_optimization/service.py` | Riskfolio + 过闸 |
| Quant / Agent | `5_integrations/quant/api.py` | 只调 3_riskengine / 4_business |
| 驾驶舱状态 | `2_processing/api/routers/portfolio_cockpit.py` | 委托 `limits.sfc` |
