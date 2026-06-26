# 1_datastorage — 數據儲存層

## 模塊定位

FSI 風控業績平台六層架構的**第一層**，負責所有業務數據的持久化儲存。是整個平台的數據基礎，其他所有層（計算、技能、部署、入口）均從此層讀取或寫入數據。

```
6_entry  ←→  5_deploy  ←→  3_skills  ←→  4_mcp
                               ↓
                         2_processing
                               ↓
                      【1_datastorage】  ← 本層
```

---

## 目錄結構

```
1_datastorage/
├── docker-compose.yml          本地開發環境一鍵啟動（PG + TimescaleDB + Redis + MinIO）
├── postgres/
│   ├── schema/                 Schema 定義文件（11個，001-011順序執行）
│   │   ├── 001_schema_init.sql   fsi schema + 全局 ENUM 類型
│   │   ├── 002_raw.sql           L1 原始入庫表（raw_*）
│   │   ├── 003_para.sql          L2 參數主數據表（para_*）
│   │   ├── 004_balance.sql       L2 持倉數據表（balance_*）
│   │   ├── 005_mktdata.sql       L2 市場數據表（mktdata_*）
│   │   ├── 006_transact.sql      L2 交易記錄表（transact_*）
│   │   ├── 007_risk.sql          L3 風控結果表（svc_risk_*）
│   │   ├── 008_workflow.sql      L3 審核工作流表（svc_wf_*）
│   │   ├── 009_sys.sql           L3 系統日誌表（svc_sys_*）
│   │   ├── 010_index_counterparty.sql  指數成分/交易對手/可比組等補充表
│   │   └── 011_user_menu.sql     用戶/角色/菜單/查詢定義配置表
│   └── migrations/
│       └── migrate.py          版本管理腳本（冪等執行/狀態查詢）
├── redis/
│   └── redis.conf              Redis 配置（緩存 + Celery Broker）
├── timeseries/
│   └── hypertable_setup.sql    TimescaleDB 超表設置（時序數據優化）
└── object_store/
    └── bucket_policy.json      MinIO/S3 存儲桶策略（報告/artefact 存儲）
```

---

## 數據庫表三層架構

共 **97 張表**，按職責分三層，前綴即層別：

### Layer 1 — 原始數據層（`raw_*`，7張）
直接接收外部系統推送的原始數據，**零轉換**入庫。保留完整 JSONB payload，ETL 失敗可從此重跑。

| 表名 | 數據來源 |
|---|---|
| `raw_position` | 托管行 / 估值系統的持倉報表 |
| `raw_transaction` | 交易系統 / 券商流水 |
| `raw_price` | Wind / Bloomberg 行情推送 |
| `raw_fx_rate` | 匯率數據源 |
| `raw_nav` | 基金管理人 / 托管行確認 NAV |
| `raw_yield_curve` | 利率曲線（HIBOR / SHIBOR / SOFR） |
| `raw_etl_batch` | ETL 批次追蹤記錄 |

### Layer 2 — 業務數據層（46張）

清洗整合後的核心業務數據，無 FK 約束、無 Trigger，ETL 高速寫入。

**`para_*`（20張）— 參數主數據**
機構、人員、組合/基金、份額類別、基金經理、基準、風控限制（監管/內部/合同）、數據字典、可比組、交易對手、菜單/查詢配置、用戶角色權限。

**`balance_*`（16張）— 持倉數據**
每日收盤後估值系統推送。按資產類別獨立建表：
現金、定期存款、存款證（CD）、債券、股票、基金、期貨、期權、回購、養老金、估值資產負債表、組合 NAV 快照（含 WAM/WAL/偏差金額）、資產配置彙總、NAV 日變動、份額持有人摘要/排名。

**`mktdata_*`（20張）— 市場數據**
行情、評級、指數、匯率、利率曲線、基準利率（HIBOR/SHIBOR）、指數成分股/成分券、股息、基金 NAV、機構集團關係。

**`transact_*`（13張）— 交易記錄**
債券、股票、CD、存款、期貨、期權、回購（普通 + 銀行間）、基金申贖、投資者申贖、現金流水、個券損益、組合損益匯總。

### Layer 3 — 服務/結果層（`svc_*`，10張）
由 `2_processing` 計算引擎寫入，只讀查詢層。

| 表名 | 內容 |
|---|---|
| `svc_risk_snapshot` | 每日風控快照：WAM/WAL/VaR/DV01/集中度/合規狀態 |
| `svc_risk_exposure` | 暴露明細：按資產/發行人/評級/國家/行業維度 |
| `svc_risk_perf` | 業績指標：各期收益率/夏普/信息比率/最大回撤 |
| `svc_risk_alert_event` | 風控預警事件記錄 |
| `svc_monitor_excess_return` | 個券超額收益監控 |
| `svc_wf_review_request` | 人工審核請求（合規違規/高風險場景） |
| `svc_wf_review_decision` | 審核決策記錄 |
| `svc_wf_audit_log` | 不可篡改審計日誌 |
| `svc_wf_agent_checkpoint` | Agent 阻塞點記錄 |
| `svc_sys_op_log` | 全平台操作日誌 |

---

## 基礎設施組件

| 組件 | 用途 | 端口 |
|---|---|---|
| **PostgreSQL 16** | 主業務數據庫（fsi schema） | 5432 |
| **TimescaleDB** | 時序數據優化（市場行情歷史） | 5433 |
| **Redis 7** | 計算結果緩存 + Celery 任務隊列 | 6379 |
| **MinIO** | 報告文件 / Excel artefact 對象存儲 | 9000/9001 |

---

## 設計原則

1. **無 FK 約束、無 Trigger** — ETL 批量寫入高效，完整性由應用層保證
2. **前綴即層別** — `raw_/para_/balance_/mktdata_/transact_/svc_` 一眼識別
3. **每類資產獨立表** — `balance_bond` / `balance_stock` / `balance_cd` 各含資產特有字段，避免大量 NULL 列
4. **Generated Column** — `remaining_days` 自動計算，無需應用層維護
5. **JSONB 擴展** — `raw_data` / `extra_attrs` / `breach_details` 應對未來字段擴展
6. **WAM/WAL 放持倉層** — 與 NAV 同表（`balance_portfolio_nav`），對齊估值系統輸出，直接可讀

---

## 快速啟動

```bash
# 1. 啟動本地基礎設施
docker-compose -f 1_datastorage/docker-compose.yml up -d

# 2. 配置環境變量
cp .env.example .env  # 填入 POSTGRES_PASSWORD 等

# 3. 執行所有 Schema 遷移
python 1_datastorage/postgres/migrations/migrate.py

# 4. 查看遷移狀態
python 1_datastorage/postgres/migrations/migrate.py --status
```

---

## 層間職責邊界

| 操作 | 是否允許 |
|---|---|
| `2_processing` 讀取所有表 | ✅ |
| `2_processing` 寫入 `raw_` / `balance_` / `transact_` / `svc_` | ✅ |
| `3_skills` 只讀查詢 `svc_` / `mktdata_` | ✅ |
| `6_entry` 直接寫入業務表 | ❌（通過 `2_processing` API） |
| 直接修改 `schema/` 文件不走 `migrate.py` | ❌ |
