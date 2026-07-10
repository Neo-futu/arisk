---
name: portfolio-morning-brief
category: user-sample
layer: chat         # 用戶層技能（Chat Agent 使用）
description: 用戶個人技能樣本 — 每日早上自動生成投資組合晨報
tools: get_system_info, get_exposure, get_var, get_positions
usage: 複制此文件到用戶個人技能配置，根據需要修改
version: "1.0"
---

# 投資組合晨報技能（用戶個人技能樣本）

## 使用方法

1. 在 Chat 頁面「個人設置」中將此技能模板添加到自定義指令
2. 或者直接對話：「幫我生成今天的晨報」

## 觸發條件

- 「今天晨報」/ 「早安報告」/ 「morning brief」
- 「今天市場情況」/ 「組合狀況」

## 執行步驟

### Step 1 — 確認參數
```
get_system_info()
→ 確認 fund_id 和 current_date
→ 用戶慣用的基金（在個人設置中配置）
```

### Step 2 — 拉取核心數據
```
get_exposure(fund_id, today)
→ WAM / WAL / DLA / WLA / 合規狀態

get_var(fund_id, today, method="historical", confidence=0.99)
→ 99% VaR

get_positions(fund_id, today)
→ 前 5 大持倉
```

### Step 3 — 生成晨報

## 晨報輸出模板

```markdown
# {基金名稱} 投資組合晨報
**日期**：{today} | **基金**：{fund_id}

## 風險指標概覽
| 指標 | 今日 | SFC 上限 | 狀態 |
|------|------|---------|------|
| WAM  | XX 天 | 60 天 | ✅/🟡/🔴 |
| WAL  | XX 天 | 120 天 | ✅/🟡/🔴 |
| DLA  | XX% | ≥7.5% | ✅/🟡/🔴 |
| WLA  | XX% | ≥15% | ✅/🟡/🔴 |
| VaR(99%) | HKD XX | — | — |

## 合規狀態
{is_compliant ? "✅ 完全合規" : "❌ " + breach_flags}

## 前 5 大持倉
| 發行人 | 資產類型 | 佔比 |
|-------|---------|------|
| {issuer_1} | {type} | XX% |
...

## 今日關注事項
- {如有接近閾值的指標，自動提示}
- {如有即將到期的持倉，自動提示}
```

## 個性化配置建議

複制此模板到 `iam.user_agent_config.custom_instructions`：

```
我是 [職位]，主要關注 [fund_id]。
每次對話請優先確認今日數據是否已更新。
晨報格式請使用簡潔版（3段式：指標+合規+持倉）。
```
