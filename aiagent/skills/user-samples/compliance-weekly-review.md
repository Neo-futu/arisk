---
name: compliance-weekly-review
category: user-sample
layer: chat         # 用戶層技能（Chat Agent 使用）
description: 用戶個人技能樣本 — 週度合規審查報告，適合合規審查員
tools: get_system_info, get_exposure, get_var_compare, get_positions, knowledge_search
usage: 合規審查員可將此添加到個人技能
version: "1.0"
---

# 週度合規審查技能（用戶個人技能樣本）

## 適合對象

合規審查員 / 風控主任 — 每週五生成本週合規審查報告

## 觸發條件

- 「週度合規報告」/ 「本週合規情況」/ 「weekly review」
- 「SFC 合規總結」

## 執行步驟

### Step 1 — 獲取本週數據
```
# 獲取最新暴露數據
FOR fund_id IN [BHMMF001, BHMMF002]:
    get_exposure(fund_id, today)
    get_var_compare(fund_id, today, confidence=0.99)
    get_positions(fund_id, today)
```

### Step 2 — 查詢相關法規背景
```
knowledge_search(
    query="SFC 守則第 8.2 章 WAM WAL 流動性要求",
    source="sfc_regulation"
)
→ 引用具體條款支持判斷
```

### Step 3 — 生成週報

## 週報輸出模板

```markdown
# 週度 SFC 合規審查報告
**審查週期**：{start_date} 至 {end_date}
**審查員**：[用戶姓名]
**審查基準**：《單位信託及互惠基金守則》第 8.2 章

---

## 1. 合規總結

| 基金 | WAM | WAL | DLA | WLA | 合規狀態 |
|------|-----|-----|-----|-----|---------|
| BHMMF001 | XX 天 | XX 天 | XX% | XX% | ✅/❌ |
| BHMMF002 | XX 天 | XX 天 | XX% | XX% | ✅/❌ |

## 2. 風險評估

### VaR 對比（99% 置信度）
| 基金 | 歷史模擬法 | 蒙特卡洛 | 參數法 | 最保守值 |
|------|----------|---------|-------|---------|
| BHMMF001 | ... | ... | ... | ... |

## 3. 持倉合規核查

### 發行人集中度（SFC 限額：單一 ≤10%，同集團 ≤20%）
[前 10 大持倉及佔比]

### 到期期限分佈
[WAM/WAL 貢獻分析]

## 4. 法規條款引用
[來自 knowledge_search 的相關條款]

## 5. 審查結論
[合規 / 有條件合規 / 違規（附改善建議）]

## 6. 下週關注事項
[即將到期持倉 / 接近閾值的指標 / 市場關注點]

---
*本報告由 ARISK Chat Agent 輔助生成，審查員負責最終確認*
```

## 個性化配置（合規審查員）

```
我是 [公司] 的合規審查員，
主要審查 BHMMF001 和 BHMMF002 的 SFC 守則第 8.2 章合規狀況。
每次對話請以嚴謹的合規視角分析，引用具體條款。
報告需要中英文對照重要術語。
```
