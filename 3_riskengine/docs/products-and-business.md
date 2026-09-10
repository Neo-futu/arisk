<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# RiskEngine 产品与金融业务功能

本文说明 **当前已实现** 的产品、指标、风险流程与报表。加新能力的步骤见 [`development-playbook.md`](development-playbook.md)。接口见 [`architecture-and-interfaces.md`](architecture-and-interfaces.md)。在平台上按持仓+行情做切片开发（枚举、索引、单产品单指标示例）见 [`platform-incremental-verification.md`](platform-incremental-verification.md)。

---

## 1. 产品目录（ProductKind）

平台 `asset_class`（及 metadata 别名）映射见 `instruments/classify.py` 的 `_KIND_BY_ASSET`。`FUND` 且名称/issuer/`fund_type` 含 MMF / MONEY MARKET / 貨幣市場 → **MMF**。

| ProductKind | 业务含义 | 代码 | 定价路径 | 平台来源 |
|---|---|---|---|---|
| `CASH` | 现金、未映射现金 | `products/cash.py` | 账面 | `fsi.balance_cash` |
| `EQUITY` | 股票现货 | `equity.py` | 市值；EQUITY/FX/VOL 相对冲击 | `fsi.balance_stock` |
| `ETF` | 上市基金 | 同权益现货路由 | 市值 | `fsi.balance_fund` / stock |
| `FUND` | 非 MMF 基金 | 通用 Product | NAV/市值 | `fsi.balance_fund` |
| `BOND` | 债券 | `fixed_income.py` | FinancePy FlatDiscountCurve 按 YTM 再定价 | `fsi.balance_bond` |
| `CD` | 存单 | 同上 | 同债券族 | `fsi.balance_cd` |
| `DEPOSIT` | 存款 | 同上 | IborDeposit 口径的 DF 再定价 | `fsi.balance_deposit` |
| `REPO` | 回购 | 合同已有 | 路由 financepy `repo_carry`；产品类待补 | — |
| `MMF` | 货币市场基金（一等产品） | `money_market/fund.py` | PRODUCT=NAV；LOOK_THROUGH=持仓加总 | 货币账本或 FUND+MMF 提示 |
| `FX` | 外汇现货 | `fx.py` | ORE；零冲击=账面 | metadata `asset_class=FX` |
| `FX_FORWARD` | 外汇远期 | `fx.py` | ORE `FxForward` | 持仓 metadata |
| `FX_OPTION` | 外汇期权（欧式/美式） | `fx.py` | ORE；美式另有期货期权 CRR | metadata `exercise` |
| `FUTURE` | 期货 | `futures.py` | ORE | metadata |
| `OPTION` | 权益期权 | `options.py` | ORE | metadata |
| `IRS` / `SWAP` | 利率互换 | `rates.py` | ORE `MakeVanillaSwap` | metadata `notional` `pay_fixed` |
| `SWAPTION` | 互换期权 | `rates.py` | 年金 + `blackFormula`（不构造 Swaption 对象） | metadata |
| `CDS` | 信用违约互换 | `credit.py` | FlatHazardRate + FlatForward（不构造 CDS 对象） | metadata `hazard_rate` |
| `STRUCTURED` | 结构化 / 脚本化 OTC | 合同已有 | 路由 ore `scripted_or_otc` | metadata |

**MMF 规则：** 份额层看 NAV；WAM/WAL、利率敏感度、赎回覆盖必须 **look-through** 到 Bond/CD/Deposit/Cash。SFC：WAM ≤ 60 日、WAL ≤ 120 日、影子价偏离 50bp（预警 40bp 或期限 90%）。

---

## 2. 冲击与情景（市场风险因子）

| RiskFactorType | 典型产品反应 |
|---|---|
| `RATE` | 债券/存款/CD/IRS；KRD 按 tenor 桶过滤 |
| `CREDIT_SPREAD` | 固收与 CDS；进入压力情景 |
| `EQUITY` | 股票、部分基金 |
| `FX` | 非报表货币持仓 |
| `VOLATILITY` | 期权 / 部分权益代理 |

`ShockMode`：`ABSOLUTE`（利率/利差用小数，0.0001=1bp）、`RELATIVE`（价格/波动用比例）。

内置情景（可编辑基准，不是逐日重放）：

| ID | 类型 | 要点 |
|---|---|---|
| `gfc_2008` | historical | 股 -37%、利差 +350bp、波动 +120%、FX 8% |
| `fed_hike_75` | hypothetical | 利率 +75bp、股 -6%、波动 +20% |
| `covid_2020` | historical | 股 -30%、利差 +200bp、波动 +150%、利率 -100bp |
| `stagflation` | hypothetical | 利率 +150bp、利差 +100bp、股 -18%、FX 5% |

---

## 3. 估值与投资风险流程

| 流程 | API | 业务用途 |
|---|---|---|
| 组合估值 | `valuation.price` | 报表货币 PV，零冲击=账面 |
| 情景再估值 | `valuation.revalue(shocks)` | What-if 市值 |
| Greeks | `valuation.greeks` / `risk.sensitivity` | 因子 delta/gamma |
| 现金流 | `valuation.cashflows` | 票息+兑付；MMF 为 NAV 或穿透 |
| 关键利率久期 | `risk.krd` | 1M…20Y+ 桶 PV01 |
| 敞口 | `risk.exposure` / `portfolio.aggregate` | Gross/Net/杠杆、按资产类 |
| 组合风险 | `portfolio.risk` | LOOK_THROUGH + 因子 PnL + Euler RC |
| 基金风险 | `portfolio.fund_risk` | PRODUCT + NAV 历史 VaR/CVaR |
| 优化 | `portfolio.optimize` / `risk.optimize` | HRP/HERC/CVaR/RP，**提案不是成交** |

KPI 包（`risk.kpis` / `investment_risk` 域）：

VaR, CVaR, ES, Volatility, Drawdown, Beta, Tracking Error, Risk Contribution, Gross/Net Exposure, Factor Exposure, Duration, DV01, KRD, CS01, Liquidity, Concentration, Counterparty Exposure, PFE, EPE, Leverage。

域 → KPI 映射在 `4_business/investment_risk/domains.py` 的 `MODULE_KPIS`。

---

## 4. Risk Testing 十项

实现：`risk/testing.py`。Python：`bound.risk()` 或 `4_business.risk_testing.service.run`。HTTP 仍走 kernel。

| 分析 | 输入 | 输出要点 |
|---|---|---|
| Sensitivity | shocks | 中心差分 delta/gamma |
| Stress | Scenario | 多因子同时再估值；`analytic=STRESS` |
| Scenario | Scenario / `named(id)` | 同上，`analytic=SCENARIO` |
| Reverse Stress | 情景 + 目标损失占 NAV% | 二分临界尺度 |
| Tail Risk | sigma 档 + 资本缓冲 | NAV 历史 σ；Riskfolio ES |
| KRD | bump_bps | 分桶 PV01 |
| PnL Explain | 上一期 snapshot | 五路恒等 |
| Historical Backtest | 默认 NAV；可选行情序列 | 累计收益、回撤 |
| VaR Backtest | 置信度、窗口 | Kupiec、红绿灯 |
| XVA | 违约强度、回收、融资利差 | CVA/DVA/FVA/MVA、EPE 曲线 20 步 |

---

## 5. 流动性、交易对手、限额、治理

**流动性**

- KPI `Liquidity`：现金 + 存款 + 久期≤0.25y 的固收，占 NAV（样本组合 10% 口径保持不变）。
- `liquidity.report`：产品分桶后加总；T0 无 haircut，ILLIQUID 25%。
- `redemption(pct)`：从 T0 起覆盖赎回金额；MMF 赎回压力用同一瀑布。
- `mmf()`：WAM/WAL vs 60/120 + 影子偏离。

**交易对手**

- KPI：按 issuer / security_name 聚 \|MV\|。
- `counterparty.report`：ORE Trade 描述符上的 counterparty / netting_set；组合 XVA 按 \|PV\| 分摊，**总额等于** `xva()`。
- PFE ≈ 确定性 EPE 曲线峰值；EPE ≈ 曲线均值。全量 MC 净额立方仍是扩展项（不跑 OREApp）。

**限额**（`limits.evaluate`）

Position / Issuer / Sector / Country / Currency / Counterparty（分组）、Gross/Net/Leverage、Liquidity（MIN）、VaR/CVaR/Drawdown、Derivative Exposure、**WAM/WAL/Shadow NAV Deviation**（仅 MMF 账本有值，混合账本为 0 故默认 GREEN）。

状态：达限=WARNING，超限=BREACH，达 hard 倍数=HARD_BREACH。`passed` 在 GREEN/WARNING 为真。

**验证与治理**

- `validation.run`：正 PV、Greeks 字段、利率上移不增加债重仓 PV、FinancePy vs ORE DF、可选 PnL 恒等。
- `governance.review`：限额 + 验证 + MMF 不得 `breach`。**不是交易指令。**

---

## 6. 报表（当前可出示的包）

| 报表 | 入口 | 给谁看 |
|---|---|---|
| 估值表 | `valuation.price` / `cashflows` | 估值 / 运营 |
| 敏感度表 | `risk.sensitivity` | 投资风险 |
| 情景/压力 PnL | `stress.run` `scenario.named` | 风控委员会 |
| 反向压力 | `stress.reverse` | 资本 / 流动性预案 |
| KRD 表 | `risk.krd` | 固收 |
| PnL 解释 | `pnl.explain` | 业绩归因 |
| 历史/VaR 回测 | `historical_backtest` `var_backtest` | 模型验证 |
| KPI 包 | `risk.kpis` | 投资风险各页 |
| 组合/基金风险 | `portfolio.risk` `fund_risk` | PORT 风格 |
| 优化提案 | `portfolio.optimize` + `limits.check` | 配置；须过闸 |
| 流动性与赎回 | `liquidity.report` | MMF / 现金管理 |
| XVA / 对手方 | `counterparty.report` | 信用 / 交易对手 |
| SFC MMF | `liquidity.mmf` + 驾驶舱 overview | 合规 |
| 限额仪表 | `limits.evaluate` | 风险治理 |
| Governance | `governance.review` | 放行检查 |

驾驶舱列表（AUM、七日收益、WAM/WAL、sparkline）仍由 SQL 供数；**是否 ok/warn/breach** 必须用 `limits.sfc.compliance_status`，与引擎同一口径。

---

## 7. 业务域对照

| 前端 / API | 业务包 | 引擎能力 |
|---|---|---|
| `/investment-risk` | `4_business.investment_risk` | KPI 域 + 流动性/对手方报告 |
| `/portfolio-opt` | `4_business.portfolio_optimization` | Riskfolio 优化 + 仿真仓 + 压力 |
| `/risk-testing` | `4_business.risk_testing` | 十项分析；HTTP=kernel，Python=`service.run` |
| `/risk-rules` 限额 | `4_business.risk_governance` | Limit Engine + Pre-Trade |
| `/portfolio-cockpit` | processing cockpit | SFC 状态函数在 RiskEngine |
| Quant / Agent | `5_integrations.quant` | 上述能力的 Python 门面 |

Pre-Trade / 优化提案默认 `is_trade_instruction=False`，不写 LIVE 账本。
