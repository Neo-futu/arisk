<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# adapter — 旧新接口适配

## 用途

在遗留模块与 `3_riskengine` / `4_business` 之间转换请求与响应形状（DTO、单位、日期语义等）。

## 与 3_riskengine/adapters 的区别

| 目录 | 层级 |
|---|---|
| `adapter/`（根） | 平台级：旧 Processing 合同 ↔ 新 Business/RiskEngine 合同 |
| `3_riskengine/adapters/` | 引擎级：RiskEngine ↔ FinancePy / Riskfolio / ORE |
| `5_integrations/` | 外部系统：PMS/OMS/行情/托管/FA ↔ ARISK Data Contract |

Wave 2 仅 skeleton；首个适配器在 Canonical Data Contracts Wave 后引入。
