<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# RiskEngine 文档目录

本目录是 **ARISK RiskEngine**（`3_riskengine/`，版本见 `core/lineage.py`）给人读的说明。三库调研与路由表仍以 [`target-architecture.md`](target-architecture.md) 为权威。

| 文档 | 读者 | 内容 |
|---|---|---|
| [架构和接口](architecture-and-interfaces.md) | 架构 / 业务 / 接入方 | 分层、对象模型、绑定 API、HTTP / Python / Quant 入口 |
| [代码和说明](codebase-guide.md) | 开发 | 目录、模块职责、关键函数、血缘字段 |
| [产品与金融业务](products-and-business.md) | 业务 / 产品 / 风控 | 全部 ProductKind、指标、风险流程、报表 |
| [组合驾驶舱](portfolio-cockpit.md) | 业务 / 风控 / 开发 | 组合·规模·持仓资产类型·收益·净值五大业务模块与引擎口径 |
| [组合概况](investment-risk-overview.md) | 业务 / 风控 / 开发 | `/investment-risk/overview`：组合·区间收益·配置·Top10股债·行业 |
| [整体风险敞口 / 基本信息](investment-risk-indicators.md) | 业务 / 风控 / 开发 | `/investment-risk/indicators` 基本信息：组合·币种·成立日·WAM/WAL·投管人员 |
| [风险指标 Tab / 六大风控类型](investment-risk-risk-metrics.md) | 业务 / 风控 / 开发 | `#risk-exposure` 风险指标：核心五卡·滚动波动·VaR三方法·市场/信用/流动性/集中度/合规/压力 |
| [业绩归因 Tab](investment-risk-attribution.md) | 业务 / 风控 / 开发 | indicators 业绩归因：Brinson BHB/BF·Campisi·个券贡献 Carino·资产贡献·Beta（独立模型包） |
| [利率信用 Tab](investment-risk-rates-credit.md) | 业务 / 风控 / 开发 | indicators 利率信用：债账本·久期/DV01/CS01·期限分桶·评级/多机构·发行人集中（独立模型包） |
| [产品压力测试 Tab](investment-risk-product-stress.md) | 业务 / 风控 / 开发 | indicators 产品压力测试：LQAP 假设·Overview·赎回·Horizon·Stress·LQA 字段（独立模型包） |
| [因子风险](investment-risk-factor-risk.md) | 业务 / 风控 / 开发 | `/investment-risk/factor-risk`：因子敞口·标准冲击 PnL·RC·Beta/TE（独立模型包） |
| [基本面因子与行为](investment-risk-factor-behavior.md) | 业务 / 风控 / 开发 | `/investment-risk/factor-behavior`：Momentum/LowVol/Size·行业 HHI·拥挤度（独立模型包） |
| [组合配置与优化](portfolio-opt.md) | 业务 / 风控 / 开发 | `/portfolio-opt`：收益模型·有效前沿·画像·HRP 闸门（提案非成交，独立模型包） |
| [风险预算与前置试算](investment-risk-pretrade-budget.md) | 业务 / 风控 / 开发 | `/investment-risk/pretrade-budget#risk-budget`：决策闸门·久期/VaR 预算·RC·RP·因子冲击对比（独立模型包） |
| [风险情景分析](risk-testing.md) | 业务 / 风控 / 开发 | `/risk-testing/*`：敏感度·压力·情景·反向压力·尾部·KRD·PnL·历史/VaR回测·XVA（独立模型包） |
| [数据流：bound / products / Top10](data-flow-bound-products.md) | 开发 / 接入 | 库表→2_processing→bind→products→前十大个股 |
| [开发细化](development-playbook.md) | 开发 + 业务一起迭代 | 如何加产品、指标、流程、报表；红线与测试 |
| [平台切片开发](platform-incremental-verification.md) | 开发 + 业务 | 枚举；索引；单切片。引擎包 `scripts/riskengine/`，闭环 `scripts/platform_workflow.py` |
| [目标架构](target-architecture.md) | 架构 | FinancePy / ORE / Riskfolio 能力矩阵与路由 |

**边界（全部文档共用）：**

- 业务与前端禁止 `import financepy|ORE|QuantLib|riskfolio`。厂商只在 `adapters/`。
- 不创建第二套持仓 / 市场主数据。权威表是 `fsi.balance_*` / `fsi.mktdata_*` / `fsi.para_portfolio`。
- 不跑 `OREApp` / InputParameters XML。不构造 `FixedRateBond` / `DiscountingBondEngine` / `Swaption` / `CreditDefaultSwap` 工具对象。
- HTTP `/api/v1/fsi/risk-testing/*` 经 `4_business.risk_testing` 委托 `risk().risk_testing`（`scenario_testing` 包）。
- 计算结果是风险估计，不是会计估值或监管资本批复。
