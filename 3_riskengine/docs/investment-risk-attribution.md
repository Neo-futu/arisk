<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 业绩归因 Tab 业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/indicators` → **业绩归因** Tab  
引擎入口：`RiskEngine().bind(snapshot).pnl().attribution()`  
实现：`3_riskengine/pnl/attribution/`（**相对独立的模型包**）  
业务域：`4_business.investment_risk.pnl_attribution`

本文说明的是**资管业绩归因业务能力**，不是工具栏 / 导出 / SQL 按钮。

模型在请求内实时计算，**不读取报表层缓存**；与 processing `models/brinson|campisi|contribution` 同口径，但引擎侧自包含，不 import `2_processing`。

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **Brinson 摘要** | 组合/基准/超额，配置·选券·交互 | `modules.summary` | 顶部六卡 |
| **各类资产收益贡献** | 资产类净损益与贡献% | `modules.asset_contribution` | 资产贡献表 |
| **个股损益前/后十大** | 按净损益排序 | `modules.security_pnl` | 前十大 / 后十大 |
| **个券收益贡献** | \(C_i=W_i\times R_i\)，Carino 链接 | `modules.contribution_model` | 个券贡献计算器 |
| **Brinson 模型** | BHB / BF，单期或多期 GRAP | `modules.brinson_model` | Brinson 面板 |
| **Campisi 模型** | 债券收入/国债/利差/择券 | `modules.campisi_model` | Campisi 面板 |
| **个股 Beta 贡献** | 前十大权重 × Beta | `modules.equity_beta` | Beta 贡献卡 |

```python
from 3_riskengine import RiskEngine

pack = RiskEngine().bind(snapshot).pnl().attribution(
    meta={"benchmark_id": "HSI", "portfolio_rows": [...], "benchmark_rows": [...]},
    brinson_method="BHB",
    brinson_multi=True,
    brinson_group="asset",
)
assert pack["business_modules"] == [
    "summary", "asset_contribution", "security_pnl",
    "contribution_model", "brinson_model", "campisi_model", "equity_beta",
]
```

---

## 2. Brinson 摘要与模型

### 2.1 摘要六卡

| 字段 | 口径 |
|---|---|
| `fund_return_pct` | 组合区间收益 ×100 |
| `benchmark_return_pct` | 基准收益（如 HSI）×100 |
| `active_return_pct` | 超额 = 组合 − 基准（GRAP 下为财富差） |
| `allocation_effect_pct` | 配置效应 |
| `selection_effect_pct` | 选券效应 |
| `interaction_effect_pct` | 交互效应 |

### 2.2 BHB / BF

**BHB（Brinson–Hood–Beebower）**

\[
A=(w_p-w_b)\,r_b,\quad
S=w_b\,(r_p-r_b),\quad
I=(w_p-w_b)\,(r_p-r_b)
\]

**BF（Brinson–Fachler）**

\[
A=(w_p-w_b)\,(r_b-R_b),\quad
S=w_p\,(r_p-r_b),\quad
I=0\ \text{（并入选择）}
\]

多期 **GRAP**：

\[
\text{效应}_t^{\mathrm{link}}
=\text{效应}_t\cdot
\prod_{i<t}(1+R_{p,i})\cdot
\prod_{i>t}(1+R_{b,i})
\]

链接后配置+选券+交互 = 期末财富差 \(\Pi(1+R_p)-\Pi(1+R_b)\)。

分组：`asset` / `industry` / `symbol` / `portfolio`。  
无指数成分时，基准用**组合资产类别等权对照**。

实现：`3_riskengine/pnl/attribution/brinson.py`。

---

## 3. 各类资产贡献与个股损益

| 模块 | 口径 |
|---|---|
| `asset_contribution` | 按资产类汇总 `net_pnl`；`contribution_pct = net_pnl / 期初净值 × 100` |
| `top_winners` / `top_losers` | 个券净损益降序 / 升序 Top N |

权威可为 `fsi.transact_pnl_item`（经 meta 注入）；引擎也可用持仓 `unrealized_pnl` / 代理收益派生。

---

## 4. 个券收益贡献

\[
C_i = W_i \times R_i
\]

| 模式 | 口径 |
|---|---|
| `single` | 期初权重 × 区间收益 |
| `average` | 平均权重 × 累计收益 |
| `daily` + Carino | \(C_{i,t}=W_{i,t-1} R_{i,t}\)，再 \(\kappa\) 链接到几何组合收益 |

Carino：

\[
\kappa_t=\frac{\ln(1+R_{p,t})}{R_{p,t}},\quad
C_i=\frac{1}{\kappa}\sum_t \kappa_t C_{i,t}
\]

保证 \(\sum C_i = R_p = \Pi(1+R_{p,t})-1\)；差额为现金/费用残差。

实现：`contribution.py`。

---

## 5. Campisi 债券归因

无基准：国债 \(=-\,D\cdot\Delta y_{\mathrm{treas}}\)；利差 = 总收益 − 收入 − 国债；择券 = 0。  
有基准：利差 \(=-\,D\cdot\Delta s\)；择券 = 总 − 收入 − 国债 − 利差。  
多期按后续总收益复利链接。

分组：`industry` / `symbol` / `asset` / `portfolio`。  
实现：`campisi.py`。

---

## 6. 个股 Beta 贡献

| 字段 | 口径 |
|---|---|
| `value` | 组合 Beta（NAV 对基准回归） |
| `benchmark_id` | 如 HSI |
| `constituents[]` | 前十大权重：代码 / 名称 / 占比 / Beta / 样本数 |

---

## 7. 数据流

```
持仓权重 + 区间收益帧（meta.portfolio_rows）
基准权重 + 收益帧（meta.benchmark_rows 或等权资产类）
NAV / 基准指数序列
损益明细（可选 meta.pnl_rows / asset_contribution）
        ↓
独立模型：brinson / campisi / contribution
        ↓
pnl().attribution() → 七大业务模块
```

HTTP：

- `GET .../performance-attribution/{fund_id}` — 摘要 / 资产贡献 / 前十损益
- `GET .../attribution-models/{fund_id}` — Brinson / Campisi / 贡献视图字典

---

## 8. 验证

```bash
python 3_riskengine/scripts/run_tests.py tests/test_investment_risk_attribution.py -q
```

断言：七模块齐全；BHB 单期算术恒等式；Carino 贡献和 = 几何收益；Campisi 有基准择券残差；域 `pnl_attribution.analyze` 含 attribution 包。

---

## 9. 边界

- 模型包相对独立：只依赖本目录纯函数 + snapshot/meta，不读报表层、不 import processing。
- 厂商库仅 `adapters/`；归因不调用 FinancePy/ORE/Riskfolio。
- 无完整持仓时序时，引擎用当前权重 + 代理收益做单期演示；生产应对齐日频权重与收益帧。
- 归因效应是相对基准的业绩分解，不是会计损益表。
