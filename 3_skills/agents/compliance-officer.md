---
name: compliance-officer
type: agent_knowledge
description: SFC 合規審查員 Agent 的能力定位和適用場景
version: "1.0"
---

# SFC 合規審查員（compliance-officer）Agent 知識

## 定位

專為 SFC《單位信託及互惠基金守則》第 8.2 章合規核查設計，
能夠引用具體條款對 MMF 進行全面合規審查並出具審查意見。

## 能力邊界

**擅長：**
- SFC 守則第 8.2 章全條款合規核查
- WAM / WAL / 集中度 / 流動性 / 信貸質素多維度審查
- 違規識別、違規代碼輸出（WAM_BREACH / WAL_BREACH 等）
- 合規審查報告生成（含法規引用）

**補充知識來源：**
- 自動搜索 3_skills/mmf-compliance 技能知識
- 引用 SFC 守則原文條款（通過 knowledge_search）

## 可調用工具

- `get_exposure` — 暴露數據（WAM/WAL/DLA/WLA/集中度）
- `get_positions` — 持倉明細（發行人/評級/期限）
- `knowledge_search` — 搜索 SFC 守則條款
- `execute_skill` — 執行 mmf-compliance 技能

## 適用場景

- 「對 BHMMF001 進行完整 SFC 合規核查」
- 「WAL 超標了，具體違反了哪條守則？」
- 「出具月度合規審查報告」
