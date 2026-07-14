# platform_agent — 系統層業務 AI

**定位**：ARISK 平台的**系統層業務 AI**，自動化運行平台的核心業務流程，
無需人工干預：ETL 數據載入、日終風控快照、合規監控、報表生成。

> **三層業務 AI 的位置**：
> - **Platform Agent（本模塊）：系統層業務 AI（自動運維）** ← 你在這裡
> - 3_skills：專家級業務技能（領域知識編碼）
> - aiagent：用戶層業務 AI（個人對話助理）
> - 4_mcp：外部 / 內部數據連接層（統一取數入口）

---

## 系統能自動做什麼

```
每日 09:00 → ETL 協調員啟動
  → load_daily_positions（持倉數據載入）
  → 驗證數據完整性
  → 數據質量評分

每日 18:30 → 系統調度員啟動
  → compute_daily_risk_snapshot（風控快照計算）
  → AI 異常檢測（WAM/WAL 接近閾值告警）
  → 自動觸發合規監控報告
  → 生成 MMF 日報（report_03_mmf）

每小時 → refresh_price_cache（行情緩存更新）

實時 → 系統監控員值守
  → 服務健康檢查
  → 數據異常識別
  → 合規預警推送
```

---

## 五層架構

```
+------------------------------------------------------------------+
| L1: 控制與規劃層 (Brain)                                           |
|  業務規則引擎：VaR/WAM/WAL 確定性計算                              |
|  AI 決策層：任務協調、異常識別、告警判斷                             |
|  Agent 角色：scheduler / monitor / etl-coordinator               |
|  文件：platform_agent/agents/ + engine/platform_runner.py         |
+------------------------------------------------------------------+
| L2: 記憶與知識層 (Memory)                                          |
|  業務數據庫：fsi schema 97 張業務表（持倉/快照/合規/報表）           |
|  時序數據：TimescaleDB（NAV歷史、VaR趨勢）                          |
|  操作緩存：Redis DB0（行情緩存）+ DB1/DB2（Celery 隊列/結果）        |
|  業務技能知識：通過 knowledge_search 查詢 3_skills（同一知識庫）     |
|  外部/內部取數：通過 4_mcp/gateway 連 Wind 與 internal-db            |
|  文件：1_datastorage/ + 2_processing/api/deps.py                  |
+------------------------------------------------------------------+
| L3: 工具與技能層 (Tools + Skills)                                  |
|  系統運維工具（9個）：                                              |
|    trigger_celery_task / get_task_status / check_system_health   |
|    query_business_db / trigger_report / get_queue_stats           |
|    scaffold_system_tool / scaffold_system_skill / scaffold_agent  |
|  knowledge_search：查詢 3_skills 業務技能知識                      |
|  4_mcp：外部行情 / 內部只讀資料 / 標準化 Gateway                   |
|  系統運維技能：platform_agent/skills/（操作手冊）                   |
|  文件：platform_agent/engine/system_tools.py                      |
+------------------------------------------------------------------+
| L4: 外部 / 內部連接層 (MCP / Data Connector)                       |
|  4_mcp/wind       — 外部行情 / 財務 / 指數 / 評級                   |
|  4_mcp/internal   — 內部只讀資料 / 快照 / 持倉 / NAV               |
|  4_mcp/gateway    — 統一 MCP 入口                                   |
+------------------------------------------------------------------+
| L5: 編排與通訊層 (Orchestration)                                   |
|  Celery Beat：定時任務調度（ETL/快照/行情）                         |
|  Redis：任務隊列 + 結果存儲 + 狀態緩存                              |
|  服務網格：processing:8001 → entry:8010 → backend:8000            |
|  SSE 端點：6_entry:8010/platform/v1/stream                        |
|  文件：2_processing/workers/ + 6_entry/web/routers/platform_v1.py|
+------------------------------------------------------------------+
```

---

## 三個系統 Agent 角色

### scheduler（系統調度員）
管理 Celery 任務依賴和執行順序。

```
18:25 check_system_health → 所有服務正常
18:30 trigger_celery_task("compute_daily_risk_snapshot")
18:45 get_task_status → SUCCESS
18:46 trigger_celery_task("run_ai_anomaly_detection", fund_id=BHMMF001)
19:00 trigger_report("report_03_mmf", BHMMF001, today)
```

### monitor（系統監控員）
監控服務健康、數據完整性、合規狀態。

```
check_system_health("all") → 服務狀態報告
query_business_db("SELECT ... FROM fsi.risk_snapshots WHERE ...") → 合規核查
knowledge_search("SFC WAM WAL 閾值") → 從 3_skills 獲取合規判斷依據
```

### etl-coordinator（ETL 協調員）
管理數據載入流程和質量驗證。

```
trigger_celery_task("load_daily_positions")
query_business_db("SELECT fund_id, COUNT(*) FROM fsi.positions WHERE ...") → 驗證
```

---

## 工具清單（10個）

### 系統運維工具
| 工具 | 說明 |
|------|------|
| `trigger_celery_task` | 觸發業務任務（快照/ETL/AI異常檢測） |
| `get_task_status` | 查詢任務執行狀態 |
| `check_system_health` | 服務健康檢查 |
| `query_business_db` | 只讀查詢業務數據 |
| `trigger_report` | 觸發報表生成 |
| `get_queue_stats` | Celery 隊列統計 |
| `knowledge_search` | 查詢 3_skills 業務技能知識（合規閾值等） |

### 系統擴展工具（開發者使用）
| 工具 | 生成目標 |
|------|---------|
| `scaffold_system_tool` | 生成新業務工具代碼模板 → aiagent/engine/tools.py |
| `scaffold_system_skill` | 生成新技能 SKILL.md → 3_skills/ 或 aiagent/skills/ |
| `scaffold_agent_role` | 生成新 Agent 角色提示模板 |

---

## 技能目錄

`platform_agent/skills/` 是系統運維操作手冊（不是知識庫，不索引）：

| 技能 | 說明 |
|------|------|
| `daily-risk-ops` | 每日風控快照的完整執行順序 |
| `etl-ops` | ETL 數據載入和驗證流程 |
| `compliance-monitor` | 合規監控執行步驟 |

**注意**：這些是 Platform Agent 的操作手冊（Private），
`3_skills/skills/` 才是公共的專家業務技能（被索引入知識庫，兩層 AI 都能查）。

## MCP 的意義

Platform Agent 需要的是「穩定取數」而不是自己直連所有資料源，因此 4_mcp 應被視為這一層的標準連接器：

- 外部資料：Wind / 行情 / 財務 / 指數 / 評級
- 內部資料：只讀業務查詢、風控快照、持倉、NAV 歷史
- 業務推理：仍由 Platform Agent + skills 負責

這樣可以把資料存取、業務邏輯和策略判斷分開，避免 Agent 直接綁死在資料庫或第三方 SDK 上。

## 原來的編排層在哪裡

如果你說的是這份文件原本的編排層，它現在對應的是 L5，核心入口在 `6_entry/web/routers/platform_v1.py`，執行鏈會落到 `platform_agent/engine/platform_runner.py` 和 Celery 調度流程。

## 新增：platform_agent 獨立編排模塊

為了與 aiagent 解耦，platform_agent 現在具備自己的 orchestrator：

- `platform_agent/orchestrator/supervisor.py`
  - 調度 `scheduler / monitor / etl-coordinator`
  - 支持多階段鏈式流程（例如日終 EOD）
- `platform_agent/orchestrator/task_state.py`
  - Redis 任務狀態機（prefix: `arisk:platform_task`）
- `platform_agent/engine/stream.py`
  - SSE 編排封裝，通過 supervisor 調度 `run_platform_agent`

`/platform/v1/stream` 已改為使用 `platform_sse_generator`，
因此 platform 的編排邏輯不再直接混在 router 內。

---

## 啟動方式

```bash
# 啟動計算引擎（Platform Agent 工具的後端）
python scripts/dev.py --parts processing entry backend frontend

# 啟動 Celery Worker（Platform Agent 任務執行引擎）
celery -A 2_processing.workers.celery_app worker --loglevel=info

# 啟動 Celery Beat（Platform Agent 定時調度）
celery -A 2_processing.workers.celery_app beat --loglevel=info

# 通過 SSE API 使用 Platform Agent
curl -X POST http://localhost:8010/platform/v1/stream \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"觸發今日風控快照計算"}],"agent":"scheduler"}'
```
