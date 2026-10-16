<!-- 更新时间：2026-10-16（北京时间）｜生成模型：Cursor Composer -->

# 产品压力测试（Bloomberg LQAP）

> 投资风险 UI「产品压力测试」面板的权威说明：架构、功能、数据流与配置。
> 纯计算在 `3_riskengine.liquidity`；取数与落库在 `2_processing`；画面在 `frontend` LQAP 组件。

---

## 1. 定位

**产品压力测试**对齐彭博 **LQAP（Liquidity Assessment / Portfolio Liquidity）** 组合层画面：在给定赎回比例、目标变现成本倍数与历史/压力情景下，给出：

- 组合变现期限分布（Horizon Analysis）
- 个券压力明细（Stress Details）
- 组合概览与赎回情景成本
- LQA 风格字段覆盖情况

与 **SFC 货币基金流动性压测**（`sfc_liquidity_stress` / DLA·WLA）并列、口径不同：SFC 走监管参与率×ADTV；本产品对**债券**按彭博 FI 假设用 **Bid-Ask 阶梯**估天数，**股票类**才用参与率×ADTV。

---

## 2. 架构

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend  LqapPortfolioLiquidity.tsx                       │
│  路由：investment-risk/indicators → 产品压力测试面板          │
└───────────────────────────┬─────────────────────────────────┘
                            │ GET /api/v1/fsi/investment/lqa-portfolio/{fund_id}
┌───────────────────────────▼─────────────────────────────────┐
│  Backend（unified）FSI 代理 → /processing/...                │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  2_processing.api.routers.investment.get_lqa_portfolio      │
│  2_processing.tools.performance.lqa_portfolio_analytics     │
│    · 读持仓 / ADTV / 价差 / 阶梯表                           │
│    · 调 RiskEngine 纯函数                                    │
│    · 可选落库 fsi.mktdata_lqa (data_source=COMPUTED)         │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  3_riskengine.liquidity                                     │
│    lqa_fields.enrich_book   → 券级 LQA 字段 + 变现天数        │
│    lqap.analyze             → 情景拉伸、分桶、成本、报表契约  │
│    LiquidityAPI.lqap        → bind 后 stamp 封装（可选入口）  │
└─────────────────────────────────────────────────────────────┘
```

| 层 | 路径 | 职责 |
|---|---|---|
| UI | `frontend/src/modules/investment-risk/LqapPortfolioLiquidity.tsx` | 参数草稿/应用、Horizon / Stress Details、重新计算 |
| HTTP | `backend` FSI → `2_processing/api/routers/investment.py` | 鉴权代理与查询参数 |
| Orchestration | `2_processing/tools/performance/lqa_portfolio_analytics.py` | DB I/O + 调用引擎 + 持久化 |
| Engine | `3_riskengine/liquidity/{lqa_fields,lqap,api}.py` | **无 DB**：字段推导与组合聚合 |
| Schema | `1_datastorage/postgres/schema/024*.sql`、`025_lqa_fi_horizon_ladder.sql` | LQA 快照表、刷新函数、FI 天数阶梯 |

原则：引擎不直连库；业务禁止在前端复算天数/成本。

---

## 3. 功能

### 3.1 用户可调参数

| 参数 | 含义 | 默认 | 作用 |
|---|---|---|---|
| Scenario | 情景定义（CUSTOM / SEVERE / UKRAINE22 …） | `SEVERE` | 拉伸天数、成本、股票类 volume_scale |
| Redemption Size (%) | 赎回占组合市值比例 | 100 | 名义赎回额与个券/组合 Cost |
| Target Cost × | Bid-Ask 成本倍数 | 0.5 | `Cost = MV × spread × 倍数 × 情景成本因子 × 赎回比` |
| Incl Curr Day | 是否把当日计入结算 | true | `false` 时天数整体 +1 |

改参后需点 **「重新压力测试计算」**（草稿 → 应用后再请求）。

### 3.2 画面区块

| 区块 | 内容 |
|---|---|
| Portfolio Overview | 市值、持仓数、组合 Bid-Ask (bps)、波动、Pct of EDV、Liq. Horizon、Global Score |
| Redemption Scenario | Nominal / Cost / Value / Residual Mkt Val |
| Horizon Analysis | 期限桶柱状图（% MV / # Positions）+ 汇总表 |
| Stress Details | 个券表（含单位表头）+ CSV 导出 |
| 字段覆盖 | LQA_* 字段有值只数与来源说明 |

### 3.3 债股分流（变现天数）

| 资产 | Horizon 模型 | 成本 |
|---|---|---|
| 现金 / 隔夜存款 | 合约：0 天 | 通常 0 |
| 定期存款 / 回购 | 剩余期限（天） | 通常 0 |
| 债券 / CD（`BOND_*` / `CD`） | **方案 A**：Bid-Ask(bp) → 阶梯天数（不用 ADTV×参与率） | 资产类 Bid-Ask × Target Cost |
| 股票类（`EQUITY` / `ETF` …） | `MV / (EDV × 10% × volume_scale)` | 如有价差则同价差路径 |

彭博完整 FI 模型还需 Market Depth + 冲击曲线；当前为可配置阶梯近似，待深度数据接入后可替换为容量反推。

### 3.4 期限桶（Horizon buckets）

| id | 标签 |
|---|---|
| `le1` | ≤ 1 day |
| `d1_3` … `d15_25` | 分段天数 |
| `gt25` | > 25 days |
| `not_covered` | 无有效天数（如债券无报价） |

---

## 4. 数据流

```
估值日 as_of / 组合 fund_id
        │
        ▼
┌───────────────────┐     ┌────────────────────────────┐
│ balance_* 持仓     │     │ mktdata_adtv（股票类 EDV）   │
│ (bond/cd/deposit/ │     │ sfc_liquidity_bucket_def   │
│  cash/repo)       │     │   .bid_ask_cost_bps(NORMAL)│
└─────────┬─────────┘     │ lqa_fi_horizon_ladder      │
          │               │   （方案 A 阶梯）            │
          └───────┬───────┴────────────┬───────────────┘
                  ▼                    │
         enrich_book(positions,        │
           adtv, bid_ask, ladder)  ◄───┘
                  │
                  │ 券级：liq_horizon_days, bid_ask_spread,
                  │       expected_daily_volume, sector_score, …
                  ▼
         （可选）UPSERT fsi.mktdata_lqa
                  data_source = COMPUTED
                  │
                  ▼
         lqap.analyze(scenario, redemption, cost_multiple, …)
                  │
                  ▼
         JSON：overview / redemption / horizons / securities / lqa_fields
                  │
                  ▼
         UI 渲染 / CSV
```

离线全量重算：`SELECT fsi.refresh_mktdata_lqa();`（`024b`，读同一阶梯表）。日常以 API 现场计算为准。

### 4.1 成本与天数公式（当前落地）

**债券 / CD 天数（方案 A）**

1. 取 `bid_ask_cost_bps`（资产类 NORMAL；无报价 → Not Covered）
2. 在 `lqa_fi_horizon_ladder` 按 `band_seq` 找首个 `bps ≤ max_bid_ask_bps`（末行 `NULL` = 开放上沿）
3. 得 `horizon_days`，再 × 情景 `day_factor`（+ optional settlement shift）

**股票类天数**

\[
\text{Horizon} = \frac{\text{MV}}{\text{EDV} \times 0.10 \times \text{volume\_scale}} \times \text{day\_factor} + \text{shift}
\]

**变现成本（各类有价差者）**

\[
\text{Cost} = \text{MV} \times \text{spread} \times \text{cost\_multiple} \times \text{cost\_factor} \times \text{redemption\_ratio}
\]

其中 `spread = bid_ask_bps / 10000`（价格分数）。

---

## 5. 配置

### 5.1 方案 A：Bid-Ask → Horizon 阶梯（可改）

**表**：`fsi.lqa_fi_horizon_ladder`  
**脚本**：`1_datastorage/postgres/schema/025_lqa_fi_horizon_ladder.sql`  
**加载**：`lqa_portfolio_analytics._load_fi_horizon_ladder`；表缺失时回退代码常量 `DEFAULT_FI_HORIZON_LADDER`。

| ladder_id | band_seq | max_bid_ask_bps | horizon_days | 业务含义 |
|---|---|---|---|---|
| DEFAULT | 1 | 10 | 1 | ≤10 bp → 1 天 |
| DEFAULT | 2 | 50 | 3 | 10–50 bp → 3 天 |
| DEFAULT | 3 | 150 | 10 | 50–150 bp → 10 天 |
| DEFAULT | 4 | NULL | 40 | >150 bp → 40 天（>30） |

无报价不入阶梯，引擎记 **Not Covered**。

```sql
-- 调整 ≤10bp 档天数
UPDATE fsi.lqa_fi_horizon_ladder
SET horizon_days = 2, updated_at = NOW()
WHERE ladder_id = 'DEFAULT' AND band_seq = 1;

-- 查看当前档
SELECT band_seq, max_bid_ask_bps, horizon_days, label
FROM fsi.lqa_fi_horizon_ladder
WHERE ladder_id = 'DEFAULT' AND is_active
ORDER BY band_seq;
```

可另建 `ladder_id`（如 `STRESS_STRICT`）并存；API 当前固定读 `DEFAULT`。

### 5.2 资产类 Bid-Ask（bp）

**表**：`fsi.sfc_liquidity_bucket_def`（`scenario = 'NORMAL'` 的 `bid_ask_cost_bps`）  
**种子**：`022a_sfc_stress_seed.sql`（例：国债 1bp、信用债 3bp、CD 2bp）

阶梯消费的是本表价差；改种子/UPDATE 后重新压测即反映到天数档与 Cost。

### 5.3 情景因子（代码表）

**权威**：`3_riskengine/liquidity/lqap.py` → `SCENARIOS`  
每项：`(code, label, day_factor, cost_factor, volume_scale)`。

| 因子 | 作用于 |
|---|---|
| `day_factor` | 变现天数拉伸 |
| `cost_factor` | Bid-Ask 成本拉伸 |
| `volume_scale` | **仅**股票类参与率路径的日容量缩放 |

### 5.4 相关库表一览

| 对象 | 角色 |
|---|---|
| `fsi.balance_*` | 持仓权威 |
| `fsi.mktdata_adtv` | 股票类 ADTV / EDV |
| `fsi.sfc_liquidity_bucket_def` | 资产类参与率、价差 bp（本产品主要用 NORMAL 价差） |
| `fsi.lqa_fi_horizon_ladder` | FI 天数阶梯配置 |
| `fsi.mktdata_lqa` | 券级 LQA 计算结果快照（COMPUTED） |
| `fsi.sfc_liquidity_stress` | SFC 监管压测结果（**不**作为本产品主路径输入） |

---

## 6. API 与入口

| 入口 | 说明 |
|---|---|
| `GET /api/v1/fsi/investment/lqa-portfolio/{fund_id}` | 前端正式入口（经 FSI 代理） |
| Query | `as_of_date`, `scenario`, `redemption_pct`, `cost_multiple`, `include_current_day` |
| Python | `compute_lqa_portfolio_analytics(...)` |
| RiskEngine | `RiskEngine().bind(snapshot).liquidity().lqap(positions, ...)` |

单测：`3_riskengine/tests/test_lqa_fields.py`、`test_lqap.py`。

---

## 7. 边界与后续

- **不做**：前端自算 Horizon；债券套用 ADTV×10% 作为产品压力测试主口径；把 SFC DLA/WLA 结果直接当 LQAP。
- **过渡**：FI 阶梯为方案 A；接入券级 Market Depth / 冲击曲线后可演进为「Target Cost 约束下反推 \(Q_{daily}\)」。
- **热更新注意**：`backend-unified` 的 `--reload` 默认主要监视 `backend/`；改 `3_riskengine` / `2_processing` 后需重启 unified 进程才能在 API 生效。

---

## 8. 相关文档

- RiskEngine 总览：[`README.md`](README.md)、[`architecture-and-interfaces.md`](architecture-and-interfaces.md)
- 流动性其它能力（buckets / redemption / MMF SFC）：`3_riskengine/liquidity/`
- Schema：`1_datastorage/postgres/schema/024_mktdata_lqa.sql`、`024b_*.sql`、`025_lqa_fi_horizon_ladder.sql`
