# FSI Risk Platform — 完整項目說明

> 版本：0.1.0 · 最後更新：2026-06-24

---

## 一、項目概述

FSI Risk Platform 是一個面向香港認可基金（以貨幣市場基金為核心場景）的風控與業績分析平台。平台採用六層架構，支援 **Claude Agent 模式**（複雜多步驟分析）與**非 Agent 直接查詢模式**（低延遲確定性計算），並內建雙軌審核體系（**小富 AI 審核 + 人工審核**）與全鏈路操作日誌。

### 適用場景
- 貨幣市場基金 SFC 守則第8.2章合規核查
- 每日風控快照（WAM/WAL/暴露/VaR/流動性）
- 業績歸因分析（BHB 模型）
- 持倉分析、集中度監控
- 合規報告生成與對外發布審核

---

## 二、六層架構總覽（由下至上）

```
┌─────────────────────────────────────────────────────────────────────┐
│  6_entry/         Excel · Python CLI · Web UI (FastAPI) · Direct API│
├─────────────────────────────────────────────────────────────────────┤
│  5_deploy/        Agent YAMLs · Subagents · Orchestrator · k8s     │
├─────────────────────────────────────────────────────────────────────┤
│  3_skills/        SKILL.md · Commands · Human-Review Skill          │
├─────────────────────────────────────────────────────────────────────┤
│  4_mcp/           WindAPI MCP · Internal DB MCP · Gateway           │
├─────────────────────────────────────────────────────────────────────┤
│  2_processing/    ETL · Risk Engine · Performance · Review · Logs   │
├─────────────────────────────────────────────────────────────────────┤
│  1_datastorage/   Postgres · TimescaleDB · Redis · S3 (MinIO)       │
└─────────────────────────────────────────────────────────────────────┘
```

### 層間職責邊界

| 層 | 讀 | 寫 | 觸發方 |
|---|---|---|---|
| 1_datastorage | 上層所有 | 2_processing ETL workers | 2_processing |
| 2_processing | 1_datastorage, 4_mcp | 1_datastorage | 6_entry, 5_deploy |
| 3_skills | 透過 MCP 讀 2_processing API（只讀） | xlsx artefact（由 write-holder subagent） | agent, 6_entry |
| 4_mcp | 外部 API (Wind), 1_datastorage | — | 2_processing, 3_skills |
| 5_deploy | 3_skills, 配置文件 | — | CI/CD, 6_entry |
| 6_entry | 2_processing API, 3_skills | — | 用戶 |

---

## 三、目錄詳解

### `1_datastorage/` — 資料儲存層

| 文件 | 說明 |
|---|---|
| `docker-compose.yml` | 本地開發：Postgres + TimescaleDB + Redis + MinIO 一鍵啟動 |
| `postgres/schema/001_funds.sql` | 基金/基準/份額類別主數據 |
| `postgres/schema/002_positions.sql` | 持倉快照 + 交易記錄（含 issuer_group 集中度字段） |
| `postgres/schema/003_market_data.sql` | 行情 / 匯率 / 利率 / NAV 歷史 |
| `postgres/schema/004_risk_results.sql` | 風控快照 + 暴露分解 + 業績計算結果 |
| `postgres/schema/005_review_workflow.sql` | **人工+AI 審核工作流**：review_requests（含 ai_* 字段）, review_decisions, audit_log, agent_checkpoints |
| `postgres/schema/006_op_logs.sql` | **操作日誌表**：全平台六層操作記錄 |
| `timeseries/hypertable_setup.sql` | TimescaleDB 日內行情 + NAV 實時序列（分區/壓縮策略） |
| `redis/redis.conf` | DB0=行情緩存(60s TTL), DB1/2=Celery, DB4=NAV緩存 |
| `object_store/bucket_policy.json` | S3/MinIO bucket 及前綴策略 |

### `2_processing/` — 計算處理層

| 模組 | 文件 | 說明 |
|---|---|---|
| ETL | `etl/fx_converter.py` | Redis緩存→DB→fallback 匯率換算 |
| ETL | `etl/load_positions.py` | CSV/Wind 持倉批量載入（觸發 DATA_LOAD 審核） |
| Risk | `risk/exposure_engine.py` | WAM/WAL/流動性/集中度計算 + SFC 守則合規判斷 |
| Risk | `risk/var_calculator.py` | 歷史模擬法 + 參數法 VaR / CVaR |
| Performance | `performance/attribution.py` | BHB 業績歸因（配置/選股/交互效應） |
| SQL | `sql/position_exposure.sql` | 持倉彙總 SQL（含 WAM/WAL/集中度合規判斷） |
| **Review** | `review/review_manager.py` | 創建審核請求，**自動觸發小富 AI 審核** |
| **Review** | `review/ai_reviewer.py` | **🤖 小富 AI 審核員**（Claude 驅動） |
| **Review** | `review/checkpoint.py` | agent 阻塞點（ReviewCheckpoint 上下文管理器） |
| **Logging** | `logging/op_logger.py` | 全平台結構化操作日誌（Postgres + structlog） |
| **Logging** | `logging/middleware.py` | FastAPI HTTP 請求自動日誌中間件 |
| API | `api/main.py` | Processing FastAPI 服務（port 8001）|
| API | `api/routers/positions.py` | /positions 端點 |
| API | `api/routers/risk.py` | /risk/exposure + /risk/var 端點 |
| API | `api/routers/review.py` | /review/* 審核端點（含 /ai-review, /ai-approve） |
| API | `api/routers/op_logs.py` | /op-logs/* 日誌查詢端點 |
| Workers | `workers/celery_app.py` | Celery 定時任務配置 |
| Workers | `workers/tasks.py` | 每日風控快照、行情緩存刷新、持倉載入 |

### `3_skills/` — 能力技能層

| 文件 | 說明 |
|---|---|
| `skills/risk-analysis/SKILL.md` | 風控分析完整流程（含 WAM/WAL/VaR/合規/審核觸發） |
| `skills/mmf-compliance/SKILL.md` | SFC 守則第8.2章逐條核查（含精確條款引用） |
| `skills/performance-report/SKILL.md` | 多期收益 + BHB 歸因輸出格式 |
| `skills/xlsx-report/SKILL.md` | xlsx 生成（write-holder 模式，審核後才能生成） |
| `skills/human-review/SKILL.md` | **人工審核技能**：審核觸發矩陣、阻塞等待協議 |
| `commands/risk.md` | `/risk` 命令定義 |
| `commands/compliance.md` | `/compliance` 命令定義 |

### `4_mcp/` — 資料連接層

| 文件 | 說明 |
|---|---|
| `.mcp.json` | wind + internal-db + fsi-gateway 三個 MCP 服務定義 |
| `wind/wind_mcp_server.py` | WindAPI MCP（含 mock，生產環境需安裝 WindPy） |
| `internal/internal_mcp_server.py` | Postgres 只讀 MCP（持倉/風控快照/NAV） |

### `5_deploy/` — 部署編排層

| 文件 | 說明 |
|---|---|
| `orchestrate.py` | **Orchestrator**：data-puller→risk-calculator→[審核①]→report-writer→[審核②] |
| `agents/risk-agent/agent.yaml` | orchestrator 配置（含 review_gates 審核觸發規則） |
| `agents/risk-agent/subagents/data-puller.yaml` | 只讀數據拉取，無寫權限 |
| `agents/risk-agent/subagents/risk-calculator.yaml` | 只讀計算，檢測到違規輸出 review_required=true |
| `agents/risk-agent/subagents/report-writer.yaml` | **write-holder**：唯一有寫入 artefacts/ 和 S3 權限 |
| `agents/compliance-agent/agent.yaml` | MMF 合規監控 Agent |
| `k8s/deployment.yaml` | processing-api + entry-web + celery-worker 三個 Deployment |
| `docker/Dockerfile.processing` | 處理層容器 |
| `scripts/deploy-agent.sh` | 一鍵部署 Managed Agent（含 subagents → orchestrator 順序） |

### `6_entry/` — 入口層

| 文件 | 說明 |
|---|---|
| `web/app.py` | FastAPI 統一入口（port 8000）：Agent + Direct + Review + Logs |
| `web/routers/agent_mode.py` | /agent/run（非同步）+ /agent/chat（同步小富對話） |
| `web/routers/direct_query.py` | /query/* 直接轉發 Processing API（低延遲） |
| `web/routers/review_ui.py` | /review-ui/* 審核收件箱（代理到 Processing API） |
| `web/routers/op_logs_ui.py` | /logs-ui/* 操作日誌查詢（代理到 Processing API） |
| `web/static/index.html` | 深色主題 Web UI（四 tab：儀表板/審核收件箱/操作日誌/AI助手） |
| `cli/run.py` | Python CLI：`python run.py risk BHMMF` / `positions` / `var` |
| `excel/bootstrap/bootstrap.md` | /bootstrap Excel 初始化命令 |

---

## 四、人工審核模組

### 設計原則

> **任何不可逆操作在執行前必須停止，等待審核批准。**

不可逆操作包括：寫入數據庫、發布報告、存在 SFC 守則違規時繼續、Agent 交接到 write-holder。

### 審核架構：雙軌並行

```
審核請求創建
    │
    ├─→ 🤖 小富 AI 審核（自動，後台非同步）
    │       • 分析風險等級 (LOW/MEDIUM/HIGH/CRITICAL)
    │       • 輸出建議 (APPROVE/REJECT/ESCALATE/REQUIRE_HUMAN)
    │       • 識別 SFC 守則條款引用
    │       • 給人工審核員提示
    │       └─→ 存入 review_requests.ai_review_result
    │
    └─→ 👤 人工審核（Web UI 收件箱）
            • 看到小富的分析作為參考
            • 做出最終決策：批准/拒絕
            • 可選：採納小富的自動批准建議
            └─→ Redis pub/sub 通知等待的 agent checkpoint
```

### 小富 AI 審核（`2_processing/review/ai_reviewer.py`）

**永遠需要人工的類別（小富不能自動批准）：**
- `COMPLIANCE_BREACH` — 任何 SFC 守則違規
- `HIGH_RISK` — VaR > 5% NAV 或 CVaR > 8%

**小富可建議自動批准的類別（仍需人工確認）：**
- `REPORT_PUBLISH`（無違規時）
- `DATA_LOAD`（常規持倉文件）
- `DATA_WRITE`（常規數據更新）

**小富 API 端點：**
```
GET  /review/{review_id}/ai-review   → 取小富分析結果
POST /review/{review_id}/ai-approve  → 執行小富自動批准（禁用於 COMPLIANCE_BREACH/HIGH_RISK）
```

### 審核觸發矩陣

| 場景 | 類別 | 優先級 | SLA | 強制 |
|---|---|---|---|---|
| WAM/WAL/集中度超守則 | COMPLIANCE_BREACH | 🔴 緊急 | 30分鐘 | ✅ |
| VaR > NAV 5% | HIGH_RISK | 🔴 緊急 | 30分鐘 | ✅ |
| 報告對外發布 | REPORT_PUBLISH | 🟡 正常 | 120分鐘 | ✅ |
| 批量持倉寫入 | DATA_WRITE | 🟡 正常 | 60分鐘 | ✅ |
| 新持倉文件載入 | DATA_LOAD | 🟡 正常 | 60分鐘 | ✅ |
| Agent 交接 | AGENT_HANDOFF | 🟡 正常 | 30分鐘 | ✅ |

### 審核阻塞點（Checkpoint）

審核請求由 `ReviewCheckpoint` 上下文管理器創建，agent 在此暫停：

```python
# 2_processing/review/checkpoint.py
async with ReviewCheckpoint(
    db, redis,
    category="COMPLIANCE_BREACH",
    title="WAM 超限：60.3天 > 60天上限",
    summary="...",
    triggered_by="risk-agent",
    fund_id="BHMMF",
    payload={"breach_flags": {"WAM_BREACH": True}},
) as approved:
    if approved:
        await write_risk_snapshot(...)   # 僅批准後執行
    else:
        logger.warning("Action blocked")
```

**Redis pub/sub 通知機制：**
- 頻道：`fsi:review:decision:{review_id}`
- 批准/拒絕時，`notify_decision()` 發布事件
- Checkpoint 訂閱頻道，收到通知後 yield approved

### 數據表

```sql
-- fsi.review_requests: 審核請求（含 ai_* 字段）
-- fsi.review_decisions: 每次批准/拒絕記錄
-- fsi.audit_log: 不可篡改審計日誌（append-only）
-- fsi.agent_checkpoints: agent 阻塞點記錄
```

---

## 五、操作日誌模組

### 設計目標

- 全鏈路覆蓋：六層的所有關鍵操作均有日誌
- 結構化存儲：Postgres + structlog JSON 文件雙寫
- 不阻塞主流程：日誌寫入失敗不影響業務操作
- 可查詢：支援多維度篩選（類別/級別/操作者/基金/耗時）

### 日誌類別

| 類別 | 說明 | 主要觸發方 |
|---|---|---|
| `API_ACCESS` | HTTP 請求/響應（中間件自動記錄） | LoggingMiddleware |
| `AGENT_ACTION` | Agent 執行步驟 | Orchestrator |
| `REVIEW_EVENT` | 審核流程（創建/小富分析/批准/拒絕） | review_manager |
| `ETL_JOB` | 持倉/市場數據載入 | load_positions, wind_etl |
| `RISK_CALC` | 風控計算（暴露/VaR） | exposure_engine, var_calculator |
| `PERF_CALC` | 業績計算（歸因） | attribution |
| `MCP_CALL` | Wind/內部 MCP 工具調用 | wind_mcp_server, internal_mcp_server |
| `AUTH` | 認證/授權事件 | API middleware |
| `DATA_WRITE` | 數據庫寫入操作 | ETL workers |
| `SCHEDULER` | Celery 定時任務 | celery workers |
| `SYSTEM` | 服務啟動/關閉/健康檢查 | app.py |

### 使用方式

```python
# 2_processing/logging/op_logger.py

# 1. 實例化（每個模組一個）
logger = OpLogger("risk-calculator", actor_type="agent")

# 2. 直接記錄
await logger.info(db, "compute_exposure",
    category="RISK_CALC", fund_id="BHMMF",
    detail="WAM=58.3天", extra={"wam": 58.3}
)

# 3. 計時器（自動記錄 duration_ms）
async with logger.timed(db, "load_positions", category="ETL_JOB", fund_id="BHMMF") as ctx:
    count = await _do_load(...)
    ctx.extra["loaded_rows"] = count

# 4. 快捷函數（無需實例化）
await log_event(db, "review_created", "REVIEW_EVENT", actor="orchestrator",
    fund_id="BHMMF", review_id=review_id)
```

### 查詢 API

```
GET /op-logs/?level=ERROR&category=REVIEW_EVENT&since=2026-06-24  → 篩選日誌
GET /op-logs/summary                                                → 彙總統計
GET /op-logs/slow-ops?threshold_ms=2000                            → 慢操作排查
```

### Web UI 日誌頁

位置：`6_entry/web/static/index.html` — 「操作日誌」tab

功能：
- 多維度篩選（級別/類別/操作者/基金/狀態/最小耗時）
- 分頁顯示（每頁 50 條）
- 日誌彙總統計（總數/錯誤數/警告數/平均耗時）
- 行顏色區分（ERROR=紅, WARNING=黃, 慢操作=橙）

---

## 六、Orchestrator 數據流

```
用戶請求 → orchestrate.py
               │
               ▼
    ① data-puller（只讀）
       ↓ 取持倉 + 市場數據
               │
               ▼
    ② risk-calculator（只讀計算）
       ↓ 計算 WAM/WAL/暴露/VaR
       ↓ 輸出 review_required=true/false
               │
               ▼
    [審核點 ①] breach_flags 非空？
       ├─→ 是：提交 COMPLIANCE_BREACH 審核
       │        小富自動分析 → 人工決策
       │        批准 → 繼續 │ 拒絕 → 中止
       └─→ 否：直接繼續
               │
               ▼
    ③ report-writer（write-holder）
       ↓ 生成 xlsx 報告
       ↓ 寫入 artefacts/
               │
               ▼
    [審核點 ②] 報告發布前
       ├─→ 提交 REPORT_PUBLISH 審核
       │        小富自動分析 → 人工確認
       │        批准 → 上傳 S3 公開鏈接
       └─→ 拒絕 → 報告保留但不發布
               │
               ▼
    完成：返回 artefact_url + task_log
```

---

## 七、四大入口場景

### 1. Excel Live

```
/bootstrap                     → 偵測可用 MCP/skills
/risk BHMMF                    → 觸發 risk-analysis SKILL
                               → 調用 Processing API
                               → 輸出到 Excel 工作表
```

### 2. Python CLI

```bash
python 6_entry/cli/run.py risk BHMMF          # 風控快照
python 6_entry/cli/run.py positions BHMMF     # 持倉列表
python 6_entry/cli/run.py var BHMMF --confidence 0.99
```

### 3. Web UI + AI 助手（小富）

```
瀏覽器 http://localhost:8000
  ├─ 儀表板 tab    → /query/risk/exposure/BHMMF
  ├─ 審核收件箱 tab → /review-ui/inbox + 小富分析
  ├─ 操作日誌 tab  → /logs-ui/?category=REVIEW_EVENT
  └─ AI 助手 tab   → /agent/chat（小富對話）
```

### 4. Agent 模式 vs Direct Query

```python
# Agent 模式：複雜分析，多步驟，有審核點
POST /agent/run  {"task": "生成本月風控報告", "fund_id": "BHMMF"}
→ 返回 task_id，輪詢 /agent/status/{task_id}

# Direct Query：低延遲，確定性計算，無審核
GET /query/risk/exposure/BHMMF?as_of_date=2026-06-24  # <200ms
GET /query/risk/var/BHMMF?confidence=0.99
```

---

## 八、快速啟動

```bash
# 1. 環境設置
cd /d/vsproject/fsi-risk-platform
cp .env.example .env          # 填入 DB/WindAPI/Anthropic key

# 2. 啟動數據庫
docker-compose -f 1_datastorage/docker-compose.yml up -d

# 3. 初始化 schema
psql -U fsi_user -d fsi_risk -f 1_datastorage/postgres/schema/001_funds.sql
# ... 依序 002-006

# 4. 安裝依賴
pip install -e ".[dev]"

# 5. 啟動 Processing API（port 8001）
uvicorn 2_processing.api.main:app --reload --port 8001

# 6. 啟動 Celery Worker
celery -A 2_processing.workers.celery_app worker --loglevel=info

# 7. 啟動 MCP Gateway
python -m 4_mcp.wind.wind_mcp_server &
python -m 4_mcp.internal.internal_mcp_server &

# 8. 啟動 Web UI（port 8000）
uvicorn 6_entry.web.app:app --reload --port 8000

# 9. 瀏覽器打開
open http://localhost:8000
```

---

## 九、開發規範

### 技能來源
所有 SKILL.md 在 `3_skills/skills/` 修改，禁止直接改 agent bundle 副本。

### DB 變更
Schema 變更走 `1_datastorage/postgres/migrations/`，不直接改 schema 文件。

### 審核原則
- `COMPLIANCE_BREACH`/`HIGH_RISK`：必須人工審核，任何代碼不得繞過
- 小富建議僅為參考，`ai_auto_approved=True` 記錄仍需人工點擊確認
- `audit_log` 表 append-only，任何應用層代碼禁止執行 DELETE/UPDATE

### 日誌原則
- 日誌寫入失敗不得拋出異常（try/except 靜默處理）
- 敏感數據（API key、密碼）不得寫入日誌
- `actor` 字段必填，區分 human/agent/system

### 運行檢查
```bash
python scripts/check.py        # lint + 跨層引用驗證
python scripts/sync_skills.py  # 同步 skills 到 agent bundle
```

---

## 十、API 端點速查

### Processing API（port 8001，內部，需 X-API-Key）

```
GET  /health
GET  /positions/{fund_id}?as_of_date=          持倉列表
GET  /positions/{fund_id}/summary?as_of_date=  持倉彙總
GET  /risk/exposure/{fund_id}?as_of_date=      暴露分析（含合規）
GET  /risk/var/{fund_id}?as_of_date=           VaR 計算
POST /review/request                           提交審核請求
GET  /review/pending                           待審核列表
GET  /review/{id}                              審核詳情
POST /review/{id}/claim                        認領
POST /review/{id}/approve                      批准
POST /review/{id}/reject                       拒絕
GET  /review/{id}/ai-review                    小富 AI 分析
POST /review/{id}/ai-approve                   採納小富批准
GET  /review/history/audit-log                 審計日誌
GET  /op-logs/                                 操作日誌查詢
GET  /op-logs/summary                          日誌統計
GET  /op-logs/slow-ops                         慢操作
```

### Web Entry（port 8000，外部）

```
POST /agent/run                AgentTask 非同步
GET  /agent/status/{task_id}   任務狀態
POST /agent/chat               小富同步對話
GET  /query/risk/exposure/{id} Direct 暴露查詢
GET  /query/risk/var/{id}      Direct VaR 查詢
GET  /query/positions/{id}     Direct 持倉查詢
GET  /review-ui/inbox          審核收件箱
GET  /review-ui/inbox/{id}     審核詳情
POST /review-ui/inbox/{id}/approve  批准
POST /review-ui/inbox/{id}/reject   拒絕
POST /review-ui/inbox/{id}/ai-approve 採納小富
GET  /review-ui/audit-log      審計日誌
GET  /logs-ui/                 日誌查詢
GET  /logs-ui/summary          日誌統計
GET  /logs-ui/slow-ops         慢操作
GET  /health
```

---

*本文檔由 Claude 自動生成並持續維護。如有架構變更，請同步更新此文件。*
