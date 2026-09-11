<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# portfolio_optimization — 组合配置与优化

第二大核心业务域：应该配置什么组合？

```
Optimization
    ↓
RiskEngine
    ↓
Valuation
    ↓
Investment Risk
    ↓
Risk Testing
    ↓
Limits
```

优化结果是 **提案（PROPOSAL）**，不是交易指令；未经授权不得改 Live Portfolio。

## 引擎

Riskfolio-Lib，只经 `3_riskengine.adapters.riskfolio`。库未安装时使用 RiskEngine 确定性 fallback（含既有 PyPortfolioOpt / native HRP）。

## 模块

construction / SAA / TAA / risk_budget / risk_parity / black_litterman / hrp / herc / cvar / constraints / liquidity / turnover / simulation / validation

## Simulation Portfolio

Live → Clone → Simulation → Modify → Optimize → Stress → Compare。仿真仓不写 `fsi.balance_*`。

前端路由 `/portfolio-opt` 保持兼容。
