# ARISK Local Development Stack

本文檔提供一份類似 `full-stack-fastapi-template` 的本地啟動總覽，覆蓋以下部分：

- `frontend/`
- `backend/`
- `6_entry/`
- `4_mcp/`
- `3_skills/`
- `2_processing/`

目標是讓本地啟動順序、端口、依賴和每層角色一次講清楚。

## 1. 本地拓撲

```text
Browser
  ↓ http://localhost:5173
frontend/              唯一 Web UI
  ↓ /api/v1/*
backend/               對外 API / JWT / FSI 代理
  ├── → 2_processing/  http://localhost:8001
  └── → 6_entry/       http://localhost:8010

6_entry/               內部入口（Agent / Direct / CLI / Excel）
4_mcp/                 MCP 工具層（stdio client-activated）
3_skills/              Skill / Prompt 資產層（無常駐進程）
2_processing/          計算與 SQL 核心
1_datastorage/         PostgreSQL / Redis / S3
```

## 2. 服務矩陣

| 層 / 目錄 | 是否常駐進程 | 推薦端口 | 主要責任 | 直接依賴 |
|---|---|---:|---|---|
| `frontend/` | 是 | `5173` | Dashboard + Chat，唯一 Web UI | Node 或 Bun，`backend/` |
| `backend/` | 是 | `8000` | JWT、BFF、對外 API 代理 | Python、`2_processing/`、`6_entry/` |
| `6_entry/` | 是 | `8010` | 內部 Agent / Direct 入口、CLI、Excel | Python、`2_processing/` |
| `2_processing/` | 是 | `8001` | 風控計算、SQL、報表生成核心 | PostgreSQL、Redis |
| `4_mcp/internal` | 可選 | stdio | 內部 DB MCP 工具 | Python、PostgreSQL |
| `4_mcp/wind` | 可選 | stdio | Wind MCP 工具 | Python、Wind 憑證 |
| `3_skills/` | 否 | - | Skill / Prompt / commands 資產 | 無 |

## 3. 依賴前置

### 基礎服務

- PostgreSQL 已啟動，且可訪問 FSI schema
- Redis 已啟動（Celery / cache 使用）

### Python

- Python 3.12+
- 建議已安裝根目錄依賴：

```bash
pip install -e ".[dev]"
```

### Backend

- `backend/` 使用 `uv` 管理依賴：

```bash
cd backend
uv sync
```

### Frontend

- Node 20+ 或 Bun
- 推薦命令：

```bash
cd frontend
npm install
```

## 4. 啟動順序

推薦順序如下：

1. `1_datastorage/`：先保證 PostgreSQL / Redis 可用
2. `2_processing/`：先起計算核心，其他層都依賴它
3. `6_entry/`：起內部入口服務，承接 Agent / Direct
4. `backend/`：起對外 API，代理到 processing / entry
5. `frontend/`：起唯一 Web UI
6. `4_mcp/`：按需啟動 internal / wind MCP 工具
7. `3_skills/`：無需啟動，只要檔案存在即可被 Agent / tooling 使用

## 5. 一鍵啟動

使用：

```bash
python scripts/dev.py
```

### Profile

```bash
python scripts/dev.py --profile web
```

啟動：

- `2_processing` on `8001`
- `6_entry` on `8010`
- `backend` on `8000`
- `frontend` on `5173`

```bash
python scripts/dev.py --profile agent
```

啟動：

- `2_processing`
- `6_entry`

```bash
python scripts/dev.py --profile full
```

啟動：

- `2_processing`
- `6_entry`
- `backend`
- `frontend`
- `4_mcp/internal`
- `4_mcp/wind`

### 常用選項

```bash
python scripts/dev.py --no-frontend
python scripts/dev.py --with-internal-mcp
python scripts/dev.py --with-wind-mcp
python scripts/dev.py --only processing
python scripts/dev.py --parts processing backend frontend
python scripts/dev.py --list-parts
python scripts/dev.py --dry-run --profile full
```

### PowerShell 包裝腳本（Windows）

```powershell
./scripts/dev.ps1 -Profile web
./scripts/dev.ps1 -Profile full -WithInternalMcp -WithWindMcp
./scripts/dev.ps1 -Only backend
./scripts/dev.ps1 -Parts processing,backend,frontend
./scripts/dev.ps1 -ListParts
./scripts/dev.ps1 -DryRun -Profile full
```

## 6. 手動啟動命令

### 2_processing

```powershell
$env:DATABASE_URL='postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk'
$env:PROCESSING_API_KEY='internal_key_change_me'
uvicorn 2_processing.api.main:app --host 127.0.0.1 --port 8001 --reload
```

### 6_entry

```powershell
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'
uvicorn 6_entry.web.app:app --host 127.0.0.1 --port 8010 --reload
```

### backend

```powershell
$env:ENTRY_API_URL='http://127.0.0.1:8010'
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'
cd backend
fastapi dev app/main.py --host 127.0.0.1 --port 8000
```

### frontend

```powershell
cd frontend
npm install
npm run dev
```

## 6.1 前後端單獨啟動步驟

### Frontend only

```powershell
cd frontend
npm install
npm run dev
```

### Backend only

```powershell
$env:ENTRY_API_URL='http://127.0.0.1:8010'
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'
cd backend
uv sync
fastapi dev app/main.py --host 127.0.0.1 --port 8000
```

### internal MCP

```powershell
$env:DATABASE_URL='postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk'
python 4_mcp/internal/internal_mcp_server.py
```

### wind MCP

```powershell
$env:WIND_USERNAME='<your-user>'
$env:WIND_PASSWORD='<your-password>'
python 4_mcp/wind/wind_mcp_server.py
```

## 7. 層與層之間怎麼配合

### Web 產品鏈路

```text
frontend -> backend -> 2_processing
frontend -> backend -> 6_entry
```

### Agent / Direct 內部鏈路

```text
6_entry -> 2_processing
5_deploy -> 2_processing / 4_mcp / 3_skills
```

### MCP 鏈路

```text
Agent / tools -> 4_mcp/internal
Agent / tools -> 4_mcp/wind
```

## 7.1 各層作用、運行入口與腳本

| 層 | 作用 | 主要運行入口 | 推薦啟動腳本 / 命令 |
|---|---|---|---|
| `frontend` | 唯一 Web UI（dashboard + chat） | `frontend/src/main.tsx` | `python scripts/dev.py --profile web` 或 `npm run dev` |
| `backend` | 對外 API、JWT、FSI 代理 | `backend/app/main.py` | `python scripts/dev.py --profile web` 或 `fastapi dev app/main.py` |
| `6_entry` | 內部 Agent / Direct API、CLI、Excel 入口 | `6_entry/web/app.py` | `python scripts/dev.py --profile agent` 或 `uvicorn 6_entry.web.app:app --port 8010` |
| `5_deploy` | Agent 編排、審核閘門 | `5_deploy/orchestrate.py` | `python 5_deploy/orchestrate.py <fund> <date> --risk-only` |
| `4_mcp/internal` | 內部 DB MCP 工具 | `4_mcp/internal/internal_mcp_server.py` | `python scripts/dev.py --with-internal-mcp` |
| `4_mcp/wind` | Wind MCP 工具 | `4_mcp/wind/wind_mcp_server.py` | `python scripts/dev.py --with-wind-mcp` |
| `3_skills` | skills/prompts/commands 資產 | `3_skills/skills/*/SKILL.md` | 無常駐進程，按需被 agent/tooling 載入 |
| `2_processing` | 計算與 SQL 核心 | `2_processing/api/main.py` | `python scripts/dev.py --profile agent` 或 `uvicorn 2_processing.api.main:app --port 8001` |

## 8. 關於 3_skills

`3_skills/` 不是本地開發時要單獨啟動的服務。它是：

- `SKILL.md`
- `commands/*.md`
- prompt 資產

也就是說，它屬於「能力資產層」，不是「常駐進程層」。

## 9. 推薦本地工作流

### 只做 Web 頁面 / API 開發

```bash
python scripts/dev.py --profile web
```

### 做 Agent / Direct 整合

```bash
python scripts/dev.py --profile agent
```

### 做 MCP 能力驗證

```bash
python scripts/dev.py --profile agent --with-internal-mcp --with-wind-mcp
```

## 10. 常見問題

### frontend 起不來

- 先在 `frontend/` 執行 `npm install`
- 若使用 Bun，確認 `bun` 在 PATH 中

### backend 起不來

- 確認 `backend/` 已 `uv sync`
- 確認 `.env` 中 JWT / DB 設定完整

### 6_entry 或 processing 起不來

- 先確認 PostgreSQL 可連
- 再確認 `DATABASE_URL` / `PROCESSING_API_KEY` 一致

### MCP 沒有對外 HTTP 端口

- 目前 `4_mcp` 以 stdio MCP server 為主，通常由 Claude / Agent / 客戶端按需拉起
- 因此在本地它屬於「可選工具進程」，不是 Web 必需服務