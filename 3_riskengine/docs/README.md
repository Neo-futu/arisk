<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# RiskEngine 文档目录

本目录是 **ARISK RiskEngine**（`3_riskengine/`，版本见 `core/lineage.py`）给人读的说明。三库调研与路由表仍以 [`target-architecture.md`](target-architecture.md) 为权威。

| 文档 | 读者 | 内容 |
|---|---|---|
| [架构和接口](architecture-and-interfaces.md) | 架构 / 业务 / 接入方 | 分层、对象模型、绑定 API、HTTP / Python / Quant 入口 |
| [代码和说明](codebase-guide.md) | 开发 | 目录、模块职责、关键函数、血缘字段 |
| [产品与金融业务](products-and-business.md) | 业务 / 产品 / 风控 | 全部 ProductKind、指标、风险流程、报表 |
| [开发细化](development-playbook.md) | 开发 + 业务一起迭代 | 如何加产品、指标、流程、报表；红线与测试 |
| [平台切片开发](platform-incremental-verification.md) | 开发 + 业务 | 枚举资产/产品/指标/情景/估值；索引；单切片实现示例 |
| [目标架构](target-architecture.md) | 架构 | FinancePy / ORE / Riskfolio 能力矩阵与路由 |

**边界（全部文档共用）：**

- 业务与前端禁止 `import financepy|ORE|QuantLib|riskfolio`。厂商只在 `adapters/`。
- 不创建第二套持仓 / 市场主数据。权威表是 `fsi.balance_*` / `fsi.mktdata_*` / `fsi.para_portfolio`。
- 不跑 `OREApp` / InputParameters XML。不构造 `FixedRateBond` / `DiscountingBondEngine` / `Swaption` / `CreditDefaultSwap` 工具对象。
- HTTP `/api/v1/fsi/risk-testing/*` 仍委托 `ProfessionalRiskEngine` → `core/kernel`，以保持已发布数字。
- 计算结果是风险估计，不是会计估值或监管资本批复。
