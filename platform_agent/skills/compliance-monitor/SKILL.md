---
name: compliance-monitor
category: operations
description: SFC MMF 合規自動監控操作手冊 — Platform Agent 每日執行合規核查的步驟
tools: query_business_db, check_system_health, trigger_celery_task
agent: monitor
version: "1.0"
---

# SFC MMF 合規監控操作手冊

> 這是 Platform Agent monitor 的操作手冊，說明如何執行合規監控流程。
> 合規業務知識（守則條款、指標定義）請查詢 3_skills/mmf-compliance。

## 觸發時機

每日風控快照完成後自動觸發（由 scheduler 協調）。

## 執行步驟

### Step 1 — 讀取快照結果
```sql
SELECT fund_id, as_of_date, wam_days, wal_days,
       daily_liquid_pct, weekly_liquid_pct,
       is_compliant, breach_flags
FROM fsi.risk_snapshots
WHERE as_of_date = CURRENT_DATE
ORDER BY fund_id
```
（通過 `query_business_db` 執行）

### Step 2 — 評估告警級別

| 指標 | 🔴 違規 | 🟡 預警 | ✅ 正常 |
|------|--------|--------|--------|
| WAM  | > 60天  | 55-60天 | ≤ 55天 |
| WAL  | > 120天 | 110-120天 | ≤ 110天 |
| DLA  | < 7.5%  | 7.5%-10% | ≥ 10% |
| WLA  | < 15%   | 15%-18% | ≥ 18% |

### Step 3 — 觸發 AI 深度分析（有預警時）
```
trigger_celery_task("run_ai_anomaly_detection",
  kwargs={fund_id, as_of_date})
```

### Step 4 — 輸出監控報告

格式見 3_skills/mmf-compliance 的輸出模板。

## 緊急處理

🔴 發現違規 → 立即通知風控主任（記錄到 iam.frontend_log，level=error）
🟡 發現預警 → 加入下次晨報，建議持倉調整
