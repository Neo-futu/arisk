# ARISK 平台技術架構說明

> ARISK — Agent for Risk & Investment Analysis System  
> 阿雷斯 · 智能風控和投資分析系統  
> 版本：1.0 · 2026-07-08

---

## 一、平台定位

ARISK 是面向香港認可貨幣市場基金（MMF）的**數據監控與風險分析平台**，核心場景：

- **SFC 第 8.2 章合規核查**：WAM / WAL / 流動性 / 集中度
- **每日風控快照**：VaR（三方法）/ 暴露分析 / 壓力測試
- **業績歸因**：Brinson-Fachler 模型 / NAV 偏差分析
- **報表自動化**：日報（xlsx）/ 月報 Factsheet（docx + pdf）
- **AI Agent 分析**：Chat 對話 + tool_use + 流式輸出

---

## 二、整體架構概覽

### 2.1 分層架構圖

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用戶交互入口                                   │
│                                                                       │
│   瀏覽器（Web）      Excel 插件        Python CLI                    │
│        ↓                 ↓                  ↓                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  frontend/          React 19 + Vite + shadcn/ui  :5173       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              ↓ JWT Bearer                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  backend/           FastAPI + SQLModel + Alembic  :8000       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              ↓ X-API-Key                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  6_entry/           入口路由層（Web / CLI / Excel）:8010      │   │
│  │    ├─ agent_v2.py   → aiagent/（Chat AI）                    │   │
│  │    └─ direct_query  → 2_processing（確定性查詢）             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────────┐   │
│  │  3_skills/   │  │   4_mcp/      │  │   aiagent/             │   │
│  │  能力技能庫  │  │  Wind MCP     │  │  AI 智能執行模塊       │   │
│  │  SKILL.md    │  │  內部 DB MCP  │  │  agents/ skills/ engine│   │
│  └──────────────┘  └───────────────┘  └────────────────────────┘   │
│                              ↓ HTTP                                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  2_processing/      FastAPI 計算引擎             :8001        │   │
│  │    ├─ tools/risk/   VaR / Exposure Engine                    │   │
│  │    ├─ tools/mmf/    報表生成腳本                              │   │
│  │    ├─ api/routers/  REST API                                  │   │
│  │    └─ workers/      Celery 定時任務                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              ↓ asyncpg / psycopg2                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  1_datastorage/     PostgreSQL · Redis · MinIO                │   │
│  │    PostgreSQL :5432  fsi schema（97 張表）+ iam schema        │   │
│  │    Redis      :6379  Celery Broker + 計算緩存                 │   │
│  │    MinIO      :9000  報表文件存儲                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 服務端口總覽

| 服務 | 端口 | 協議 | 說明 |
|---|---|---|---|
| `frontend` | 5173 | HTTP | Vite Dev Server（開發）/ Nginx（生產）|
| `backend` | 8000 | HTTP | FastAPI Web API + Swagger `/docs` |
| `6_entry` | 8010 | HTTP | 入口路由服務（內部）|
| `2_processing` | 8001 | HTTP | 業務計算 API（內部）|
| `PostgreSQL` | 5432 | TCP | 主數據庫 |
| `Redis` | 6379 | TCP | 緩存 + Celery |
| `MinIO` | 9000 / 9001 | HTTP | 對象存儲 / 管理台 |

---

## 三、各層技術棧詳解

### 3.1 數據持久層（1_datastorage/）

**PostgreSQL 16**
- 數據庫：`fsi_risk`
- Schema 分離：
  - `fsi` schema — 97 張業務表（ETL、持倉、計算結果）
  - `iam` schema — 認證表（user / item / role / menu，Alembic 管理）
  - `public` schema — 系統默認
- 連接方式：
  - 同步：`psycopg2`（ETL 腳本、report 腳本）
  - 異步：`asyncpg` via `SQLAlchemy[asyncio]`（FastAPI 服務）

**數據庫表三層架構：**
```
raw_*      原始入庫（7張）  ← ETL 零轉換，保留完整 JSONB
para_*     參數主數據（20張）← 基金、評級、風控限制配置
balance_*  持倉業務數據（16張）← 每日收盤後推送
mktdata_*  市場數據（20張）← 行情、評級、利率曲線
transact_* 交易記錄（13張）← 债券/存單/回購/申贖
svc_*      計算結果（10張）← 風控快照、合規、審核日誌
```

**Redis 7**
- Celery Broker（`redis://localhost:6379/1`）
- Celery Result Backend（`redis://localhost:6379/2`）
- 計算結果緩存（`redis://localhost:6379/0`）

**MinIO**
- 月報 Factsheet（PDF / Word）
- Excel 報表文件

---

### 3.2 業務計算層（2_processing/）

**FastAPI（異步）**  
端口：8001，供 `6_entry`、`backend`、`aiagent` 調用

**REST API 端點：**

| 前綴 | 功能 |
|---|---|
| `GET /positions/{fund_id}` | 持倉列表（支持資產類別過濾）|
| `GET /risk/exposure/{fund_id}` | 暴露分析 + SFC 合規狀態 |
| `GET /risk/var/{fund_id}` | VaR（historical / monte_carlo / distribution）|
| `GET /risk/var-compare/{fund_id}` | 三方法 VaR 並發對比 |
| `POST /reports/generate` | 觸發報表生成任務 |
| `GET /reports/tasks/{id}` | 任務進度查詢 |
| `GET /reports/download/{report_id}/{file}` | 報表文件下載 |
| `POST /schedules/` | 定時報表任務 CRUD |
| `POST /schedules/{id}/run-now` | 立即執行定時任務 |
| `GET /health` | 健康檢查 |

**計算引擎（tools/）：**
```
2_processing/tools/
├── risk/
│   ├── exposure_engine.py   暴露分析（WAM/WAL/DLA/WLA + SFC 合規核查）
│   └── var_calculator.py    VaR（歷史模擬法 + 蒙特卡洛 + 參數法）
├── performance/
│   └── attribution.py       Brinson-Fachler 業績歸因
└── mmf/
    ├── run_report.py         SQL → Excel 報表執行入口
    └── report_04/
        ├── run_monthly.py    月報一鍵生成（xlsx + json + pdf + docx）
        ├── extract_data.py   DB → outputdata.json
        ├── create_factsheet.py  → PDF
        ├── create_charts.py     → PNG 圖表
        └── create_word_report.py → Word
```

**Celery 定時任務：**

| 任務 | 觸發時間 | 說明 |
|---|---|---|
| `compute_daily_risk_snapshot` | T+1 07:00 | 全基金風控快照 |
| `run_exposure_check` | T+1 07:30 | 暴露 + 合規違規檢查 |
| `expire_stale_reviews` | 每小時 | 超時審核請求標記 |
| `etl_load_positions` | T+1 06:00 | 從估值系統 ETL 持倉 |

**認證：** `X-API-Key` Header（`PROCESSING_API_KEY`）

---

### 3.3 能力技能層（3_skills/）

面向 Claude Code IDE 和 Excel 插件的技能庫，採用與 `claude-risk-agent` 完全相同的格式。

```
3_skills/
├── skills/                   SKILL.md 技能定義
│   ├── risk-analysis/        風控分析（WAM/WAL/VaR/暴露）
│   ├── mmf-compliance/       MMF SFC 合規核查
│   ├── performance-report/   業績歸因
│   └── xlsx-report/          Excel 報表生成
└── commands/                 /slash 命令定義
    ├── risk.md               /risk [fund_id] [date]
    ├── compliance.md         /compliance [fund_id]
    └── var.md                /var [fund_id]
```

**觸發路徑：** Excel → Claude Code → `3_skills/` → `2_processing` API

---

### 3.4 數據連接層（4_mcp/）

基於 MCP（Model Context Protocol）協議連接外部數據源。

```
4_mcp/
├── wind/
│   └── wind_mcp_server.py   Wind API（行情 / 評級 / 利率曲線）
└── internal/
    └── internal_mcp_server.py  內部 Postgres 只讀查詢
```

**提供的 MCP 工具：**

| 工具 | 說明 |
|---|---|
| `wind_get_price` | 債券/基金歷史收盤價 |
| `wind_get_fx` | 外匯匯率 |
| `wind_get_bond_info` | 債券靜態信息（票息/評級/到期日）|
| `wind_get_yield_curve` | 收益率曲線（HIBOR/SHIBOR）|
| `db_get_holdings` | 內部持倉查詢 |
| `db_get_risk_snapshot` | 風控快照查詢 |
| `db_query_custom` | 自定義只讀 SQL |

**統一 MCP Gateway：** `http://localhost:8002/mcp`（Bearer Token 認證）

---

### 3.5 部署編排層（5_deploy/）

```
5_deploy/
├── agents/
│   ├── risk-agent/agent.yaml          風控 Agent 部署配置
│   │   └── subagents/
│   │       ├── data-puller.yaml       數據拉取子 Agent
│   │       ├── risk-calculator.yaml   計算子 Agent
│   │       └── report-writer.yaml     報告寫入子 Agent（唯一 Write 權限）
│   └── compliance-agent/agent.yaml   合規 Agent 部署配置
├── k8s/deployment.yaml               Kubernetes 部署清單
├── docker/Dockerfile.processing       2_processing 容器
└── orchestrate.py                     多 Agent 協調事件循環
```

**子 Agent 最小權限設計（來自 claude-risk-agent 模式）：**
```
data-puller    → 只讀（Read, Grep, MCP read-only）
risk-calculator → 計算（Read, Bash sandboxed）
report-writer  → 唯一可寫葉節點（Read, Write, Edit）
```

---

### 3.6 入口層（6_entry/）

```
6_entry/
├── web/
│   ├── app.py              FastAPI 應用（:8010）
│   └── routers/
│       ├── agent_v2.py     AI Agent V2（調用 aiagent/ 模塊）
│       ├── agent_mode.py   AI Agent V1（向後兼容）
│       ├── direct_query.py 確定性查詢（代理到 2_processing）
│       ├── review_ui.py    人工審核收件箱
│       └── op_logs_ui.py   操作日誌查看
├── cli/run.py              Python CLI（風控查詢 / ETL / 計算）
└── excel/bootstrap/        Excel 插件初始化命令
```

**入口分類：**
- **Web Chat**（`/agent/v2/stream`）→ aiagent/ → Claude API + 2_processing
- **直接查詢**（`/query/*`）→ 2_processing（確定性，低延遲）
- **CLI**（`python 6_entry/cli/run.py risk`）→ 2_processing
- **Excel**（`/bootstrap`）→ 3_skills + 4_mcp + 2_processing

---

### 3.7 Web API 閘道層（backend/）

**FastAPI + SQLModel + Alembic**，端口：8000

```
backend/
└── app/
    ├── core/
    │   ├── config.py      Pydantic Settings（讀取 .env）
    │   ├── db.py          SQLAlchemy 引擎（同步 psycopg）
    │   └── security.py    JWT（PyJWT）+ 密碼哈希（pwdlib argon2）
    ├── models.py          SQLModel 數據模型（iam schema）
    ├── crud.py            用戶 CRUD
    ├── api/
    │   ├── deps.py        依賴注入（DB Session / 當前用戶 / httpx 客戶端）
    │   └── routes/
    │       ├── login.py   OAuth2 密碼登錄 + JWT 簽發
    │       ├── users.py   用戶管理（CRUD）
    │       └── fsi/       FSI 業務代理路由
    │           ├── risk.py       → 2_processing /risk/*
    │           ├── positions.py  → 2_processing /positions/*
    │           ├── reports.py    → 2_processing /reports/*
    │           ├── schedules.py  → 2_processing /schedules/*
    │           └── agent.py      → 6_entry /agent/v2/*（含 SSE 透傳）
    └── alembic/           數據庫遷移（iam schema）
```

**認證流程：**
```
POST /api/v1/login/access-token
  → 驗證 email/password（Argon2 哈希）
  → 簽發 JWT（8 天有效期，HS256）
  → 前端存入 localStorage

後續請求：
  Authorization: Bearer <token>
  → get_current_user() 解碼 JWT
  → 查詢 iam.user 表驗證用戶狀態
```

---

### 3.8 Web UI 層（frontend/）

**React 19 + TypeScript + Vite + TanStack Router**，端口：5173（開發）

```
frontend/src/
├── routes/_layout/
│   ├── index.tsx        風控儀表板（WAM/WAL/合規卡片 + 資產配置）
│   ├── risk.tsx         VaR 三方法對比
│   ├── positions.tsx    持倉明細（TanStack Table）
│   ├── compliance.tsx   SFC 第 8.2 章逐條核查
│   ├── reports.tsx      報表生成（xlsx / docx / pdf 下載）
│   ├── schedules.tsx    定時報表任務管理
│   └── chat.tsx         AI Agent Chat（SSE 流式）
├── components/
│   ├── Sidebar/AppSidebar.tsx  側邊欄導航
│   ├── FsiToolbar.tsx          基金/日期/刷新工具欄
│   └── ui/                     shadcn/ui 組件庫（40+）
└── fsiClient.ts         FSI API 客戶端（axios + SSE fetch）
```

**UI 技術棧：**

| 技術 | 版本 | 用途 |
|---|---|---|
| React | 19.2 | UI 框架 |
| TypeScript | 5.9 | 類型安全 |
| Vite | 8.0 | 構建工具 |
| TanStack Router | 1.170 | 文件系統路由 |
| TanStack React Query | 5.101 | 服務端狀態管理 |
| shadcn/ui + Radix UI | latest | 組件庫 |
| Tailwind CSS | 4.2 | 樣式 |
| react-markdown + remark-gfm | 10.x | Markdown 渲染（Chat 頁面）|
| axios | 1.16 | HTTP 客戶端 |

**SSE 接收（Chat 頁面）：**
```typescript
// fetch + ReadableStream（不用 EventSource，支持 POST + body）
const response = await fetch('/api/v1/fsi/agent/v2/stream', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ messages, agent, context }),
})
const reader = response.body!.getReader()
// 逐塊解析 SSE 行 → 更新消息氣泡
```

---

### 3.9 AI Agent 模塊（aiagent/）

詳見 `docs/architecture_aiagent.md`。核心技術棧：

| 組件 | 技術 |
|---|---|
| AI 推理 | Anthropic Claude API（claude-sonnet-4-6）|
| Agent 定義 | Markdown frontmatter（同 claude-risk-agent）|
| 工具執行 | Python async + httpx → 2_processing |
| 流式輸出 | FastAPI StreamingResponse + SSE |
| 技能框架 | SKILL.md（同 claude-risk-agent 格式）|

---

## 四、數據流

### 4.1 Web 儀表板數據流（確定性查詢）

```
瀏覽器（/risk 頁面）
  → fetch GET /api/v1/fsi/risk/var-compare/BHMMF001?as_of_date=2026-06-25
  → backend:8000（JWT 驗證）
  → httpx GET processing:8001/risk/var-compare/BHMMF001
  → 2_processing/tools/risk/var_calculator.py
  → asyncpg → PostgreSQL fsi.balance_bond/cd/deposit...
  → 返回 JSON
  → React Query 緩存（staleTime: 0）→ 渲染 VaR 表格
```

### 4.2 AI Chat 數據流（流式 Agent）

```
瀏覽器（/chat 頁面）
  → fetch POST /api/v1/fsi/agent/v2/stream（SSE）
  → backend:8000（JWT 驗證）
  → httpx stream POST 6_entry:8010/agent/v2/stream（X-API-Key）
  → 6_entry/agent_v2.py
  → aiagent/engine/sse_generator()
  → aiagent/engine/runner.py
    ├── 載入 agents/risk-analyst.md（系統提示）
    ├── anthropic.messages.create(model, system, messages, tools)
    ├── tool_use → tools.py → httpx → processing:8001
    └── 返回 tool_result → 繼續循環（最多 10 輪）
  → SSE 事件流（text / tool_call / tool_result / done）
  → 瀏覽器 ReadableStream → Markdown 渲染
```

### 4.3 報表生成數據流（異步任務）

```
瀏覽器（/reports 頁面，點擊「生成報表」）
  → POST /api/v1/fsi/reports/generate
  → backend:8000 → processing:8001/reports/generate
  → ThreadPoolExecutor.submit(_run_report_sync)
    ├── subprocess.run(python run_report.py)  → report_04_mmf_monthly_*.xlsx
    ├── subprocess.run(python extract_data.py) → outputdata.json
    ├── subprocess.run(python create_charts.py) → PNG
    ├── subprocess.run(python create_factsheet.py) → PDF
    └── subprocess.run(python create_word_report.py) → docx
  → 複製到 artefacts/reports/{report_id}/
  ← 前端輪詢 GET /tasks/{id}（1.5s 間隔）
  ← 完成後顯示 XLSX / DOCX / PDF 三個下載按鈕
```

### 4.4 定時報表數據流（Scheduler）

```
aiagent/scripts/schedules.py（背景 daemon 線程）
  → 每分鐘整點檢查 artefacts/schedules.json
  → 匹配 hour/minute → 檢查 last_run_date（防重複）
  → _running_schedules 集合（防並發）
  → threading.Thread(_exec_report)
    → subprocess.run(run_report.py / run_monthly.py)
    → 輸出到 artefacts/scheduled/{schedule_id}/
  → _record_run() → 寫入 schedules_history.json
```

---

## 五、認證與安全架構

```
┌──────────────────────────────────────────────────────────┐
│  瀏覽器                                                   │
│  Authorization: Bearer <JWT>                             │
└───────────────────────────┬──────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│  backend/（認證邊界）                                       │
│  ├── JWT 解碼（PyJWT HS256，SECRET_KEY）                   │
│  ├── 查詢 iam.user（SQLModel）驗證 is_active               │
│  ├── CurrentUser = Annotated[User, Depends(get_current_user)]│
│  └── 代理請求到下游                                        │
└───────────┬─────────────────────────────────────────────┘
            ↓ X-API-Key: internal_key_change_me
┌───────────────────────────────────────────────────────────┐
│  6_entry / 2_processing（內部服務，不暴露外網）             │
│  只接受 X-API-Key 頭，不驗證 JWT                           │
└───────────────────────────────────────────────────────────┘
```

**密碼哈希：** pwdlib（Argon2 主 + BCrypt 降級）  
**JWT 有效期：** 8 天（`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 8`）  
**安全配置：** `.env` 中 `SECRET_KEY` 生產環境必須修改

---

## 六、雙軌校驗體系（Audit Trail）

符合 SFC 對「內部控制與清晰留痕」的審慎監管要求：

```
計算結果 / 報告發布
  ↓
小富 AI 審核員（ai_reviewer.py，Claude claude-sonnet-4-6）
  → 輸出：APPROVE / REJECT / ESCALATE / REQUIRE_HUMAN
  ↓（如觸發人工審核）
人工審核員（review_ui.py Web 界面）
  → 認領 → 批准 / 拒絕
  ↓
svc_wf_review_request / svc_wf_review_decision / svc_wf_audit_log
（寫入不可篡改審計日誌）
```

**審核觸發條件：**

| 觸發場景 | SLA |
|---|---|
| SFC 合規違規 | 30 分鐘 |
| VaR > NAV 5% | 30 分鐘 |
| 報告對外發布前 | 120 分鐘 |
| 批量數據寫入 | 60 分鐘 |

**全鏈路操作日誌：**  
所有 API 請求、計算任務、審核事件均寫入 `svc_sys_op_log`，供 SFC 現場檢查審閱。

---

## 七、開發環境啟動

### 7.1 前置條件（本機安裝，無需 Docker）

| 組件 | 版本 | 說明 |
|---|---|---|
| PostgreSQL | 16+ | 主數據庫 |
| Redis | 7+ | Celery broker |
| Python | 3.12+ | 後端 |
| uv | latest | Python 包管理 |
| Bun / Node | 20+ | 前端 |

### 7.2 首次初始化

```bash
# 1. 環境變量
cp .env.example .env   # 填入 SECRET_KEY / POSTGRES_PASSWORD

# 2. 建庫 + FSI Schema（97 張表）
python scripts/setup_db.py

# 3. Auth 表 + 超管用戶
cd backend && uv sync
alembic upgrade head           # 創建 iam schema 的 user/item/role 表
python -m app.initial_data     # 創建 admin@fsi.com 超管
cd ..

# 4. Processing API 依賴
pip install -r 2_processing/requirements.txt

# 5. 前端依賴
cd frontend && bun install && cd ..
```

### 7.3 日常啟動（一條命令）

```bash
python scripts/dev.py
```

啟動四個進程：

| 進程 | 端口 | 說明 |
|---|---|---|
| processing | 8001 | 計算引擎（uvicorn）|
| 6_entry | 8010 | 入口路由（uvicorn）|
| backend | 8000 | Web API（fastapi dev）|
| frontend | 5173 | React SPA（bun dev）|

### 7.4 訪問入口

| 地址 | 說明 |
|---|---|
| http://localhost:5173 | Web 前端（登錄：admin@fsi.com / changethis）|
| http://localhost:8000/docs | Backend API 文檔（含 /api/v1/fsi/* 路由）|
| http://localhost:8001/docs | Processing API 文檔（內部）|
| http://localhost:8010/docs | 6_entry API 文檔（內部）|

---

## 八、目錄結構索引

```
fsi-risk-platform/
├── 1_datastorage/         PostgreSQL schema + Redis + MinIO
│   └── postgres/schema/   001~011 SQL 文件（按序執行）
├── 2_processing/          業務計算引擎
│   ├── api/               FastAPI 路由（:8001）
│   ├── tools/             計算引擎（risk / performance / mmf）
│   ├── sql/mmf/           SQL 查詢文件 + 報表模板
│   └── workers/           Celery 定時任務
├── 3_skills/              Claude Code 技能庫
├── 4_mcp/                 Wind MCP + 內部 DB MCP
├── 5_deploy/              Agent 部署 + k8s
├── 6_entry/               入口路由層（:8010）
├── aiagent/               AI 智能執行模塊（橫切）
│   └── docs/architecture_aiagent.md  ← 架構詳解
├── backend/               Web API 閘道（:8000）
├── frontend/              React SPA（:5173）
├── artefacts/             生成物輸出
│   ├── reports/           按需報表
│   └── scheduled/         定時報表
├── scripts/               開發工具（setup_db / dev / check）
└── docs/
    ├── technical_architecture.md  ← 本文件
    └── architecture_aiagent.md    ← aiagent 架構詳解
```

---

## 九、關鍵技術選型說明

| 決策 | 選擇 | 原因 |
|---|---|---|
| Web 框架 | FastAPI | 異步、類型安全、自動 OpenAPI 文檔 |
| ORM | SQLModel（SQLAlchemy + Pydantic）| 統一模型定義，同時做 ORM 和 API schema |
| 認證 | JWT + pwdlib Argon2 | 現代密碼哈希（抗 GPU 暴力破解），無狀態 token |
| 前端路由 | TanStack Router（文件系統路由）| 類型安全路由，無魔法字符串 |
| 前端狀態 | TanStack React Query | 服務端狀態管理，無 Redux 複雜性 |
| UI 組件 | shadcn/ui + Radix UI | 可訪問性、可定制，非黑盒組件庫 |
| AI 框架 | Anthropic messages.create() + tools | 標準 tool_use，無需 beta Managed Agents |
| 流式輸出 | SSE over POST（fetch + ReadableStream）| 支持 POST body，比 WebSocket 更輕量 |
| 報表生成 | subprocess.run（隔離進程）| 隔離 Excel/PDF 庫崩潰，不影響 API 服務 |
| 任務調度 | 自實現（threading.Lock + 整分鐘對齊）| 無需 APScheduler 依賴，防雙觸三層設計 |
| 數據庫 Schema | fsi + iam 共存於同一實例 | 最小化基礎設施，邏輯隔離無物理分離 |
