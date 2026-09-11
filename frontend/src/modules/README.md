<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# frontend/src/modules — 业务模块归属

路由保持兼容；`portfolio-opt/` 目录名不改。一级菜单与 Workbench 合同见 `frontend/src/platform/nav.ts`。

| 业务域 | 菜单 | 模块目录 | 路由 |
|---|---|---|---|
| 投资风险分析 | 投资风险分析 | `investment-risk/` | `/investment-risk/*` |
| 组合配置与优化 | 组合配置与优化 | `portfolio-opt/` | `/portfolio-opt` |
| 风险测试 | 风险测试 | `risk-testing/` | `/risk-testing/*` |
| 组合与持仓 | 数据管理 / 持仓 / 驾驶舱 | `data-management/`、`portfolio-cockpit/` | `/data-management`、`/positions`、`/portfolio-cockpit` |
| 估值与损益 | 估值与损益 | `valuation-pnl/` | `/valuation` |
| 市场数据与指标 | 市场数据与指标 | `indicator-explorer/`、`sql-library/` | `/indicator-explorer`、`/sql-library` |
| 系统管理 | 系统管理 | `system-config/` | `/system-config` 等 |

Frontend 只做 Input / API / Visualization / Interaction。金融结果来自 RiskEngine。
