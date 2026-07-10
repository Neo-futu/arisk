---
name: etl-ops
category: operations
description: ARISK ETL 運維技能 — 持倉載入、行情更新、數據質量驗證
tools: trigger_celery_task, get_task_status, query_business_db
agent: etl-coordinator
version: "1.0"
---

# ETL 運維技能

## 觸發條件

- 每日 09:00（Celery Beat：load_daily_positions）
- 每小時（Celery Beat：refresh_price_cache）
- 手動：「今天的持倉沒有載入」

## 持倉數據載入（每日 09:00）

### 執行步驟
```
1. trigger_celery_task("load_daily_positions")
   → task_id

2. get_task_status(task_id)
   → SUCCESS → 執行驗證

3. 驗證 SQL:
   SELECT fund_id,
          COUNT(*) as positions,
          SUM(market_value_hkd) as total_nav_hkd,
          MIN(as_of_date) as data_date
   FROM fsi.positions
   WHERE as_of_date = CURRENT_DATE
   GROUP BY fund_id

4. 預期結果：
   BHMMF001 → positions > 20, total_nav_hkd > 0
   BHMMF002 → positions > 20, total_nav_hkd > 0
```

### 異常處理

| 異常 | 原因 | 處理 |
|------|------|------|
| positions = 0 | ETL 失敗或源數據問題 | 重試，確認源系統 |
| total_nav_hkd ≤ 0 | 估值異常 | 告警人工確認 |
| as_of_date ≠ today | 舊數據 | 確認 ETL 是否成功 |

## 行情緩存更新（每小時）

```
trigger_celery_task("refresh_price_cache")
  → 從 Wind MCP 拉取最新行情
  → 存入 Redis（DB0）
  → TTL: 60 分鐘

驗證：check_system_health("processing")
  → 確認 /health 返回 200
```

## 數據質量評分

```
100分 - 所有基金持倉完整 + NAV 正常 + 行情已更新
 80分 - 持倉完整但行情緩存過期
 60分 - 部分基金持倉缺失
  0分 - 所有基金持倉缺失（需緊急處理）
```
