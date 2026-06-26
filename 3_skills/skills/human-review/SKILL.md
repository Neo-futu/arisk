---
name: human-review
description: >
  人工審核技能：指導 agent 在關鍵步驟前暫停、生成審核請求、等待批准、
  根據決策繼續或中止。所有涉及寫入、發布、合規違規的操作必須觸發此技能。
triggers:
  - requires review
  - 需要審核
  - compliance breach
  - 合規違規
  - before writing
  - 寫入前
  - publish report
  - 發布報告
  - human approval
  - 人工批准
---

# 人工審核技能

## 核心原則

> **任何不可逆操作在執行前必須停止並獲得人工批准。**

「不可逆操作」包括：
- 寫入數據庫（持倉、NAV、風控快照）
- 發布報告到外部（S3 公開 URL、郵件分發）
- 存在 SFC 守則違規時繼續運行
- Agent 交接到下一個具有寫入權限的子 agent

---

## 審核觸發矩陣

| 場景 | 類別 | 優先級 | 強制 / 可選 |
|------|------|--------|------------|
| WAM/WAL/集中度超守則限額 | `COMPLIANCE_BREACH` | 🔴 緊急 | **強制** |
| VaR > NAV 5% 或 CVaR > NAV 8% | `HIGH_RISK` | 🔴 緊急 | **強制** |
| 報告對外發布前 | `REPORT_PUBLISH` | 🟡 正常 | **強制** |
| 批量持倉寫入 DB | `DATA_WRITE` | 🟡 正常 | **強制** |
| 新持倉文件載入 | `DATA_LOAD` | 🟡 正常 | **強制** |
| Agent 交接到 report-writer | `AGENT_HANDOFF` | 🟡 正常 | **強制** |
| 手動觸發 | `MANUAL` | 🟢 低 | 可選 |

---

## Agent 在審核點的標準流程

### Step 1：識別審核需要
在執行任何上述操作前，agent 必須主動識別是否需要審核。
不要假設可以直接執行。

### Step 2：構建審核請求

審核請求必須包含：
```json
{
  "category": "COMPLIANCE_BREACH",
  "title": "WAM 超限：{實際值} > 60天上限",
  "summary": "基金 {fund_id} 在 {date} 的 WAM 為 {值}天，超過 SFC 守則第8.2(f)條上限 60天。建議：縮短組合期限。",
  "triggered_by": "{agent-name}",
  "fund_id": "{fund_id}",
  "payload": {
    "breach_flags": {...},
    "wam_days": ...,
    "threshold": 60,
    "positions_contributing": [...]
  },
  "artefact_path": "artefacts/{report_file}.xlsx"
}
```

**summary 必須包含：**
- 違規/風險的具體數值
- 適用的守則條款（如 SFC 第8.2(f)條）
- 建議採取的措施
- 如果批准，將執行什麼操作

### Step 3：提交並等待

```
POST /review/request → 獲得 review_id
```

**停止輸出任何中間結果**，直到收到決策通知。
不要推測審核結果，不要假設會被批准。

### Step 4：根據決策行動

**批准（APPROVED）：**
- 繼續執行被保護的操作
- 在 artefact/報告中記錄「已獲 {reviewer} 於 {time} 批准」

**拒絕（REJECTED）：**
- **立即停止**被保護的操作
- 向用戶報告：「操作已被 {reviewer} 拒絕，原因：{reason}」
- 不要嘗試繞過或重新提交相同的請求
- 記錄到審計日誌

---

## 在 SKILL 的其他步驟中插入審核點

### risk-analysis 中的審核點

```
Step 3（暴露計算後）→ 如發現 breach_flags 非空 → 觸發 COMPLIANCE_BREACH 審核
                        ↓ 等待批准
Step 5（生成報告前）→ 觸發 REPORT_PUBLISH 審核
                      ↓ 等待批准
Step 5（寫入 DB）→ 觸發 DATA_WRITE 審核
                   ↓ 等待批准
```

### mmf-compliance 中的審核點

```
完成逐條核查後 → 如任一條款違規 → 強制觸發 COMPLIANCE_BREACH 審核
不論是否違規 → 發布合規報告前 → 觸發 REPORT_PUBLISH 審核
```

---

## 審核等待期間的行為規範

- ✅ 繼續回答用戶的其他問題
- ✅ 展示已計算完成的只讀數據（不寫入）
- ✅ 說明正在等待審核的操作和 review_id
- ❌ 不要執行任何寫入操作
- ❌ 不要假設審核結果並提前生成「已批准」的輸出
- ❌ 不要繞過審核直接執行（即使看起來很安全）

---

## 審核超時處理

如果審核超過 SLA 時限（COMPLIANCE_BREACH: 30分鐘，其他: 60分鐘）：
1. 向用戶發出警告：「審核請求 {review_id} 已超過 {sla} 分鐘未處理」
2. 系統自動將請求標記為 `EXPIRED`
3. **被保護的操作不得執行**（不能因超時而自動批准）
4. 建議用戶重新提交或聯繫審核員

---

## 給審核員的信息格式

每次觸發審核時，向審核員展示：

```
⚠️ 需要人工審核

標題: {title}
類別: {category}
優先級: {🔴緊急/🟡正常/🟢低}
基金: {fund_id}  日期: {date}
SLA: {sla_minutes} 分鐘內處理

摘要:
{summary}

如批准，將執行:
{action_description}

相關文件: {artefact_url}

[前往審核收件箱] → {review_url}
```
