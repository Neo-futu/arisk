<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 组合驾驶舱业务模块 × RiskEngine

页面入口：`http://localhost:5173/portfolio-cockpit`  
引擎入口：`RiskEngine().bind(snapshot).portfolio().fundamentals()`  
实现：`3_riskengine/portfolio/cockpit.py`

本文说明的是**资管业务能力**（组合、规模、持仓资产类型、收益、净值），不是日期框 / 导出 / Ask AI 等页面控件。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **组合** | 组合身份、产品线、币种、估值日 | `modules.portfolio` | 表：名称 / 类型 / 币种 / 估值日 |
| **组合规模** | AUM、账面 PV、Gross/Net、杠杆 | `modules.scale` | 表：规模 AUM；图：规模 |
| **持仓资产类型** | 穿透后 BOND/EQUITY/CASH… 市值与权重 | `modules.holdings_asset_mix` | 引擎图 `holdings_mix`；列表页「类型」是产品线 |
| **收益** | 日收益、区间收益、七日年化、波动/回撤/VaR | `modules.returns` | 表：当日/区间/7日；图：收益 |
| **净值** | 单位/累计净值、历史、指数化曲线 | `modules.nav` | 表：单位/累计净值；图：净值 |

```python
from 3_riskengine import RiskEngine

bound = RiskEngine().bind(snapshot)
pack = bound.portfolio().fundamentals(meta={"port_name": "博晖港币货基", "port_type": "MMF"})
assert pack["business_modules"] == [
    "portfolio", "scale", "holdings_asset_mix", "returns", "nav"
]
check = __import__("3_riskengine.portfolio.cockpit", fromlist=["verify_business_modules"])
assert check.verify_business_modules(pack)["passed"]
```

---

## 2. 模块口径（风控引擎）

### 2.1 组合 `portfolio`

| 字段 | 口径 | 权威 |
|---|---|---|
| `port_id` | 组合代码 | `fsi.para_portfolio.port_id` / snapshot.fund_id |
| `port_type` | 产品线（MMF/BOND/EQUITY…） | `para_portfolio.port_type` |
| `base_currency` | 报表货币 | snapshot.reporting_currency |
| `as_of_date` | 估值日 | snapshot.as_of_date |
| `is_mmf` | 是否货基账本 | MMF 产品组装 / 参数 |

### 2.2 组合规模 `scale`

| 字段 | 口径 |
|---|---|
| `aum` / `net_asset` | 组合净资产（NAV） |
| `base_pv` | LOOK_THROUGH 持仓再定价合计（零冲击=账面） |
| `gross_exposure` | Σ\|PV\| |
| `net_exposure` | Σ PV |
| `leverage` | Gross / AUM |
| `pv_vs_nav` | base_pv − AUM（对账差） |

实现：`portfolio.aggregate`（FinancePy/ORE 经 adapters，业务不直接 import 厂商）。

### 2.3 持仓资产类型 `holdings_asset_mix`

**这是持仓维度，不是产品线维度。**

| 字段 | 口径 |
|---|---|
| `classes[].asset_class` | ProductKind：BOND / EQUITY / CASH / CD / DEPOSIT / FX… |
| `market_value` | 该类型合计 PV（报表货币） |
| `weight` / `weight_pct` | 占组合 NAV 权重 |

视图固定 **LOOK_THROUGH**：货基先穿透到底层券再归类。  
列表页饼图「类型」目前是跨组合的 `port_type` 分布；单组合持仓结构以下钻/`fundamentals` 为准。

### 2.4 收益 `returns`

| 字段 | 口径 |
|---|---|
| `day_return` | 日收益率（小数） |
| `period_return` | 期末 unit_nav / 期初 unit_nav − 1 |
| `return_rate_7d` | 近 7 日复利年化（%）；优先货基账本，否则由 NAV 收益推算 |
| `volatility_ann` / `max_drawdown` / `var_cvar` | Fund Risk（Riskfolio/回退） |

### 2.5 净值 `nav`

| 字段 | 口径 |
|---|---|
| `unit_nav` / `acc_unit_nav` | 单位净值 / 累计净值 |
| `history` | 区间 NAV 点列 |
| `indexed` | 首日=100 的指数化净值（业绩比较常用） |
| `sparkline_aum` | AUM 折线点 |

权威表：`fsi.balance_portfolio_nav`。无表时可用 `snapshot.nav_returns` 合成轨迹做引擎自测。

---

## 3. 数据流

```
fsi.para_portfolio          → 组合身份 / 产品线
fsi.balance_portfolio_nav   → AUM、单位净值、日收益、历史
fsi.balance_* 持仓          → LOOK_THROUGH 资产类型与规模
fsi.balance_portfolio_mmf   → 七日年化、WAM/WAL（货基）
fsi.mktdata_*               → 估值再定价曲线 / 报价（规模 PV）
        ↓
RiskEngine.bind(snapshot)
        ↓
fundamentals() → 五大业务模块
```

多组合总览列表仍由 processing SQL 供数；**区间收益公式、净值指数化、SFC 状态**与引擎同一实现（`period_return` / `indexed_nav_series` / `limits.sfc`）。

---

## 4. 与页面图的对应

| 页面 Tab | 业务含义 | 引擎 |
|---|---|---|
| 规模 | 各组合 AUM | `scale.aum` / 多组合 `charts.aum` |
| 类型 | 跨组合产品线占比 | `charts.mix`（semantic=`port_type`） |
| （下钻）持仓结构 | 单组合持仓资产类型 | `holdings_asset_mix.chart` |
| 收益 | 区间/日收益 | `returns.*` |
| 净值 | 指数化净值曲线 | `nav.indexed` |

---

## 5. 验证

```bash
python 3_riskengine/scripts/run_tests.py tests/test_portfolio_cockpit_page.py -q
```

断言要点：

- 混合账本：`holdings_asset_mix` 含 BOND/EQUITY/CASH，权重和≈1
- 货基：穿透后为固收类；`sfc_status` ∈ {ok,warn,breach}
- `verify_business_modules(pack)["passed"] is True`
- 规模 AUM 与 snapshot.net_asset 一致

---

## 6. 边界

- RiskEngine **不**另建组合主数据；组合目录权威在 `fsi.para_portfolio`。
- 厂商库只在 `adapters/`；业务代码只调 `fundamentals` / `aggregate` / `fund_risk`。
- 计算结果是风险与业绩估计，不是会计估值或监管批复。
- 货基合规徽标页表可不展示，但 `sfc_status` 口径必须来自 `limits.sfc`。
