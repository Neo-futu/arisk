# ARISK

六層核心架構 + 現代 Web 前後端的基金風控與業績分析平台，支援 Agent 模式與非 Agent 直接查詢模式。

## 項目架構（由下至上）

```
1_datastorage/     資料儲存層  — Postgres · TimescaleDB · Redis · S3
2_processing/      計算處理層  — ETL · 風控指標 · 業績分析 · FastAPI (port 8001)
3_skills/          能力技能層  — SKILL.md · commands · 共用 prompt 庫
4_mcp/             資料連接層  — WindAPI MCP · 內部 MCP gateway
5_deploy/          部署編排層  — agent.yaml · subagents · k8s · Docker
6_entry/           內部入口層 — Agent / Direct API · Excel · Python CLI（不再作為對外 Web 入口）
─────────────────────────────────────────────────────────────
backend/           Web API 層  — FastAPI + JWT 認證 + FSI 代理路由 (port 8000)
frontend/          唯一 Web UI 層 — React 19 + Vite + shadcn/ui（Dashboard + Chat）(port 5173/3000)
```

### 前後端分離架構

```
瀏覽器
  ↓ :3000 (Nginx) / :5173 (Vite dev)
frontend/          React SPA（儀表板 / 風控 / 持倉 / 合規 / 報表 / Chat）
  ↓ /api/v1/*  :8000
backend/           FastAPI（JWT 認證 + /api/v1/fsi/* 統一代理）
  ├── /api/v1/fsi/risk/*, /positions/* → :8001
  └── /api/v1/fsi/agent/*              → :8010
  ↓
6_entry/           內部入口服務（Agent / Direct / CLI / Excel）
  ↓
2_processing/      計算引擎 FastAPI（WAM/WAL/VaR/合規/持倉）
  ↓
1_datastorage/     PostgreSQL · Redis
```

### 數據庫共存
- `iam` schema：`backend/` Alembic 管理的身份與權限表（user / item / role / menu / permission）
- `fsi` schema：FSI 97 張業務表（SQL 腳本管理）
- 同一 PostgreSQL 實例（`fsi_risk` 數據庫），互不干擾

## 開發規則

### 編輯原則
- **前端 FSI 頁面**：`frontend/src/routes/_layout/`（risk / positions / compliance / reports / chat）
- **FSI API 調用**：`frontend/src/fsiClient.ts`（axios 封裝，JWT Bearer token）
- **後端 FSI 路由**：`backend/app/api/routes/fsi/`（代理到 processing:8001，需 JWT）
- **Agent 內部入口**：`6_entry/web/routers/`（由 backend 轉發，不直接給瀏覽器）
- **技能來源**：所有 SKILL.md 在 `3_skills/skills/` 修改，禁止直接改 agent bundle 副本
- **SQL 修改**：schema 變更走 `1_datastorage/postgres/migrations/`，不直接改 schema 文件
- **計算引擎**：`2_processing/tools/risk/` 和 `2_processing/tools/performance/`（不在 backend/）

### 前置條件（本機安裝，無需 Docker）

| 依賴 | 說明 | Windows 安裝 |
|---|---|---|
| PostgreSQL 16 | 主數據庫 | https://www.postgresql.org/download/windows/ |
| Redis 7 | Celery broker + 緩存 | https://github.com/tporadowski/redis/releases（Windows port） |
| Python 3.12+ | 後端 + Processing | https://python.org |
| uv | Python 包管理 | `pip install uv` |
| Bun 或 Node 20+ | 前端 | https://bun.sh |

### 首次初始化（只做一次）

```bash
# 1. 複製環境變量
copy .env.example .env        # Windows
# 編輯 .env，填入 POSTGRES_PASSWORD / SECRET_KEY

# 2. 建立數據庫、創建用戶、初始化 FSI Schema
python scripts/setup_db.py

# 3. 安裝 Python 依賴
cd backend && uv sync && cd ..
pip install -r 2_processing/requirements.txt   # Processing API 依賴

# 4. Alembic 遷移（auth 表）
cd backend
alembic upgrade head
python app/initial_data.py    # 創建超級用戶 admin@fsi.com
cd ..

# 5. 安裝前端依賴
cd frontend && bun install && cd ..
```

### 日常開發啟動（一條命令）

```bash
python scripts/dev.py
```

啟動後訪問：
- **前端**：http://localhost:5173
- **後端 API 文檔**：http://localhost:8000/docs（含 /api/v1/fsi/* 路由）
- **6_entry 內部入口**：http://localhost:8010/docs
- **Processing API 文檔**：http://localhost:8001/docs

### 環境設置
```bash
# .env 關鍵變量
SECRET_KEY=<隨機字符串>
FIRST_SUPERUSER=admin@fsi.com
FIRST_SUPERUSER_PASSWORD=<密碼>
POSTGRES_SERVER=localhost
POSTGRES_DB=fsi_risk
POSTGRES_USER=fsi_user
POSTGRES_PASSWORD=<密碼>
REDIS_URL=redis://localhost:6379/0
PROCESSING_API_URL=http://localhost:8001
ENTRY_API_URL=http://localhost:8010
```

## 層間職責邊界

| 層 | 讀 | 寫 | 觸發方 |
|---|---|---|---|
| datastorage | processing, skills(只讀查詢) | processing ETL workers | processing |
| processing | datastorage, 4_mcp | datastorage | backend / deploy |
| skills | 透過 MCP 讀 processing API | xlsx artefact（由 write-holder subagent） | agent / entry |
| mcp | 外部 API, 內部 DB | — | processing, skills |
| deploy | 3_skills, 5_deploy configs | — | CI/CD |
| backend | processing API、6_entry API（代理） | — | frontend / 外部 API |
| frontend | backend API (/api/v1/*) | — | 瀏覽器用戶 |

## 四大場景

1. **Web 儀表板 / Chat** → `frontend/` → `backend/api/v1/fsi/*` → `2_processing/api/` 或 `6_entry/web/routers/`
2. **Excel live** → `6_entry/excel/bootstrap` → `3_skills/` → `2_processing/api/`
3. **Python 腳本** → `6_entry/cli/run.py` → `2_processing/` → `1_datastorage/`
4. **Agent 模式** → `6_entry/web/routers/agent_mode.py` → `5_deploy/agents/`
