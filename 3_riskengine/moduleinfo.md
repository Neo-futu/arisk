<!-- 更新时间：2026-09-10（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 3_riskengine — 统一量化与风险引擎

## 模块定位

目标架构第二层计算内核，介于 `4_business`（业务用例）与 `adapters/`（第三方库）之间。

```
4_business（业务用例）
      ↓
【3_riskengine】  ← 本层
  估值 | 风险 | 情景 | 流动性 | 交易对手 | PnL | 限额 | 验证 | Governance
      ↓
  adapters/ → FinancePy / Riskfolio / ORE
      ↓
  1_datastorage fsi.balance_* / fsi.mktdata_*
```

## 当前状态

- Phase A–J 已完成。RiskEngine **1.0.0** 是 ARISK 资产管理风险基础设施。
- FinancePy → Product / Market / Model；ORE → Trade / XVA（无 OREApp XML）；Riskfolio → Portfolio Risk / Optimization。
- MMF 与 Equity / Bond / FX / Option / Future 同级。
- `ProfessionalRiskEngine` / HTTP 仍委托 `core/kernel` 以保持已发布数字。
- FinancePy / Riskfolio / ORE 只在 `adapters/`。

## 子模块

见 [`README.md`](README.md)、[`docs/README.md`](docs/README.md) 与 [`docs/target-architecture.md`](docs/target-architecture.md)。
