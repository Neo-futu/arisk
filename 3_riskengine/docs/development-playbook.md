<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# RiskEngine 开发细化说明

给开发与业务一起 **按产品、指标、风险流程、报表** 往上长。先读 [`architecture-and-interfaces.md`](architecture-and-interfaces.md) 与 [`products-and-business.md`](products-and-business.md)。代码落点见 [`codebase-guide.md`](codebase-guide.md)。在平台上结合持仓与行情、按「一类资产 × 一个产品 × 一种估值 × 一个指标 × 一个情景」开发见 [`platform-incremental-verification.md`](platform-incremental-verification.md)。

原则：每加一块，**接口 + 测试 + 文档** 同一次提交。不改三库源码，不绕过 adapter，不改 `core/kernel.py` 公式（HTTP 数字）。

---

## 0. 红线

1. 厂商 import 只允许出现在 `3_riskengine/adapters/**`。
2. 不跑 `OREApp` / 不拼 InputParameters XML。
3. 不构造 `FixedRateBond`、`DiscountingBondEngine`、`Swaption`、`CreditDefaultSwap`、`MidPointCdsEngine`、`BlackSwaptionEngine`。
4. 零冲击 PV 必须等于平台 `market_value_base`（报表货币）。
5. 不新建持仓/行情主数据表。新字段进现有 `fsi.*` 或 snapshot `metadata` / `data_quality`。
6. MMF 与股票债券同级；WAM/WAL 走 look-through。SFC 状态只改 `limits/sfc.py`。
7. 限额/优化/Governance 输出 `is_trade_instruction=False`，除非产品明确做成交。
8. 业务层（`4_business`）只调 `RiskEngine.bind` / 已有 service，不复制定价或 VaR。

回归：

```bash
python -m pytest 3_riskengine/tests 2_processing/test/test_professional_risk_engine.py 2_processing/test/test_portfolio_cockpit.py -q
```

---

## 1. 加一类金融产品

业务先定：产品名称、平台表/字段、`asset_class`、要哪些冲击、零冲击是否等于账面。

开发按序改：

| 步 | 文件 | 做什么 |
|---|---|---|
| 1 | `core/contracts.py` | 若没有枚举，加 `ProductKind` |
| 2 | `instruments/classify.py` | `_KIND_BY_ASSET` 别名；必要时 `factor_family` |
| 3 | `products/<family>.py` | 新 dataclass：实现 `value` / `sensitivity` / `cashflows`。**禁止** import 厂商 |
| 4 | `products/assemble.py` | `product_from_holding` 分支；OTC 条款走 `_otc_fields` / metadata |
| 5 | `core/resolve.py` | `_PRODUCT_PRICE`：默认 adapter + fallback |
| 6 | `adapters/ore/trade.py` | `_TRADE_TYPE` 描述符（业务仍不拼 XML） |
| 7 | `adapters/ore/pricing.py` 或 financepy | 仅当需要冲击增量；零冲击仍返回账面 |
| 8 | `liquidity/buckets.py` | `LISTED` / `OTC_STICKY` 或按剩余天数入桶 |
| 9 | `tests/fixtures.py` + `tests/test_phase_d_ore_products.py` 同类 | 组装、零冲击恒等、至少一种冲击、`ore_app is False` |
| 10 | [`products-and-business.md`](products-and-business.md) | 补一行产品表 |

**最小产品骨架：**

```python
@dataclass
class MyProduct(Product):
    def __post_init__(self) -> None:
        self.kind = ProductKind.MYKIND
        super().__post_init__()

    def sensitivity(self, market, shocks=()):
        base = self.value(market)
        # 只解释对本产品有意义的 Shock；其余忽略
        return {"base_pv": base, "shocked_pv": shocked, "pnl": shocked - base}
```

曲线从 `market.curves["reprice_from_ytm"]` 或 `market.curves["ore_reprice"]` 取 callable，不要在产品里 `import ORE`。

**REPO / STRUCTURED：** 枚举与路由已在，缺的是产品类与定价实现。优先按上表补齐，而不是新开平行引擎。

---

## 2. 加一项指标（KPI / 限额度量）

| 步 | 文件 | 做什么 |
|---|---|---|
| 1 | 与业务确认公式、单位（金额 / NAV 比 / 天数 / bp）、数据是否已在 snapshot | 缺数先加 loader 字段，不造表 |
| 2 | `risk/kpis.py` | `KPI_IDS` + `kpi_*`；用 `_report(...)` 统一外壳 |
| 3 | `risk/kpis.py` `compute_kpi_pack` | 纳入打包 |
| 4 | 若要进限额 | `limits/policy.py` 的 `LIMIT_IDS` / `DEFAULT_SPECS`；`limits/metrics.py` `collect_metrics` |
| 5 | 若只属于某业务页 | `4_business/investment_risk/domains.py` 的 `MODULE_KPIS` |
| 6 | 测试 | 样本 snapshot 上断言方向或恒等；默认政策下混合样本须仍 GREEN |
| 7 | 文档 | 更新产品与业务文 §3 |

SFC 类指标（WAM/WAL/偏离）**只**改 `limits/sfc.py` 与 `liquidity/mmf.py`。驾驶舱 `_compliance_status` 必须继续委托 `sfc.compliance_status`。

流动性 KPI（现金+短久期）与 `liquidity.report` 分桶是两套口径：改 KPI 会动历史 10% 样本断言；分桶/赎回可独立变精细。

---

## 3. 加一条风险流程

现有十项在 `risk/testing.py` + `RiskAPI` 方法。新增分析：

1. `core/contracts.py` 增加 `AnalyticKind`（若需要路由）。
2. `core/resolve.py` 放入 `_PORTFOLIO_ANALYTICS` 或 `_ANALYTIC_OVERRIDE`。
3. 在 `risk/testing.py` 实现，用 `stamp(bound, "MY_ANALYTIC", payload, model=...)`。
4. `risk/api.py` 增加同名小写方法（`calculate("my_analytic")` 靠 `hasattr`）。
5. 若属于压力/情景，同时接到 `stress/api.py` 或 `scenario/api.py`。
6. `4_business.risk_testing.service.run` 增加分支（Python 路径）。**不要**默默改 `execute_risk_test` 的 kernel 数字。
7. 测试：`analytic` 字段、关键恒等、`ore_app is False`（若相关）。
8. 文档：产品与业务文 §4。

**再估值类流程**（敏感度、压力、反向压力、KRD）必须走 `bound.valuation().revalue`，以便所有产品自动参与。不要在流程里按券种手写第二套 PV。

**统计类流程**（VaR、尾部、回测）走 NAV 或 Riskfolio 收益面板，缺库回退 NumPy。

**对手方流程** 走 `adapters/ore` 映射 + 现有 XVA 积分；不要引入 OREApp 立方「半接入」。

---

## 4. 加一张报表

报表 = 已有分析的稳定 JSON 包，而不是新引擎。

| 报表类型 | 组装位置 | 注意 |
|---|---|---|
| 单分析 | 直接返回 `testing.*` / `liquidity.report` | 保持 `analytic` `engine_version` |
| 投资风险页 | `kpis.compute_kpi_pack` + `domains.analyze_domain` | 域字典不要拆公式 |
| 过闸提案 | `4_business/portfolio_optimization/pipeline.py` | 估值+风险+压力+limits |
| 驾驶舱 | processing SQL 供展示数字；状态用 sfc | 禁止第二套 WAM 规则 |
| 新监管包 | 先 `governance.review` 扩展字段，或新 `bound.*.report()` | `is_trade_instruction=False` |

血缘必填键：`core/contracts.py` 的 `RESULT_LINEAGE_KEYS`。缺键时用 `stamp` 或 `lineage_context`。

前端新页：只消费 `4_business` / `/api/v1/fsi/...` 已有 JSON，不要从浏览器调 adapter。

---

## 5. 加情景 / 限额政策

**情景：** 在 `scenario/catalog.py` 增加 `Scenario(...)`。HTTP 目录会经 `2_processing.tools.risk_testing.scenarios` 再导出（保持同一对象）。冲击要写清 `factor_type` `mode` `label`。

**限额：** `limits/policy.py` 增加 spec（`MAX`/`MIN`、warning、hard、unit、是否 grouped）。分组限额的 metric 必须是 `{name: ratio}` 字典。默认阈值保持宽松，避免样本混合组合无故 BREACH；用测试注入 `policy={...}` 覆盖。

**Pre-Trade：** `4_business.risk_governance.pre_trade` 已跑估值 + sensitivity + stress + limits。新闸门加在治理层，不要在产品 `value()` 里做合规。

---

## 6. 按资产类生长的优先序（业务可勾选）

当前骨架已通。深化时建议：

1. **MMF / 存款 / CD / 短债** — WAM/WAL 加权规则、评级、发行人集中度、更细流动性桶、影子价字段进 snapshot。
2. **债券** — 曲线形状（非平行）、OAS/CS01 用信用冲击再估值、现金流日程。仍用 FinancePy 曲线包装，不启用 QL `FixedRateBond`。
3. **FX / 期权 / 期货** — vol surface、美式/障碍走现有 ORE 路径扩展参数，不要 XML。
4. **IRS / Swaption / CDS** — 期限、定盘、回收率从 metadata 补全；XVA 分摊改为按净额集（描述符已有字段）。
5. **Repo / Structured** — 先 DTO + 路由 + 账面 PV，再谈特殊定价。
6. **组合层** — 真实单券收益面板替代 NAV×beta；优化约束与 SFC 限额对齐。

每一步都要：零冲击恒等、至少一条冲击测试、文档表更新。

---

## 7. 业务怎么提需求（给非开发）

写清楚这四件事即可，开发按本文第 1–4 节落地：

1. **产品**：叫什么、哪张表、是否 MMF 穿透、报表货币。
2. **指标**：公式、单位、预警/硬限、是否进驾驶舱。
3. **流程**：时点还是区间、输入冲击还是历史窗口、输出给谁签字。
4. **报表**：字段列表、是否交易指令、是否允许与 HTTP kernel 数字不同（Python 路径可以不同）。

不要指定「用 FinancePy 还是 ORE」——那是 `resolve()` 的事。

---

## 8. 验收清单（每项变更）

- [ ] 产品或分析能从 `RiskEngine().bind(sample_snapshot)` 调到
- [ ] 业务模块无新的厂商 import（`test_imports` / phase A 护栏）
- [ ] 零冲击 PV = 账面（若该产品参与估值）
- [ ] `ore_app is False`（若碰 ORE）
- [ ] PnL 五路或限额默认政策未被破坏
- [ ] `3_riskengine/docs/products-and-business.md` 已改最新态
- [ ] 未改 `core/kernel.py`，或明确只修 HTTP 且有 PRE 测试
