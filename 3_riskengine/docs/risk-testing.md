<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 风险情景分析业务模块 × RiskEngine

页面入口：`http://localhost:5173/risk-testing/sensitivity`（及侧栏各子菜单）  
引擎入口：`RiskEngine().bind(snapshot).risk().risk_testing(analytic, **params)`  
实现：`3_riskengine/risk/scenario_testing/` + `3_riskengine/risk/testing.py`  
业务域：`4_business.risk_testing.service`（装载 snapshot / 行情后委托引擎包）

本文说明的是**资管风控引擎业务能力**（敏感度、压力、情景、回测、XVA），不是页头工具栏或侧栏菜单本身。

模型在请求内实时计算；不创建第二套持仓主数据。HTTP `/api/v1/fsi/risk-testing/run` 经业务层调用本包。

适配器：FinancePy · 1.1.2｜Riskfolio-Lib · 7.3.0｜ORE / QuantLib · 1.43

---

## 1. 业务模块总览（十个子分析）

| 子菜单 | analytic | 时间语义 | 引擎键 / 公式要点 | 适配器 |
|---|---|---|---|---|
| 敏感度测试 | `SENSITIVITY` | 时点 | 中心差分 Δ/Γ | FinancePy |
| 压力测试 | `STRESS` | 时点 | 多因子联合再估值 PnL | FinancePy / ORE |
| 情景测试 | `SCENARIO` | 时点 | 情景冲击 + 资产类别聚合 | FinancePy / ORE |
| 反向压力测试 | `REVERSE_STRESS` | 时点 | 二分求临界冲击倍数 | FinancePy |
| 尾部风险测试 | `TAIL_RISK` | 区间 | 3σ–5σ 损失 vs 资本缓冲 | Riskfolio |
| 关键利率久期 | `KRD` | 时点 | 节点隔离 PV01 / KRD | FinancePy |
| PnL 归因 | `PNL_EXPLAIN` | 区间 | Carry+Rates+FX+Position+Residual | RiskEngine |
| 历史收益回测 | `HISTORICAL_BACKTEST` | 区间 | 买入持有路径 / MDD | NumPy·行情 |
| VaR 回测 | `VAR_BACKTEST` | 区间 | 滚动 VaR + Kupiec + 交通灯 | Riskfolio |
| 估值调整 XVA | `XVA` | 时点 | CVA/DVA/FVA/MVA 暴露积分 | ORE |

每个子分析返回统一页面模块：

| 模块 | 键 | 含义 |
|---|---|---|
| 参数语义 | `modules.parameters` | analytic、时点/区间、业务描述 |
| KPI 卡 | `modules.kpi_cards` | 净资产、PnL、持仓数、状态（及分析专属卡） |
| 结果表 | `modules.result_table` | sensitivities / buckets / points … |
| 数据质量 | `modules.data_quality` | 覆盖、假设 |
| 方法论 | `modules.methodology` | 公式、适配器、流水线 |

```python
from importlib import import_module

RiskEngine = import_module("3_riskengine").RiskEngine
st = import_module("3_riskengine.risk.scenario_testing")

pack = RiskEngine().bind(snapshot).risk().risk_testing(
    "SENSITIVITY",
    shocks=st.default_shocks(),
)
assert pack["analytic"] == "SENSITIVITY"
assert st.verify_business_modules(pack)["passed"]
assert pack["modules"]["result_table"]["rows"]
```

---

## 2. 敏感度测试

\[
\Delta \approx \frac{PV(+h)-PV(-h)}{2h},\quad
\Gamma \approx \frac{PV(+h)+PV(-h)-2\,PV}{h^{2}}
\]

默认五因子：`rate +1bp` / `fx +1%` / `vol +10%` / `equity +1%` / `cs +1bp`。  
也可传入单一因子冲击。结果行：`sensitivities[]`（delta / gamma / up_pnl / down_pnl）。

---

## 3. 压力 / 情景 / 反向压力

内置情景目录（`scenario.catalog`）：`gfc_2008`、`fed_hike_75`、`covid_2020`、`stagflation`，可自定义多因子 JSON。

- **压力 / 情景**：同步冲击再估值，披露 `pnl`、`by_asset_class`、`trade_values`。  
- **反向压力**：给定 `target_loss_pct_nav`，对情景冲击做二分缩放，求最小 `critical_scale` 使损失达标。

\[
\text{find } s^\* =\min\{s: -\mathrm{PnL}(s\cdot\mathrm{shocks})\ge \mathrm{target\_loss}\}
\]

---

## 4. 尾部风险与 VaR 回测

**尾部风险**（NAV 日收益，Riskfolio 历史分位）：

\[
\mathrm{loss}(\sigma)=\max\bigl(-(\mu-\sigma\cdot s)\cdot\mathrm{NAV},\,0\bigr)
\]

对照 `capital_buffer` 输出资本充足与是否击穿。

**VaR 回测**：滚动窗口历史 VaR，统计例外率，Kupiec LR（95% 临界值 3.841），交通灯 GREEN / YELLOW / RED。

---

## 5. KRD 与 PnL 归因

**KRD**：对各期限桶施加隔离利率 +1bp，

\[
\mathrm{KRD}_k=-\frac{\Delta PV_k}{PV\times 0.0001}
\]

**PnL 归因**：两期 snapshot 分解

\[
\Delta PV = \mathrm{Carry}+\mathrm{Rates}+\mathrm{FX}+\mathrm{Position}+\mathrm{Residual}
\]

信用 / 权益 / 波动残差按资产类归桶。

---

## 6. 历史收益回测

结束日持仓为投资范围；`CURRENT` 或 `CUSTOM` 权重。优先真实行情路径（processing 注入 `market`），否则回退 NAV 收益路径。披露总收益、年化、波动、最大回撤与 `backtest_points`。

---

## 7. XVA

ORE 适配器基于组合映射交易的 EPE/ENE 曲线积分：

| 调整 | 含义 |
|---|---|
| CVA | 交易对手违约成本 |
| DVA | 自身信用受益 |
| FVA | 融资成本 |
| MVA | 初始保证金融资 |

不启动 OREApp XML；`ore_app=false`。

---

## 8. 流水线

1. `load_portfolio_snapshot` → `RiskEngine.bind`  
2. 按 analytic 选择再估值 / Riskfolio NAV / 归因 / 回测 / XVA  
3. `stamp`：engine、adapters、data_quality、assumptions、implementation  
4. `modules.*` 供前端 KPI / 表 / 方法论直接消费  
5. 限额旁路：`3_riskengine.limits.evaluate`（业务层附加）

---

## 9. 边界

- 引擎包不读库；区间回测的行情面板由 processing `load_historical_market_data` 注入。  
- 业务与前端禁止直接 `import financepy|riskfolio|QuantLib`。  
- 结果是风险估计与模型验证输入，不是会计估值或监管资本批复。  
- 优化 / 回测权重调整**不是**交易指令。
