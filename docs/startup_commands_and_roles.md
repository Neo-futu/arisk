# FSI Local Startup Commands And Roles

本文件整理本地開發環境的服務架構、啟動命令、各層職責與常見操作。

---

## 1. 服務與端口對照

| 服務 | 端口 | 角色 | 說明 |
|---|---:|---|---|
| 2_processing | 8001 | 計算核心 | 風控計算、VaR、持倉與 SQL 核心 API |
| 6_entry | 8010 | Agent 入口 | SSE 流式 Chat、多模型 LLM、工具調用循環 |
| backend | 8000 | 對外後端 | JWT 認證、統一 API、代理到 processing / entry |
| frontend | 5173 | 對外前端 | 唯一 Web UI（Dashboard + Chat） |

---

## 2. 6_entry 是什麼？為什麼不能省略？

`6_entry`（port 8010）是平台的 **AI Agent 執行引擎入口**，以下場景**缺少它就無法工作**：

### 2.1 Chat 頁面完整請求鏈

```
瀏覽器 /chat
  → frontend:5173
  → POST /api/v1/fsi/agent/v2/stream → backend:8000  (JWT 認證)
  → POST /agent/v2/stream            → 6_entry:8010  ← 必須運行
      ↓ aiagent/engine/runner.py
      ├── 調用 LLM（Anthropic / Grok / Qwen 等）
      └── 執行工具 → GET /risk/var-compare/ → processing:8001
```

**沒有 6_entry**：Chat 發送後 backend 拋出 `httpx.ConnectError`，前端顯示錯誤。

### 2.2 6_entry 承擔的職責

| 路由前綴 | 文件 | 功能 |
|---|---|---|
| `/agent/v2/stream` | `routers/agent_v2.py` | SSE 流式 chat，完整 tool_use 循環（**Chat 頁面主入口**） |
| `/agent/v2/models` | `routers/agent_v2.py` | 返回支持的 LLM 列表（Anthropic / Grok / Qwen 等） |
| `/agent/v2/agents` | `routers/agent_v2.py` | 返回可用 Agent 列表（風控分析師 / 合規審查員等） |
| `/agent/v2/chat` | `routers/agent_v2.py` | 非流式同步 chat（≤30s 快速問答） |
| `/query/risk/*` | `routers/direct_query.py` | 直接查詢 processing（低延遲，跳過 LLM） |
| `/review-ui/*` | `routers/review_ui.py` | 人工審核收件箱 |
| `/logs-ui/*` | `routers/op_logs_ui.py` | 操作日誌查看器 |

### 2.3 6_entry 與 backend 的分工

- **backend** 負責：用戶認證（JWT）、對外 API 收口、把請求代理轉發給 6_entry
- **6_entry** 負責：實際 LLM 調用、tool_use 工具執行循環、SSE 流式輸出

---

## 3. 推薦啟動方式

### 3.1 一鍵啟動（推薦，自動包含所有服務）

```bash
# 默認 web profile = processing + entry + backend + frontend
python scripts/dev.py
```

```powershell
# PowerShell
./scripts/dev.ps1 -Profile web
```

啟動後訪問：
- **前端 UI**：http://localhost:5173
- **Backend API 文檔**：http://localhost:8000/docs
- **6_entry API 文檔**：http://localhost:8010/docs
- **Processing API 文檔**：http://localhost:8001/docs

### 3.2 Profile 參數說明

| Profile | 包含服務 | 適用場景 |
|---|---|---|
| `web`（默認） | processing + **entry** + backend + frontend | 日常前後端開發 |
| `agent` | processing + **entry** | 只調試 Agent/LLM，不啟前端 |
| `full` | web + mcp-gateway + internal-mcp + wind-mcp | 含 MCP Gateway + Wind 行情接入的完整環境 |

### 3.3 常用腳本參數

```bash
# 列出所有可用 parts 和 profiles
python scripts/dev.py --list-parts

# 啟動完整 web 環境（含 entry，推薦）
python scripts/dev.py --parts processing entry backend frontend

# 僅調試 Agent 不啟前端
python scripts/dev.py --profile agent

# 跳過 6_entry（僅風控計算，Chat 功能不可用）
python scripts/dev.py --parts processing backend frontend --no-entry

# 乾跑：只打印計劃，不真正啟動
python scripts/dev.py --parts processing entry backend frontend --dry-run

# 啟動完整環境 + Wind MCP
python scripts/dev.py --profile full --with-wind-mcp

# 統一啟動 MCP 全套（gateway + internal + wind）
python scripts/dev.py --profile web --with-mcp

# 只加 MCP Gateway（AI 調用先走統一入口）
python scripts/dev.py --profile web --with-mcp-gateway

# 另外啟動 AutoRisk 模塊（端口 8100）
python scripts/dev.py --profile web --with-autorisk
```

```powershell
# PowerShell 版本
./scripts/dev.ps1 -Profile web
./scripts/dev.ps1 -Parts processing,entry,backend,frontend
./scripts/dev.ps1 -Profile web -WithMcp
./scripts/dev.ps1 -Profile web -WithMcpGateway
./scripts/dev.ps1 -Only entry
./scripts/dev.ps1 -Parts processing,backend,frontend -DryRun
```

### 3.3.1 AutoRisk 模塊啟動（前端 /autorisk 入口需要）

平台前端頁面中的「自動風控」入口會調用 AutoRisk 的演示與後端服務（預設端口 8100）。
dev.py 已原生支持 autorisk 模組，可直接納入統一調度管理。

1. 包含 AutoRisk 的完整啟動

# 啟動基礎服務 + AutoRisk 模組
```
python scripts/dev.py --parts processing entry backend frontend autorisk
```

2. 單獨啟動 AutoRisk 服務
若基礎服務已在運行，僅需補啟動或調試 AutoRisk 模組：
```Bash
python scripts/dev.py --parts autorisk
```
提示：可執行 python scripts/dev.py --list-parts 查看所有可用的模組列表，或加上 --dry-run 參數預覽啟動計劃。

3. 服務驗證與存取點
啟動成功後，可透過以下位址進行驗證：

前端整合入口：http://localhost:5173/autorisk

AutoRisk 演示頁：http://localhost:8100/demo

AutoRisk API 文檔：http://localhost:8100/docs

排查：若前端點擊演示頁無響應，請先確認 dev.py 輸出日誌中 autorisk 服務是否正常起飛，或檢查本地 8100 端口是否被其他程序佔用。


### 3.4 AI 命令與 MCP 使用建議

```bash
# AI 日常（不強制 Gateway）：MCP client 會 stdio fallback
python scripts/dev.py --profile web

# AI + 統一 MCP 入口（推薦調試）
python scripts/dev.py --profile web --with-mcp-gateway

# AI + MCP 全套（Gateway + internal + wind）
python scripts/dev.py --profile web --with-mcp
```

當啟動 `mcp-gateway` 時，本地應有：

- `MCP_GATEWAY_URL=http://127.0.0.1:8002`
- 健康檢查：`http://127.0.0.1:8002/health`
- 工具列表：`http://127.0.0.1:8002/tools`

---

## 4. 手動分步啟動（調試用）

### 4.1 2_processing（8001）

```powershell
Set-Location "d:\vsproject\fsi-risk-platform"
$env:DATABASE_URL='postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk'
$env:PROCESSING_API_KEY='internal_key_change_me'
uvicorn 2_processing.api.main:app --host 127.0.0.1 --port 8001 --reload
```

作用：啟動風控計算核心 API，為 6_entry 和 backend 提供 VaR/WAM/WAL/持倉數據。

### 4.2 6_entry（8010）⚠️ Chat 功能必需

```powershell
Set-Location "d:\vsproject\fsi-risk-platform"
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'
$env:ANTHROPIC_API_KEY='sk-ant-...'
$env:OPENROUTER_API_KEY='sk-or-v1-...'   # xAI Grok 用
uvicorn 6_entry.web.app:app --host 127.0.0.1 --port 8010 --reload
```

作用：啟動 Agent 執行引擎，承接 LLM 對話請求（SSE 流式 + tool_use），調用 processing 工具。

### 4.3 backend（8000）

```powershell
Set-Location "d:\vsproject\fsi-risk-platform\backend"
$env:ENTRY_API_URL='http://127.0.0.1:8010'
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

作用：對外統一 API，處理 JWT 認證，將前端請求代理到 6_entry / processing。

### 4.4 frontend（5173）

```powershell
Set-Location "d:\vsproject\fsi-risk-platform\frontend"
bun run dev
# 或
npm run dev
```

作用：啟動唯一 Web UI（Vite 開發服務），訪問 http://localhost:5173。

### 4.5 MCP Gateway（8002，可選但推薦）

```powershell
Set-Location "d:\vsproject\fsi-risk-platform"
$env:MCP_GATEWAY_PORT='8002'
$env:MCP_GATEWAY_URL='http://127.0.0.1:8002'
python -m 4_mcp.gateway.mcp_gateway
```

作用：統一 MCP HTTP 入口，AI 工具調用可先走 gateway，再由 gateway 路由到 internal/wind。

### 4.6 internal MCP（stdio）

```powershell
Set-Location "d:\vsproject\fsi-risk-platform"
$env:DATABASE_URL='postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk'
python 4_mcp/internal/internal_mcp_server.py
```

作用：提供內部只讀工具（fund list / positions / nav / risk snapshot / query_business_db）。

### 4.7 wind MCP（stdio）

```powershell
Set-Location "d:\vsproject\fsi-risk-platform"
$env:WIND_USERNAME='your_wind_user'
$env:WIND_PASSWORD='your_wind_password'
python 4_mcp/wind/wind_mcp_server.py
```

作用：提供 Wind 行情、指數、評級等外部工具。

---

## 5. 端口占用清理

```powershell
# 查找佔用端口的進程（以 8010 為例）
Get-NetTCPConnection -LocalPort 8010 -State Listen
Stop-Process -Id <pid> -Force

# 批量清理四個端口
@(8001, 8010, 8000, 5173) | ForEach-Object {
    $conn = Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Write-Host "Killed port $_" }
}
```

---

## 6. 驗證端點

```bash
# 計算核心
curl http://127.0.0.1:8001/docs

# Agent 入口
curl http://127.0.0.1:8010/docs
curl http://127.0.0.1:8010/agent/v2/models    # 返回支持的 LLM 列表
curl http://127.0.0.1:8010/agent/v2/agents    # 返回可用 Agent 列表

# 對外 backend
curl http://127.0.0.1:8000/api/v1/utils/health-check/
curl http://127.0.0.1:8000/docs

# 前端
open http://localhost:5173

# MCP Gateway
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8002/tools
```

業務鏈路冒煙驗證：

```bash
# 直接查詢 entry -> processing（跳過 LLM）
curl "http://127.0.0.1:8010/query/risk/var-compare/BHMMF001?as_of_date=2026-06-25"
# 期望：200，results 有值
```

MCP 鏈路冒煙驗證：

```powershell
# 1) 驗證 gateway 可用
Invoke-RestMethod http://127.0.0.1:8002/health

# 2) 透過 gateway 調 internal get_context
Invoke-RestMethod -Method Post http://127.0.0.1:8002/mcp/internal/get_context -ContentType 'application/json' -Body '{"arguments":{}}'

# 3) 透過 shared client 驗證 MCP 調用（gateway 優先）
$env:MCP_GATEWAY_URL='http://127.0.0.1:8002'
@'
import asyncio
import importlib
m = importlib.import_module("4_mcp.client")
async def main():
     r = await m.call_internal_tool("get_context", {})
     print(r)
asyncio.run(main())
'@ | python -
```

---

## 6.1 完整使用 MCP 的完整命令（推薦直接複製）

```bash
# A. 一鍵啟動 Web + MCP 全套（gateway + internal + wind）
python scripts/dev.py --profile web --with-mcp

# B. 一鍵啟動完整 profile（已含 mcp-gateway/internal/wind）
python scripts/dev.py --profile full

# C. 顯式 parts 啟動（最清楚）
python scripts/dev.py --parts processing entry backend frontend  autorisk mcp-gateway internal-mcp wind-mcp
```

```powershell
# A. PowerShell 一鍵 Web + MCP 全套
./scripts/dev.ps1 -Profile web -WithMcp

# B. PowerShell 完整 profile
./scripts/dev.ps1 -Profile full

# C. PowerShell 顯式 parts
./scripts/dev.ps1 -Parts processing,entry,backend,frontend,mcp-gateway,internal-mcp,wind-mcp
```

## 6.2 專家知識提取 / Agent Chat 技能提取審批（新）

以下流程已接入強制審批 gate：

- `aiagent.engine.tools.execute_skill`（Agent Chat 的技能提取）
- `aiagent.engine.tools.knowledge_search`（當 source=skill_doc / agent_prompt / expert_chat 的專家知識提取）

實現方式：

- Agent 工具層先調用 `POST /review/gates/skill-extraction`
- Processing 端點使用 `requires_review(...)` 建立審批請求 + checkpoint 阻塞
- 審核員在 `http://127.0.0.1:8010` 的「審核收件箱」完成批准/拒絕
- 小富 AI 會自動給出審核建議（APPROVE/REJECT/ESCALATE/REQUIRE_HUMAN），人工可採納
- 批准後工具繼續執行；拒絕則工具返回審批未通過

快速演示（已啟動 `processing entry backend frontend`）：

```powershell
# 1) 直接觸發審批 gate（模擬 Agent Chat 技能提取）
Invoke-RestMethod -Method Post `
     -Uri "http://127.0.0.1:8001/review/gates/skill-extraction?fund_id=BHMMF001&as_of_date=2026-06-25" `
     -Headers @{ "X-API-Key" = "internal_key_change_me" } `
     -ContentType "application/json" `
     -Body '{"channel":"agentchat-skill","skill_name":"risk-analysis","query":"請提取風控技能流程","triggered_by":"demo-cli"}'

# 2) 打開審核頁，處理待審核單
#    http://127.0.0.1:8010  -> 審核收件箱

# 3) 批准後重新執行第 1 步，將返回 approved=true
```

更多設計與狀態機說明見：`docs/skill_approval_workflow.md`

---

## 7. 依賴 API Key 說明

| 功能 | 環境變量 | 說明 |
|---|---|---|
| Anthropic Claude | `ANTHROPIC_API_KEY` | Chat 默認模型，需設置 |
| Cursor Agent（Router / Composer）| `CURSOR_API_KEY` + `CURSOR_MODEL` | `crsr_...`；`CURSOR_MODEL=auto-smart`（可加 `CURSOR_OPTIMIZE_FOR=balanced`） |
| OpenRouter（Claude/GPT/Gemini/Grok）| `OPENROUTER_API_KEY` | 可選 `sk-or-v1-...` |
| OpenAI GPT 直連 | `OPENAI_API_KEY` | 可選 |
| Google Gemini | `GEMINI_API_KEY` | 需確認配額 |
| Kimi（月之暗面）| `MOONSHOT_API_KEY` | OpenAI 兼容接口 |
| DeepSeek | `DEEPSEEK_API_KEY` | OpenAI 兼容接口 |

均在項目根目錄 `.env` 中配置，6_entry 啟動時自動讀取。

---

## 8. 各層職責一覽

```
frontend:5173    對使用者顯示頁面，調用 backend API
     ↓
backend:8000     JWT 認證、統一 API 收口，代理到下游
     ↓
6_entry:8010     AI Agent 引擎——LLM 調用、tool_use 循環、SSE 流式輸出
     ↓
processing:8001  確定性計算核心——VaR / WAM / WAL / 持倉 / 合規
     ↓
PostgreSQL:5432  業務數據存儲（fsi schema + iam schema）
```

**一句話記憶**：`frontend` 展示 → `backend` 認證 → `6_entry` 思考（LLM） → `processing` 計算 → `DB` 取數
