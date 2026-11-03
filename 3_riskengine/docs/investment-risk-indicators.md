<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 整体风险敞口 / 基本信息业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/indicators#risk-exposure`  
引擎入口：`RiskEngine().bind(snapshot).portfolio().basic_info()`  
实现：`3_riskengine/portfolio/basic_info.py`  
业务域：`4_business.investment_risk.exposure`

本文说明的是**资管业务能力**，不是工具栏 / Tab 壳 / CSV / Ask AI。

本包覆盖该页「基本信息」业务区：**组合、币种、成立日、WAM/WAL、投资管理人员**。  
同页「风险指标」Tab（核心五卡 / VaR / 六大风控类型）见 [`investment-risk-risk-metrics.md`](investment-risk-risk-metrics.md)。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **组合** | 代码、名称、产品线、基金大类、是否货基 | `modules.portfolio` | 基金卡：名称 + 类型标签 |
| **币种** | 报表基准币种、最近估值数据日 | `modules.currency` | 基准币种卡 |
| **成立日** | 成立 / 关闭 / 运作状态 / 存续天数 | `modules.inception` | 成立日卡 + 运作中/已关闭 |
| **WAM / WAL** | 货基加权平均期限与剩余期限（实际+限额+SFC） | `modules.wam_wal` | 货基：WAM/WAL 限额卡；引擎另给实际值 |
| **投资管理人员** | 经理 / 副经理 / 风控 / 合规等任职 | `modules.managers` | 投资管理人员表 |

```python
from 3_riskengine import RiskEngine

bound = RiskEngine().bind(snapshot)
pack = bound.portfolio().basic_info(
    meta={
        "port_name": "博晖港币货币基金",
        "port_type": "MMF",
        "inception_date": "2020-03-15",
        "mmf_wam_limit_days": 60,
        "mmf_wal_limit_days": 120,
        "managers": [
            {
                "person_id": "P001",
                "person_name": "张经理",
                "role": "FUND_MANAGER",
                "is_lead": True,
                "begin_date": "2020-03-15",
                "end_date": None,
            }
        ],
    },
)
assert pack["business_modules"] == [
    "portfolio", "currency", "inception", "wam_wal", "managers",
]
```

---

## 2. 模块口径

### 2.1 组合 `portfolio`

| 字段 | 口径 | 权威 |
|---|---|---|
| `port_id` / `fund_id` | 组合代码 | `fsi.para_portfolio.port_id` |
| `port_name` | 组合名称 | 同上 |
| `port_type` | 产品线（MMF/BOND/EQUITY…） | `port_type` |
| `fund_category` | 粗粒度大类：MONEY_MARKET / BOND / EQUITY / MIXED / OTHER | `is_mmf` 优先，否则 `port_type` 映射 |
| `is_mmf` | 是否货基账本 | 参数或持仓穿透判定 |
| `is_active` | 是否运作中 | `para_portfolio.is_active` |

`fund_category` 用于页面标注「哪些风险模块建议适用」——不隐藏模块，仅提示。

### 2.2 币种 `currency`

| 字段 | 口径 |
|---|---|
| `base_currency` | 报表基准币种（港币基金多为 HKD） |
| `data_date` | 最近可用估值日（≤ as_of 的 NAV 日） |
| `as_of_date` | 查询截止日 |

资管口径：基准币种决定市值折算与敞口汇总货币；与持仓原币种（`position.currency`）不同。

### 2.3 成立日 `inception`

| 字段 | 口径 |
|---|---|
| `inception_date` | 产品成立日 |
| `close_date` | 清盘 / 关闭日（可空） |
| `status` | `ACTIVE` / `CLOSED` |
| `tenure_days` | as_of − 成立日（日历天） |

成立日是业绩「成立以来」区间的起点权威；关闭后仍可查历史，但 `is_active=false`。

### 2.4 WAM / WAL `wam_wal`

货基（MMF）监管核心期限指标：

| 字段 | 口径 |
|---|---|
| `wam_days` | 加权平均期限（至利率重置 / 剩余期限） |
| `wal_days` | 加权平均剩余期限（至最终到期） |
| `mmf_wam_limit_days` | 限额（默认 SFC 60 天） |
| `mmf_wal_limit_days` | 限额（默认 SFC 120 天） |
| `wam_utilization` / `wal_utilization` | 实际 / 限额 |
| `status` | `ok` / `warn` / `breach`（与驾驶舱 SFC 同函数） |

$$
\mathrm{WAM}=\sum_i w_i\cdot d_i^{\mathrm{reset}},\quad
\mathrm{WAL}=\sum_i w_i\cdot d_i^{\mathrm{final}}
$$

权重 \(w_i\) 为 LOOK_THROUGH 市值占比。实现复用 `3_riskengine.liquidity.mmf.sfc_metrics`。  
非货基：`is_mmf=false`，实际值为空，页面改展示基金类型卡。

页面基本信息卡当前主要展示**限额**；引擎包额外给出**实际 WAM/WAL**，供对账、Agent 与货基合规。

### 2.5 投资管理人员 `managers`

| 字段 | 口径 |
|---|---|
| `person_id` / `person_name` | 人员主数据 |
| `role` | FUND_MANAGER / DEPUTY_MANAGER / RISK_OFFICER / COMPLIANCE_OFFICER / … |
| `is_lead` | 是否首席 |
| `begin_date` / `end_date` | 任职区间；`end_date` 空 = 在职 |
| `is_current` | 是否当前任职 |
| `sfc_licence_no` | SFC 牌照号（可空） |

**业务投管人员 ≠ 平台登录账号。**  
权威：`fsi.para_portfolio_manager` × `fsi.para_person`；引擎经 `meta.managers` 注入，与 HTTP `GET .../basic-info/{fund_id}` 对账。

---

## 3. 数据流

```
fsi.para_portfolio              → 组合 / 币种 / 成立日 / 货基限额
fsi.para_portfolio_manager
  × fsi.para_person             → 投资管理人员
fsi.balance_portfolio_nav       → data_date（最近估值日）
fsi.balance_*（穿透）           → WAM / WAL 实际值
        ↓
RiskEngine.bind(snapshot).portfolio().basic_info(meta=…)
        ↓
五大业务模块（可与 HTTP basic-info 字段对账）
```

HTTP：`GET /api/v1/fsi/investment/basic-info/{fund_id}`（processing `compute_portfolio_basic_info`）。  
引擎包用于：单测、Agent、域分析 `4_business.investment_risk.exposure.analyze`、与 SQL 结果对账。

---

## 4. 验证

```bash
python 3_riskengine/scripts/run_tests.py tests/test_investment_risk_indicators.py -q
```

断言：

- `verify_business_modules` 通过
- 货基夹具算出 WAM/WAL，且 WAL ≥ WAM；限额 60 / 120
- 投管名单含在职首席；HTTP 同形 `portfolio` / `managers` 字段齐全
- 非货基 `wam_wal.is_mmf=false` 且实际值为空
- 域 `exposure.analyze` 含 `basic_info` 包

夹具：`sample_mmf_snapshot` + `sample_basic_info_meta`。

---

## 5. 边界

- 不另建人事主数据；人员名单由平台表经 meta / HTTP 注入。
- 厂商库仅 `adapters/`；本业务不直接 import FinancePy/ORE/Riskfolio。
- WAM/WAL 是监管期限指标，不是久期（Duration）或修正久期。
- `fund_category` 只做适用性提示，不替代产品线 `port_type`。
