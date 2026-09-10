<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 4_business — 业务用例层

## 模块定位

```
Frontend / Backend API
        ↓
【4_business】  ← 本层（用例编排）
        ↓
3_riskengine + 5_integrations + 1_datastorage
```

## 子域

- `investment_risk/` — 投资风险分析
- `portfolio_optimization/` — 组合配置与优化（Riskfolio，过闸提案，仿真仓）
- `risk_testing/` — 敏感度、情景、压力、尾部、XVA 等
- `portfolio_management/` — 组合主数据、持仓、NAV
- `trading/` — 模拟订单、Pre-trade / Post-trade
- `operations/` — Valuation / NAV / PnL / 托管 / 基金行政
- `risk_governance/` — 风险政策、限额、违约、审批、审计；Pre-Trade

## 迁移原则

1. 先抽合同与用例边界，再迁算法至 `3_riskengine`
2. 保留全部现有 API 路径与 Frontend 路由
3. 共享能力（报表、调度、合规）后续归入各域或 `shared/`（目标架构）
