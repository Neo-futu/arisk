<!-- 更新时间：2026-09-01（北京时间）｜生成模型：GPT-5.6 Sol -->

# 2_processing — 計算處理層

## 模塊定位

FSI 風控業績平台六層架構的**第二層**，是平台的**計算核心**。負責從 `1_datastorage` 讀取原始數據，執行 ETL 清洗、風控計算、業績歸因等業務邏輯，並將結果寫回數據庫或通過 API 提供給上層。

```
6_entry  ←→  3_skills  ←→  4_mcp
                ↓
         【2_processing】  ← 本層
          ETL | 計算 | API | 任務調度
                ↓
          1_datastorage
```

---

## 目錄結構

```
2_processing/
├── api/                    FastAPI 內部計算服務
│   ├── main.py               應用入口，路由注冊
│   ├── deps.py               依賴注入（DB Session / API Key 驗證）
│   └── routers/
│       ├── data_management.py 數據管理 CRUD、模擬交易與前置風控
│       ├── indicators.py     指標探索（DataJungle）：目錄/對比時序/CSV導出/可編輯維護
│       ├── portfolio_cockpit.py 組合列表與駕駛艙：基本盤/MMF指標/狀態/sparkline（只讀）
│       ├── portfolio_opt.py   組合優化：PyPortfolioOpt 有效前沿/BL/HRP + PNG 圖表（tools/performance/portfolio_optimizer.py）
│       ├── positions.py      持倉查詢接口
│       ├── sql_assets.py     SQL 資產庫：sql/{indicators,mmf} 目錄/正文/AI 上下文（查看用）
│       ├── valuation.py      組合估值報表 + NAV 階段損益歸因（只讀計算）
│       ├── risk.py           風控指標接口
│       ├── performance.py    業績歸因接口
│       ├── review.py         人工審核工作流接口
│       └── op_logs.py        操作日誌接口
├── etl/                    數據清洗與載入
│   ├── load_positions.py     持倉 ETL（Wind / CSV → balance_* 表）
│   └── fx_converter.py       多幣種匯率換算（→ 基幣 HKD）
├── risk/                   風控計算引擎
│   ├── exposure_engine.py    暴露分析（SFC MMF 守則合規計算）
│   └── var_calculator.py     VaR 計算（歷史模擬法 + 參數法）
├── performance/            業績分析
│   └── attribution.py        收益歸因（Brinson 行業/個股效應）
├── review/                 人工審核工作流
│   ├── review_manager.py     審核請求管理（創建/查詢/決策）
│   ├── checkpoint.py         Agent 阻塞點（pre_db_write 等）
│   └── ai_reviewer.py        小富 AI 審核員（Claude 驅動）
├── workers/                Celery 異步任務
│   ├── celery_app.py         Celery 應用配置
│   └── tasks.py              定時任務定義（每日風控計算）
├── logging/                操作日誌
│   ├── op_logger.py          結構化日誌記錄（→ svc_sys_op_log）
│   └── middleware.py         FastAPI 請求日誌中間件
├── tools/                  業務邏輯 Python 工具（計算引擎 / 報表生成）
│   ├── risk/
│   │   ├── exposure_engine.py    暴露分析 + SFC MMF 合規計算
│   │   └── var_calculator.py     VaR / CVaR（歷史模擬法 + 參數法）
│   ├── performance/
│   │   └── attribution.py        Brinson 收益歸因（配置/選股/交互效應）
│   ├── internal/
│   │   └── sql_queries.py        內部查詢 SQL 統一註冊（供 4_mcp 調用）
│   └── mmf/
│       ├── run_report.py         MMF 報表總執行入口（SQL→Excel）
│       ├── report_03/
│       │   └── create_template.py   日報 XLSX 模版生成器
│       └── report_04/
│           ├── run_monthly.py        月報一鍵入口（XLSX+JSON+PDF+Word）
│           ├── create_template.py    月報 XLSX 模版生成器
│           ├── extract_data.py       DB → outputdata.json
│           ├── create_factsheet.py   outputdata.json → PDF
│           ├── create_charts.py      outputdata.json → PNG 圖表
│           ├── create_word_template.py  Word 模版生成器
│           └── create_word_report.py    outputdata.json+PNG → Word
└── sql/                    SQL 查詢文件（純查詢，不含 Python）
    └── mmf/
        ├── report_03/        日報 xlsm（含 Wind 公式）
        ├── report_03_mmf/    日報 xlsx（SFC 合規版）
        ├── report_04_mmf_monthly/  月報數據（SQL + 佈局 JSON + 模版）
        ├── report_06/        特定基金詳細分析
        └── output/           生成輸出文件
```

---

## 子模塊功能說明

### `api/` — FastAPI 內部計算服務

**對外接口**（供 `6_entry` 和 Agent 調用，不直接暴露外網）：

| 路由前綴 | 功能 |
|---|---|
| `GET/POST/PATCH/DELETE /data-management/*` | 估值持倉與行情 CRUD、模擬交易、確定性前置風控；寫入同步追加審計事件 |
| `GET /positions/*` | 持倉查詢：按組合/資產類別/日期查詢當日持倉 |
| `GET /risk/*` | 風控指標：WAM/WAL/流動性/集中度/VaR/暴露明細 |
| `GET /performance/*` | 業績歸因：收益貢獻/行業歸因/個券損益 |
| `GET /investment/overview/*` | 投資風險分析：組合業績/資產配置/前十大個股/行業配置 |
| `GET /investment/risk-indicators/*` | 確定性指標：區間收益/波動率/最大回撤/股票換手率/Beta |
| `GET /investment/attribution/*` | 績效歸因：資產貢獻/Brinson/超配/個股損益/日均重倉 |
| `POST /review/*` | 審核工作流：創建/認領/批准/拒絕審核請求 |
| `GET /op-logs/*` | 操作日誌查詢 |
| `GET /health` | 健康檢查 |

認證：`X-API-Key` Header，對應 `PROCESSING_API_KEY` 環境變量。

> 投資風險分析的所有固定公式和 SQL 計算均在 `2_processing/tools/performance/`
> 實現；`backend/` 只負責 JWT/用戶 API Key 認證與反向代理，`frontend/` 只展示結果。

---

### `etl/` — 數據清洗與載入

**`load_positions.py`**
- 從 Wind MCP 或 CSV 文件讀取原始持倉數據
- 清洗：代碼映射（Wind → 內部 ID）、異常值過濾
- 幣種換算：調用 `fx_converter` 折算為基幣 HKD
- 寫入 `raw_position`（L1）→ 清洗後寫入 `balance_*`（L2）
- 冪等：按 `source_txn_id` 去重，支持重跑

**`fx_converter.py`**
- 從 `mktdata_fx_rate` 取當日匯率
- 支持多幣種（HKD/USD/CNY/EUR/GBP）→ 基幣換算
- 處理缺失匯率的 fallback（前一日 / 固定匯率）

---

### `risk/` — 風控計算引擎

**`exposure_engine.py`** — 暴露分析
核心是 SFC《單位信託及互惠基金守則》第 8.2 章的 MMF 合規計算：

```python
# 內置 SFC MMF 守則閾值
WAM_LIMIT      = 60天    # 加權平均期限上限
WAL_LIMIT      = 120天   # 加權平均有效期上限
DAILY_LIQ_MIN  = 7.5%    # 每日流動資產下限
WEEKLY_LIQ_MIN = 15.0%   # 每週流動資產下限
SINGLE_ENTITY  = 10.0%   # 單一發行人上限（一般）
GROUP_LIMIT    = 20.0%   # 集團敞口上限
```

計算流程：
1. 從 `balance_*` 表讀取當日持倉
2. 計算各維度暴露（資產類別/發行人/評級/國家/到期日段）
3. 驗證所有合規閾值
4. 返回 `ExposureResult`，違規項目記錄到 `breach_flags`
5. 寫入 `svc_risk_exposure` + `svc_risk_snapshot`

**`var_calculator.py`** — VaR 計算

| 方法 | 說明 |
|---|---|
| 歷史模擬法 | 使用過去 252 個交易日的日收益率分佈 |
| 參數法 | 假設正態分佈，用均值/標準差計算 |

輸出：1天/10天，95%/99% 置信度的 VaR 及 CVaR（條件VaR）。

---

### `performance/` — 業績分析

**`attribution.py`** — Brinson 歸因模型

計算三效應分解：
- **配置效應**：行業超配/低配帶來的超額收益
- **選股效應**：在行業內選股優劣帶來的超額收益
- **交互效應**：兩者疊加

數據源：
- 組合持倉 → `balance_stock`
- 基準成分 → `mktdata_index_component`
- 個券收益 → `transact_pnl_item`

---

### `review/` — 人工審核工作流

**`review_manager.py`**
- 創建審核請求（觸發方：計算引擎 / Agent / 用戶）
- 支持審核狀態機：`PENDING → IN_REVIEW → APPROVED / REJECTED / EXPIRED`
- 超時自動設為 `EXPIRED`（由 Celery beat 定期掃描）

**`checkpoint.py`** — Agent 阻塞點
Agent 執行關鍵操作前（如批量寫入DB / 發布報告）在此暫停，等待審核通過才繼續。

```python
# 典型使用場景
await checkpoint.block(
    agent_name="risk_agent",
    checkpoint="pre_db_write",
    blocked_action="批量更新 balance_bond 持倉數據"
)
```

**`ai_reviewer.py`** — 小富 AI 審核員
- 由 Claude claude-sonnet-4-6 驅動
- 自動分析每個審核請求，提供結構化風險評估
- 輸出：`APPROVE / REJECT / ESCALATE / REQUIRE_HUMAN`
- **設計原則**：合規違規 / 高風險場景永遠建議人工審核，小富是建議者而非決策者

---

### `workers/` — Celery 異步任務調度

**主要定時任務：**

| 任務 | 觸發時間 | 說明 |
|---|---|---|
| `compute_daily_risk_snapshot` | 每個交易日 T+1 07:00 | 計算所有組合的每日風控快照 |
| `run_exposure_check` | 每個交易日 T+1 07:30 | 暴露分析 + 合規違規檢查 |
| `expire_stale_reviews` | 每小時 | 將超時審核請求標記為 EXPIRED |
| `etl_load_positions` | 每個交易日 T+1 06:00 | 從估值系統 ETL 持倉數據 |

Broker：Redis（`CELERY_BROKER_URL`）
Result Backend：Redis（`CELERY_RESULT_BACKEND`）

---

### `logging/` — 操作日誌

**`op_logger.py`**
結構化日誌記錄，寫入 `svc_sys_op_log` 表，覆蓋：
- API 請求/響應（耗時、狀態碼）
- 計算任務執行（開始/完成/失敗）
- 審核事件
- ETL 操作

**`middleware.py`**
FastAPI 中間件，自動為每個請求記錄：請求路徑、方法、耗時、狀態碼、用戶信息。

---

## 與其他層的交互

| 方向 | 交互說明 |
|---|---|
| **← `1_datastorage`** | 讀取 `balance_*` / `mktdata_*` / `transact_*` 等業務表 |
| **→ `1_datastorage`** | 寫入 `svc_risk_*` / `svc_wf_*` / `svc_sys_*` 計算結果 |
| **← `4_mcp`** | 通過 WindAPI MCP 獲取市場數據 |
| **→ `6_entry`** | 通過 REST API 提供計算結果（`PROCESSING_API_URL`） |
| **→ `3_skills`** | 技能層調用計算 API 獲取數據後執行業務邏輯 |

---

## 快速啟動

```bash
# 1. 確保 1_datastorage 服務已啟動
docker-compose -f 1_datastorage/docker-compose.yml up -d

# 2. 安裝依賴
pip install -e ".[dev]"

# 3. 啟動 FastAPI 計算服務
uvicorn 2_processing.api.main:app --host 0.0.0.0 --port 8001 --reload

# 4. 啟動 Celery Worker
celery -A 2_processing.workers.celery_app worker --loglevel=info

# 5. 啟動 Celery Beat（定時任務）
celery -A 2_processing.workers.celery_app beat --loglevel=info
```

**API 文檔**：啟動後訪問 `http://localhost:8001/docs`

---

## 環境變量

| 變量 | 說明 |
|---|---|
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | 數據庫連接 |
| `REDIS_URL` | Redis 連接（Celery Broker） |
| `PROCESSING_API_KEY` | 內部 API 認證密鑰 |
| `ANTHROPIC_API_KEY` | Claude API（小富 AI 審核員） |
| `ANTHROPIC_MODEL` | 默認 `claude-sonnet-4-6` |
| `MCP_GATEWAY_PORT` | MCP Gateway 端口（WindAPI） |
