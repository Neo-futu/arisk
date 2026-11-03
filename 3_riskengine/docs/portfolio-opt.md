<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 组合配置与优化 × RiskEngine

页面入口：`http://localhost:5173/portfolio-opt`  
引擎入口：`RiskEngine().bind(snapshot).portfolio().portfolio_opt(meta=...)`  
实现：`3_riskengine/portfolio/optimization/`（**相对独立的模型包**）  
业务层：`4_business.portfolio_optimization`（闸门管道 / 仿真仓；HTTP analyze 仍可走 processing 取数）

本文说明的是**资管组合构建与优化业务能力**，不是工具栏 / CSV·PNG 导出按钮 / 行情弹窗。

模型在请求内实时计算，**不读取报表层缓存、不 import `2_processing`**。价格或收益面板经 `meta.prices` / `meta.returns` 注入；闸门优化经 Riskfolio 适配器。

> **红线**：优化结果是**提案（PROPOSAL）**，不是交易指令（`is_trade_instruction=False`）。

---

## 1. 业务模块总览

| # | 模块 | 业务含义 | 引擎键 | 页面呈现 |
|---|---|---|---|---|
| 01 | **参数区** | 资产池、收益模型、Rf、权重上下限、区间 | `modules.parameters` | 参数卡 |
| 01b | **优化闸门** | Riskfolio 方法提案 + 闸门状态 | `modules.governed_gate` | 运行闸门优化 |
| 02 | **用户组合** | 可调权重与实时绩效 | `modules.user_portfolio` | 滑条权重区 |
| 03 | **有效前沿** | 前沿 / 切点 / 资产点 / 画像落点 | `modules.efficient_frontier` | 前沿图 |
| 04 | **预期收益模型** | Hist·CAGR·CAPM·BL·区间实现 | `modules.return_models` | 收益模型表 |
| 05 | **个股风控绩效** | 收益·波动·夏普·回撤·VaR·CVaR | `modules.asset_metrics` | 个股指标表 |
| 06 | **组合画像对比** | conservative / balanced / aggressive / hrp | `modules.profile_comparison` | 画像指标表 |
| 07 | **图表数据** | 相关性热力图 + 配置对比 | `modules.charts` | 热力图 / 配置表 |
| 08 | **效率诊断** | alpha_loss / excess_vol | `modules.validation` | 诊断区 |

```python
from importlib import import_module

RiskEngine = import_module("3_riskengine").RiskEngine

pack = RiskEngine().bind(snapshot).portfolio().portfolio_opt(
    meta={
        "returns": returns_df,           # 或 prices=prices_df
        "return_model": "historical_mean",
        "risk_free_rate": 0.042,
        "weight_bounds": (0.0, 0.35),
        "custom_weights": {...},
        "bl_views": {"AAPL": 0.12},
        "governed_method": "hrp",
    },
)
assert pack["business_modules"] == [
    "parameters", "governed_gate", "user_portfolio", "efficient_frontier",
    "return_models", "asset_metrics", "profile_comparison", "charts", "validation",
]
assert pack["is_trade_instruction"] is False
```

顶层字段与 HTTP `OptimizeResult` **同形**（`universe` / `return_models` / `profiles` / `frontier` / `correlation` …）。

---

## 2. 预期收益率模型（4 种）

| 模型 | 口径 |
|---|---|
| **Historical Mean** | \(\mu= \bar r \times 252\)（算术） |
| **Real CAGR** | \((P_T/P_0)^{252/n}-1\) |
| **CAPM** | \(r_f+\beta_i(E[r_m]-r_f)\)，\(r_m\)=等权市场 |
| **Black-Litterman** | 市值隐含先验 \(\pi=\delta\Sigma w_{mkt}\) + 绝对观点凸组合 |
| 区间实现收益 | \(P_T/P_0-1\)（对照列） |

协方差用样本协方差年化：\(\Sigma=\mathrm{Cov}(r)\times 252\)。

---

## 3. 组合画像

| 画像 | 目标 |
|---|---|
| `conservative` | 最小方差 |
| `balanced` | 最大夏普（切点） |
| `aggressive` | 最大二次效用（风险厌恶=1） |
| `hrp` | 层次风险平价（相关距离聚类 + 递归二分） |

权重受 `weight_bounds` 约束（页面默认 0–0.35）。可选 `target_return` / `custom` / `benchmark` 画像。

**组合指标**

\[
\begin{aligned}
\mu_p&=w^\top\mu,\quad
\sigma_p&=\sqrt{w^\top\Sigma w},\quad
\mathrm{Sharpe}=(\mu_p-r_f)/\sigma_p \\
\mathrm{MDD}&=\min(W_t/\mathrm{peak}_t-1),\quad
\mathrm{VaR}_{95}=Q_{5\%}(r_p),\quad
\mathrm{CVaR}_{95}=E[r_p\mid r_p\le\mathrm{VaR}]
\end{aligned}
\]

---

## 4. 有效前沿与 CML

- 在 \([\min\mu,\max\mu]\) 上对目标收益求最小方差轨迹。  
- **切点组合** = 最大夏普点；CML 由 \((0,r_f)\) 连切点。  
- 用户权重点与画像点叠加在 \(\sigma\)–\(\mu\) 平面，左侧拖动实时联动（前端 evaluate / 本包 `user_portfolio.metrics`）。

---

## 5. 优化闸门（01b）

流程：Riskfolio 适配器优化 → 估值 / 投资风险 / 风险测试 / 限额闸门。

| 闸门键 | 引擎侧 |
|---|---|
| `optimization` / `riskengine` | 有权重提案即 PASS |
| `valuation` / `investment_risk` / `risk_testing` / `limits` | 完整管道由 `4_business.portfolio_optimization.pipeline` 补齐 |

方法目录：`hrp` / `risk_parity` / `cvar` / `black_litterman` / `herc` / …（见 `adapters/riskfolio`）。  
**结果状态恒为 `PROPOSAL`，禁止当作成交指令。**

---

## 6. 图表数据口径

**相关性热力图**：\(\mathrm{Corr}(r_i,r_j)\)；低/负相关利于分散。  
**资产配置对比**：各画像权重矩阵（仅列示权重大于阈值的资产）。

---

## 7. 效率诊断

相对有效前沿：

| 指标 | 含义 |
|---|---|
| `excess_vol` | 同收益下相对最小方差的多余波动 |
| `alpha_loss` | 同波动下相对可达收益的损失 |

---

## 8. 校验

```python
from 3_riskengine.portfolio.optimization import verify_business_modules

assert verify_business_modules(pack)["passed"]
```

单测：`3_riskengine/tests/test_investment_risk_portfolio_opt.py`。

---

## 9. 边界

- 取数（yfinance / db / openbb）在 processing / 业务层；引擎只消费已装入面板。  
- 不在引擎内下单或写 live 持仓；仿真改权走 `4_business.portfolio_optimization.simulation`。  
- 结果是风险与配置估计，不是会计估值或监管资本批复。
