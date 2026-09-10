<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# portfolio_optimization

| 项 | 说明 |
|---|---|
| 菜单 | 组合优化 |
| 路由 | `/portfolio-opt`（保留） |
| 引擎 | Riskfolio via `3_riskengine.adapters.riskfolio` |
| 闸门 | Optimization → RiskEngine → Valuation → Investment Risk → Risk Testing → Limits |
| 仿真仓 | Clone live；禁止未授权写 Live |
| 旧引擎 | PyPortfolioOpt：`2_processing/tools/performance/portfolio_optimizer.py`（`/analyze` 兼容） |
