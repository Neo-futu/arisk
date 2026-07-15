# ARISK — Agent for Risk & Investment Analysis System

**阿雷斯 · 智能風控和投資分析系統**

面向香港認可基金（以貨幣市場基金為核心場景）的數據監控與風險分析平台，採用「分層能力平台 + 統一前後端產品入口」架構，支援 Web、Chat、Agent 模式與直接查詢模式。

版本：1.0.0 · 更新：2026-07-07

## 架構總覽

詳細整合架構與目錄責任說明見：`docs/integrated_architecture.md`

本地統一啟動、端口與依賴說明見：`docs/local_development_stack.md`

```
瀏覽器
	↓
frontend/        唯一 Web 入口（Dashboard + Chat）
	↓ /api/v1/*
backend/         統一 API / JWT / FSI 代理
	├── /api/v1/fsi/risk|positions      → 2_processing
	└── /api/v1/fsi/agent/*             → 6_entry
	↓
6_entry/         內部入口服務（Agent / Direct / CLI / Excel）
	↓
5_deploy/        Agent 編排
4_mcp/           MCP 工具層
2_processing/    計算與 SQL 核心
1_datastorage/   PostgreSQL / Redis / S3
```

## 平台分層設計策略

ARISK 採用「上層負責體驗與編排、下層負責計算與取數」的分層方式，目標是把 UI、認證、Agent 編排、技能知識、資料連接、業務計算、資料儲存拆開，避免互相耦合。

核心原則：

- **唯一前端入口**：`frontend/` 是唯一對使用者開放的 Web 入口。
- **統一後端收口**：`backend/` 負責 JWT、權限與 API 代理，不直接承擔業務計算。
- **Agent 執行入口獨立**：`6_entry/` 負責 LLM 對話、tool_use 循環與內部直查，不直接對外暴露成主產品 Web。
- **技能與知識分離**：`3_skills/` 存放可被索引的技能與命令，是知識資產層，不是長駐服務。
- **資料連接與業務邏輯分離**：`4_mcp/` 只負責外部/內部資料連接，不做業務判斷。
- **計算與查詢確定化**：`2_processing/` 承擔風控計算、業績分析、SQL 核心查詢。
- **儲存層獨立**：`1_datastorage/` 只管 PostgreSQL / Redis / S3 等底層資源。

## 各子文件夾作用

| 目錄 | 作用 | 目的 |
|---|---|---|
| `1_datastorage/` | PostgreSQL / Redis / S3 / migrations / docker-compose | 提供所有資料與快取基礎設施 |
| `2_processing/` | FastAPI 計算核心、風控指標、業績分析、Celery workers | 提供確定性業務計算與查詢結果 |
| `3_skills/` | SKILL.md 技能庫、commands、agents、prompts | 提供可索引的業務知識與技能資產 |
| `4_mcp/` | Wind MCP、Internal MCP、MCP Gateway、client | 提供統一資料連接入口，屏蔽底層來源差異 |
| `5_deploy/` | Agent 編排、部署腳本、k8s、Docker、subagents | 提供部署與多 Agent 編排配置 |
| `6_entry/` | Agent / Direct / CLI / Excel 內部入口 | 提供 LLM 執行與內部調用入口 |
| `backend/` | JWT、RBAC、統一 API、FSI 代理路由 | 提供對外收口與安全邊界 |
| `frontend/` | React SPA（Dashboard + Chat） | 提供唯一瀏覽器 UI |
| `aiagent/` | 用戶層業務 AI 的執行與知識模塊 | 處理 Chat Agent 的對話、工具與記憶 |
| `platform_agent/` | 系統層業務 AI 的執行與運維模塊 | 處理自動運維、排程與平台級流程 |

## 分層邊界

- `frontend/` 只呼叫 `backend/`。
- `backend/` 只代理到 `6_entry/` 或 `2_processing/`。
- `6_entry/` 透過工具層與 `2_processing/`、`4_mcp/`、`3_skills/` 協作。
- `3_skills/` 只保存技能與命令，不承擔 UI 或長駐服務。
- `4_mcp/` 只做資料連接，不實作業務策略。
- `platform_agent/` 與 `aiagent/` 是兩套不同的 agent runtime，目標不同、入口不同。

## 快速開始

### 1. 環境設置

```bash
git clone <repo>
cd arisk
cp .env.example .env            # 填入 DB, WindAPI, Anthropic key
pip install -e ".[dev]"
```

### 2. 啟動資料庫

```bash
docker-compose -f 1_datastorage/docker-compose.yml up -d
python 1_datastorage/postgres/migrations/init_db.py
```

### 3. 啟動 Processing API

```bash
uvicorn 2_processing.api.main:app --reload --port 8001
```

### 4. 啟動 MCP Gateway

```bash
python 4_mcp/gateway/mcp_gateway.py
```

### 5. 啟動內部 Entry 服務

```bash
uvicorn 6_entry.web.app:app --reload --port 8010
```

### 6. 啟動對外 Backend + Frontend

```bash
cd backend
uv sync
fastapi dev app/main.py --port 8000

cd ../frontend
npm install
npm run dev
```

## 目錄說明

| 目錄 | 層 | 說明 |
|---|---|---|
| `1_datastorage/` | 資料儲存 | Postgres schema、TimescaleDB、Redis、S3 bucket policy、docker-compose |
| `2_processing/` | 計算處理 | ETL、風控引擎（VaR/暴露/壓測）、業績歸因、FastAPI + Celery workers |
| `3_skills/` | 能力技能 | SKILL.md 技能庫、slash commands、共用 prompt 模板、Claude plugin 配置 |
| `4_mcp/` | 資料連接 | WindAPI MCP server、內部數據 MCP、統一 MCP gateway |
| `5_deploy/` | 部署編排 | Managed-agent YAMLs、subagent 定義、k8s manifests、Docker、部署腳本 |
| `6_entry/` | 內部入口 | Agent / Direct API、Excel bootstrap、Python CLI runner，不再作為對外 Web 入口 |
| `backend/` | 對外後端 | FastAPI + JWT + FSI 代理路由，統一暴露 /api/v1/* |
| `frontend/` | 唯一 Web 前端 | React SPA，承擔儀表板、風控頁與 Chat 工作台 |

## 支援場景

### Agent 模式（複雜分析，多步驟推理）

```python
# Browser → frontend → backend → 6_entry
POST /api/v1/fsi/agent/run  {"task": "生成本月風險報告", "fund_id": "BHMMF"}
```

### 非 Agent 直接查詢（低延遲，確定性計算）

```python
# Browser → frontend → backend → 2_processing
GET /api/v1/fsi/risk/var/BHMMF?as_of_date=2026-06-24&confidence=0.99
GET /api/v1/fsi/positions/BHMMF?as_of_date=2026-06-24
```

### Python CLI

```bash
python 6_entry/cli/run.py --task risk_report --fund BHMMF --date 2026-06-24
```

### Excel Add-in

```
/bootstrap          # 自動偵測可用 MCP/skills，載入 Excel 環境
/risk               # 在 Excel 中生成風險分析
/positions          # 列出持倉
```

## 技能 (Skills) 參考

| 技能 | Command | 說明 |
|---|---|---|
| `risk-analysis` | `/risk` | VaR、暴露分析、壓力測試 |
| `performance-report` | `/performance` | 業績歸因、基準比較 |
| `position-review` | `/positions` | 持倉明細、集中度 |
| `mmf-compliance` | `/compliance` | 貨幣市場基金合規檢查（SFC 第8.2章） |
| `xlsx-report` | — | 生成 xlsx 報表（headless） |

## MCP 連接器

| 連接器 | 說明 |
|---|---|
| WindAPI | 市場行情、財務數據、指數成分 |
| Internal DB | 持倉、交易記錄、計算結果 |
| Redis Cache | 實時行情緩存、計算中間結果 |

## 部署

```bash
# 部署 Risk Agent
bash 5_deploy/scripts/deploy-agent.sh risk-agent

# k8s 部署
kubectl apply -f 5_deploy/k8s/
```
