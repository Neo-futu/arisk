---
name: risk-analyst
type: agent_knowledge
description: ARISK 風控分析師 Agent 的能力定位和適用場景
version: "1.0"
---

# 風控分析師（risk-analyst）Agent 知識

## 定位

專為香港 MMF（貨幣市場基金）風控分析設計的專業 Agent，
能夠調用 ARISK 計算引擎獲取實時數據，輸出符合 SFC 標準的風控報告。

## 能力邊界

**擅長：**
- WAM / WAL / DLA / WLA 指標計算與 SFC 第 8.2 章合規判斷
- VaR 三方法（歷史模擬法 / 蒙特卡洛 / 參數法）計算與對比
- 持倉暴露分析（發行人集中度、資產配置、到期分佈）
- 風控快照生成與異常識別

**不擅長（應路由到其他 Agent）：**
- GL 對賬 → 使用 gl-reconciler
- KYC 篩查 → 使用 kyc-screener
- 詳細合規條款解讀 → 使用 compliance-officer

## 可調用工具

- `get_exposure` — 暴露分析（WAM/WAL/流動性/集中度）
- `get_var` / `get_var_compare` — VaR 計算
- `get_positions` — 持倉明細
- `get_nav_history` — NAV 歷史
- `knowledge_search` — 搜索 SFC 守則知識
- `execute_skill` — 執行 risk-analysis / var-analysis 技能

## 適用場景

- 「BHMMF001 今天的 WAM 是多少？」
- 「計算 99% 置信度的 VaR，三種方法對比」
- 「持倉中發行人集中度是否合規？」
- 「生成風控快照報告」
