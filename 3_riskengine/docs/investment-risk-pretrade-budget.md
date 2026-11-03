<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 风险预算与前置试算业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/pretrade-budget#risk-budget`  
引擎入口：`RiskEngine().bind(snapshot).risk().pretrade_budget(...)`  
实现：`3_riskengine/risk/pretrade/`（**相对独立的模型包**）  
业务域：`4_business.investment_risk.risk_budget`  
HTTP：`compute_pretrade_risk_budget` → 引擎包（processing 仅装载 snapshot / 限额 / 发行人统计）

本文说明的是**资管风控引擎业务能力**（风险预算贡献、VaR/DV01、前置限额闸门），不是工具栏 / 基金下拉 / 「计算」按钮。

模型在请求内实时计算；拟成交经引擎侧 `apply_proposed_trade` **克隆持仓、不写库**。不 import `2_processing` / `4_business`。

适配器：FinancePy · 1.1.2｜Riskfolio-Lib · 7.3.0｜ORE / QuantLib · 1.43

---

## 1. 业务模块总览

| 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|
| **交易参数** | 方向 / 名义 / 资产类 / 久期 / Issuer | `modules.trade_inputs` | 「交易参数与计算」 |
| **决策卡** | ALLOW·WARNING·BLOCK；剩余久期/VaR 预算；DV01 | `modules.decision_cards` | 顶部四卡 |
| **KPI 面板** | 决策·久期·VaR/CVaR·ΔVaR·敞口·Top RC·冲击 | `modules.kpi_panel` | KPI 表 |
| **风险预算贡献** | 按资产类别 RC 占比 | `modules.risk_budget` | 「风险预算贡献（按资产类别）」 |
| **试算后预算** | 拟成交后 RC 结构 | `modules.projected_budget` | 「试算后风险贡献」 |
| **RP 参考权重** | Riskfolio 风险平价（非交易指令） | `modules.rp_reference` | 「Riskfolio 风险平价参考权重」 |
| **决策摘要** | 放行建议 + 理由条 + 导出 | `modules.decision_summary` | 「前置试算决策摘要」 |
| **因子冲击对比** | 五类标准冲击：当前 vs 试算后 | `modules.factor_shock_compare` | 「标准因子冲击 PnL」 |
| **限额对比** | 久期 / Issuer / VaR / CVaR / DV01 / 冲击 | `modules.limit_comparison` | 「限额对比」 |
| **方法论** | 适配器分工 + 流水线 | `modules.methodology` | 页脚逻辑说明 |

```python
from importlib import import_module

RiskEngine = import_module("3_riskengine").RiskEngine

pack = RiskEngine().bind(snapshot).risk().pretrade_budget(
    trade_amount=10_000_000,
    trade_side="BUY",
    asset_class="BOND",
    duration_years=2.0,
    issuer_name="UNKNOWN_ISSUER",
    limits={  # 可选；缺省 duration=4 / issuer=10% / impact=5% / var=2%
        "duration_years": 4.0,
        "issuer_pct_nav": 10.0,
        "tracking_error_proxy_pct": 5.0,
        "var_pct_nav": 2.0,
    },
)
assert pack["business_modules"] == [
    "trade_inputs", "decision_cards", "kpi_panel", "risk_budget",
    "projected_budget", "rp_reference", "decision_summary",
    "factor_shock_compare", "limit_comparison", "methodology",
]
assert pack["decision"] in {"ALLOW", "ALLOW_WITH_WARNING", "BLOCK"}
```

`pack` 与 HTTP `PretradeRiskResult` **同形**（`current` / `projected` / `limits` / `risk_budget` / `decision_summary` / `engine_metrics` …），前端可直接消费。

---

## 2. 决策闸门

\[
\text{Decision} = \text{限额闸门} \times \text{风险预算剩余空间}
\]

硬限额对照（试算后）：

| 维度 | 默认限额 | 触发 |
|---|---|---|
| 组合修正久期 | 4.0 年 | `projected_duration > limit` |
| 单一发行人 %NAV | 10% | `projected_issuer_pct > limit` |
| 单笔名义冲击 %NAV | 5% | `|amount|/NAV > limit` |
| VaR %NAV | 2% | `projected_var > limit`；或 ΔVaR 绝对值 > 冲击限额 |

判定：

- 0 项超限 → **ALLOW**
- 1 项超限 → **ALLOW_WITH_WARNING**
- ≥2 项超限 → **BLOCK**

剩余预算：

- 剩余久期预算 = `duration_limit − projected_duration`
- 剩余 VaR 预算 = `var_limit − projected_var`
- 已用 % = 试算值 / 限额 × 100

---

## 3. Duration / DV01 / VaR

**久期（FinancePy / ORE 口径）**

\[
D = \frac{\sum_i MV_i \times D_i}{\sum_i MV_i}\quad(\text{固收子集})
\]

试算后：克隆持仓叠加拟成交名义与久期后重算；若 KPI 无效则回退市值加权近似。

**DV01**

\[
\mathrm{DV01} \approx PV(r+1\mathrm{bp}) - PV(r);\quad
\mathrm{proxy}=\sum_i MV_i \times D_i \times 0.0001
\]

**VaR / CVaR（Riskfolio 历史分位）**

\[
\mathrm{VaR}_\alpha = -Q_\alpha(R)\times\mathrm{NAV},\quad
\mathrm{CVaR}_\alpha = -E[R \mid R \le -\mathrm{VaR}]
\]

页面展示为 % NAV；ΔVaR = 试算后 − 当前。

---

## 4. 风险预算贡献与 RP 参考

**资产类别 RC**（因子冲击 |PnL| 归一；无冲击时回退市值权重）：

\[
\mathrm{RC}_c = \frac{\sum_{i\in c}|\mathrm{PnL}_i|}{\sum_j|\mathrm{PnL}_j|}
\]

标准冲击：`rate_1bp` / `equity_1pct` / `fx_1pct` / `cs_1bp` / `vol_10pct`（FinancePy / ORE 再估值）。

**Riskfolio 风险平价参考权重**：`portfolio().optimize("risk_parity")` → `rp_reference.rows`。  
**非交易指令**（`status=PROPOSAL`），仅作预算对照。

---

## 5. 前置试算流水线

1. `load_portfolio_snapshot` → `RiskEngine.bind`（FinancePy / ORE 估值曲线）  
2. 当前组合：Duration/DV01 + `portfolio().risk()`（VaR/CVaR、因子冲击、资产类别 RC）  
3. 风险预算：RC 占比；Riskfolio RP 参考权重  
4. `apply_proposed_trade` 克隆持仓（不写库）后重算同一套 KPI/风险包  
5. 对照 `para_risk_*` 前置限额与预算利用率 → ALLOW / ALLOW_WITH_WARNING / BLOCK  

公式总览：

\[
\text{RiskEngine 前置试算}
= \text{限额闸门} \times \text{风险预算贡献} \times \text{试算后 Duration/DV01/VaR}
\]

---

## 6. 适配器分工

| 适配器 | 职责 |
|---|---|
| FinancePy | Duration / DV01 / 标准利率·信用利差冲击再估值 |
| Riskfolio-Lib | VaR / CVaR 与风险平价（RP）参考权重 |
| ORE / QuantLib | 复杂债券与衍生品再估值 |

---

## 7. 边界

- 引擎包不读库；限额与发行人统计由 processing 注入（`limits` / `bond_stats` / `nav`）。  
- 拟成交独立实现于 `risk/pretrade/proposed.py`，不依赖 `4_business.trading.proposed`。  
- 风险平价权重是**提案**，不是下单指令。  
- 计算结果是风险估计与限额闸门，不是会计估值或监管资本批复。
