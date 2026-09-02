<!-- 更新时间：2026-09-02（北京时间）｜生成模型：GPT-5.6 Sol -->

# 风险测试（FinancePy Professional Risk Engine）

## 定位

`risk_testing` 是独立于“投资风险分析”和“组合优化”的专业风险测试模块。模块只复用 ARISK 已有的三类权威输入：

1. `fsi.balance_*` 的组合与持仓快照；
2. `fsi.mktdata_*` 与 NAV 历史市场数据；
3. `PortfolioViewer` 组合级授权及现有角色菜单授权。

模块不创建第二套组合、行情或用户权限主数据。固定收益重估优先使用 FinancePy 1.1.2 `FlatDiscountCurve`（兼容旧版 `DiscountCurveFlat`），所有报告披露有效估值日、数据覆盖和模型假设。

## 分层架构

| 层次 | 实现 |
|---|---|
| 核心估值 | FinancePy 贴现曲线、统一冲击重估、交易级 PV/PnL |
| 风险计量 | 敏感度、压力、情景、反向压力、尾部风险、KRD、PnL Explain、VaR/CVaR 回测、XVA |
| 数据与配置 | 现有 ARISK 数据库加载器、JSON API、XML 配置 API |
| 客户端 | React GUI、CSV/Excel/LibreOffice、Python/Jupyter REST client |
| QA/模型验证 | 确定性跨资产样例、方向性、平衡性、覆盖率与回归测试 |

### 输入与估值模块

| Python 模块 | 职责 |
|---|---|
| `risk_testing.portfolio_data` | 从现有 `fsi.balance_*` 表读取组合头、债券、CD、存款、股票、基金和现金持仓，并对账 NAV |
| `risk_testing.market_data` | 从现有 `fsi.balance_portfolio_nav` 与 `fsi.mktdata_quotes` 读取 NAV 收益和证券历史波动率 |
| `risk_testing.loader` | 组合持仓与市场数据编排，不保存第二套主数据 |
| `risk_testing.financepy_adapter` | 将估值日转换为 FinancePy `Date`，创建 `FlatDiscountCurve`，调用 `df_t()` 和 `bump_parallel()`；旧版自动回退 `DiscountCurveFlat` |
| `risk_testing.engine` | 统一交易级 PV、冲击后 PV、PnL 与风险因子重估内核 |

### 子菜单业务模块与 FinancePy 调用

| 子菜单 | Python 调用模块 | FinancePy / 补充算法 |
|---|---|---|
| 敏感度测试 | `risk_testing.analytics.sensitivity.run` | `FlatDiscountCurve.df_t()`、`bump_parallel()`；中心差分 Delta/Gamma |
| 压力测试 | `risk_testing.analytics.stress.run` | FinancePy 曲线冲击重估；多因子交易级 PnL 聚合 |
| 情景测试 | `risk_testing.analytics.scenario.run` | FinancePy 曲线冲击重估；自定义/历史情景同步冲击 |
| 反向压力测试 | `risk_testing.analytics.reverse_stress.run` | 重复 FinancePy 重估；二分法求最小破产/损失冲击倍数 |
| 尾部风险测试 | `risk_testing.analytics.tail_risk.run` | FinancePy PV 作为估值基础；NumPy 历史分位数、CVaR/ES、3σ–5σ |
| KRD | `risk_testing.analytics.krd.run` | `FlatDiscountCurve.bump_parallel()` + `df_t()` 节点隔离重估 |
| PnL 归因 | `risk_testing.analytics.pnl_explain.run` | FinancePy 估值持仓输入；Carry、Rates、FX、Position、Residual 对账 |
| VaR 回测 | `risk_testing.analytics.var_backtest.run` | FinancePy PV 作为估值基础；NumPy VaR/CVaR 与 Kupiec LR |
| XVA | `risk_testing.analytics.xva.run` | `FlatDiscountCurve.df_t()` 贴现 EPE/ENE；CVA/DVA/FVA/MVA 积分 |

每次运行的 API 响应均返回 `implementation`，明确记录本次实际业务模块、FinancePy 类/方法、持仓模块、市场数据模块和补充算法。

## 菜单

一级菜单“风险测试”包含独立子菜单：

- 敏感度测试
- 压力测试
- 情景测试
- 反向压力测试
- 尾部风险测试
- 关键利率久期 KRD
- PnL 归因
- VaR 回测
- 估值调整 XVA

菜单使用已有 `PORTFOLIO_VIEWER`、`INVESTMENT_DIRECTOR`、`INVESTMENT_MANAGER`、`SYSTEM_ADMIN` 角色；运行接口继续执行组合级 `PortfolioViewer` 授权。

## API

- `GET /api/v1/fsi/risk-testing/capabilities`
- `GET /api/v1/fsi/risk-testing/catalog`
- `POST /api/v1/fsi/risk-testing/run/{fund_id}`
- `POST /api/v1/fsi/risk-testing/run-xml/{fund_id}`

JSON 敏感度测试示例：

```json
{
  "analytic": "SENSITIVITY",
  "as_of_date": "2026-09-01",
  "shocks": [
    {"factor_type": "RATE", "value": 0.0001, "mode": "ABSOLUTE", "label": "Rate +1bp"},
    {"factor_type": "FX", "value": 0.01, "mode": "RELATIVE", "label": "FX +/-1%"},
    {"factor_type": "VOLATILITY", "value": 0.10, "mode": "RELATIVE", "label": "Vol +10%"}
  ]
}
```

XML 多因子情景示例：

```xml
<riskRun analytic="SCENARIO" as_of_date="2026-09-01">
  <scenario id="custom" name="Policy shock" />
  <parameters confidence="0.99" lookback_days="500" />
  <shocks>
    <shock factor_type="RATE" value="0.0075" mode="ABSOLUTE" label="Rate +75bp" />
    <shock factor_type="EQUITY" value="-0.08" mode="RELATIVE" label="Equity -8%" />
  </shocks>
</riskRun>
```

## Python 与 Jupyter

`2_processing/tools/risk_testing/client.py` 提供 `RiskTestingClient`。客户端调用认证后的 backend API，因此不会绕过用户、角色和组合权限。相同代码可直接用于 Python/IPython/Jupyter。

## Excel 与 LibreOffice

每个结果页提供 CSV 导出；Excel 与 LibreOffice 可直接打开。需要自动化时，可通过“从 Web/REST”调用 JSON/XML API，Bearer token 由现有 ARISK 登录流程签发。

## 模型治理

本模块完整覆盖上述风险工作流，但不声称逐产品复制 ORE 的全部交易类型、QuantLib 模型、SIMM、CSA 和 Monte Carlo 基础设施。当前 XVA 是透明的确定性 EPE/ENE 积分；交易级 CSA、净额结算、抵押品路径与模拟 XVA 是明确扩展点。任何近似均在 API `assumptions` 和 `data_quality` 中披露，不能作为未经模型验证的会计价格或监管资本结果。
