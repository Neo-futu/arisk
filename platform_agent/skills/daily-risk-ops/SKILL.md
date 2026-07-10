---
name: daily-risk-ops
category: operations
description: ARISK 每日風控運維技能 — 日終快照計算、AI 異常檢測、數據驗證
tools: trigger_celery_task, get_task_status, check_system_health, query_business_db
agent: scheduler
version: "1.0"
---

# 每日風控運維技能

## 觸發條件

- 每個交易日 18:30（Celery Beat 定時觸發）
- 手動觸發：「跑一下今天的風控快照」

## 標準執行流程

### Phase 1 — 前置檢查（18:25）
```
check_system_health("all")
  → 所有服務 status="ok" → 繼續
  → 有服務異常 → 告警，等待恢復

query_business_db(
  "SELECT COUNT(*) FROM fsi.positions WHERE as_of_date = CURRENT_DATE"
)
  → count > 0 → 持倉已載入，繼續
  → count = 0 → 觸發 load_daily_positions 再確認
```

### Phase 2 — 執行快照（18:30）
```
trigger_celery_task(
  "compute_daily_risk_snapshot",
  kwargs={"fund_ids": [], "as_of_date": "2026-07-09"}
)
→ 記錄 task_id

get_task_status(task_id)  # 每隔 2 分鐘輪詢
→ SUCCESS → 進入 Phase 3
→ FAILURE → 重試（最多 3 次），仍失敗則告警
```

### Phase 3 — 驗證結果（快照完成後）
```
query_business_db("""
  SELECT fund_id, wam_days, wal_days,
         daily_liquid_pct, is_compliant, breach_flags
  FROM fsi.risk_snapshots
  WHERE as_of_date = CURRENT_DATE
""")
→ 確認所有基金有記錄
→ is_compliant=FALSE → 觸發合規告警
→ WAM 接近 60天 或 WAL 接近 120天 → 發預警
```

### Phase 4 — AI 異常檢測（Phase 3 完成後）
```
FOR EACH fund_id IN [BHMMF001, BHMMF002]:
  trigger_celery_task(
    "run_ai_anomaly_detection",
    kwargs={"fund_id": fund_id, "as_of_date": today}
  )
```

## 合規閾值告警規則

| 指標 | 警告閾值 | 違規閾值 |
|------|---------|---------|
| WAM  | > 55 天  | > 60 天 |
| WAL  | > 110 天 | > 120 天 |
| DLA  | < 10%   | < 7.5% |
| WLA  | < 18%   | < 15% |
