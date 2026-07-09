# ARISK 架構設計說明 — aiagent 與整體分層的關聯

> 版本：1.0 · 2026-07-08

---

## 一、ARISK 整體架構：縱向基礎設施分層

ARISK 採用「分層能力平台 + 統一前後端產品入口」的設計，共 8 層，每層職責單一、邊界清晰。

```
┌──────────────────────────────────────────────────────────────┐
│  frontend/          Web UI（React 19 + Vite + shadcn/ui）    │  用戶界面層
│  backend/           Web API 閘道（FastAPI + JWT）             │  認證代理層
├──────────────────────────────────────────────────────────────┤
│  6_entry/           統一入口路由（Web / CLI / Excel）         │  請求分發層
├──────────────────────────────────────────────────────────────┤
│  3_skills/          能力技能庫（SKILL.md + slash commands）   │  能力定義層
│  4_mcp/             外部數據連接器（Wind API / 內部 DB）       │  數據連接層
│  5_deploy/          部署編排（agent.yaml / k8s / Docker）     │  基礎設施層
├──────────────────────────────────────────────────────────────┤
│  2_processing/      業務計算引擎（FastAPI:8001 + Celery）     │  業務計算層
│  1_datastorage/     PostgreSQL · Redis · MinIO / S3          │  數據持久層
└──────────────────────────────────────────────────────────────┘
```

每層的核心問題：

| 層 | 核心問題 | 技術實現 |
|---|---|---|
| `frontend/` | 用戶怎麼看到數據？ | React SPA + SSE 流式渲染 |
| `backend/` | 誰有權訪問？ | FastAPI + JWT + FSI 代理路由 |
| `6_entry/` | 請求從哪進來，轉給誰？ | Web / CLI / Excel 統一入口 |
| `3_skills/` | Claude Code 能做什麼？ | SKILL.md + `/risk` 命令定義 |
| `4_mcp/` | 外部數據怎麼接入？ | Wind MCP Server / 內部 DB MCP |
| `5_deploy/` | 系統怎麼部署？ | agent.yaml / k8s manifests |
| `2_processing/` | 業務怎麼計算？ | VaR / WAM / WAL / 合規引擎 |
| `1_datastorage/` | 數據怎麼存？ | PostgreSQL fsi schema（97 張表）|

---

## 二、aiagent/ 的定位：橫切的「AI 智能模塊」

`aiagent/` **不是第 9 層**，它是一個橫向切入的**業務模塊**，專門服務 Web Chat（`/chat`）功能中的 AI 智能執行部分。

```
┌──────────────────────────────────────────────────────────────┐
│                   縱向分層架構                                 │
│  frontend → backend → 6_entry → 2_processing → 1_datastorage │
└──────────────────┬───────────────────────────────────────────┘
                   │ 6_entry/agent_v2.py 調用
                   ▼
┌──────────────────────────────────────────────────────────────┐
│                  aiagent/（橫切業務模塊）                      │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ agents/  │  │ skills/  │  │cookbooks/│  │  scripts/   │ │
│  │ 9 個 .md │  │ 9 類技能  │  │CMA 部署  │  │ check/sync  │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  engine/（AI 執行核心）                                   │ │
│  │  tools.py ──→ 2_processing:8001（消費計算層）            │ │
│  │  runner.py    tool_use 循環（Claude API）                │ │
│  │  stream.py    SSE 流式輸出                               │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  msft365/（Microsoft 365 整合，Claude Office Add-in）         │
└──────────────────────────────────────────────────────────────┘
                   │ engine/tools.py 調用
                   ▼
            2_processing:8001（計算層）
```

**核心定位：** `aiagent/` 解決的是「Chat 對話中 AI 怎麼思考、用什麼技能、調用什麼工具」的**智能執行問題**，而 ARISK 6 層架構解決的是「數據怎麼存、怎麼算、怎麼傳、怎麼部署、怎麼接入」的**基礎設施問題**。

---

## 三、四組容易混淆的對比

### 3.1 `3_skills/` vs `aiagent/skills/`

兩者都叫「技能」，但執行環境和觸發方式完全不同。

| 對比維度 | `3_skills/skills/` | `aiagent/skills/` |
|---|---|---|
| **調用者** | Claude Code IDE / Excel 插件 | Web Chat Agent（/chat 頁面）|
| **觸發方式** | 用戶在終端/Excel 輸入 `/risk`、`/compliance` | Agent 在對話中通過 tool_use 自動調用 |
| **執行環境** | Claude Code 終端 / Excel 環境 | 瀏覽器 SSE 流式對話 |
| **技能格式** | SKILL.md（相同格式）| SKILL.md（相同格式）|
| **本質作用** | 告訴 Claude Code「你有什麼能力」 | 告訴 Chat Agent「這件事怎麼做」 |

```
3_skills/ 調用路徑：
  Excel / Terminal
    → Claude Code
    → 3_skills/skills/risk-analysis/SKILL.md（技能框架）
    → 2_processing API（獲取數據）
    → 輸出到 Excel / 終端

aiagent/skills/ 調用路徑：
  瀏覽器 /chat 頁面
    → 6_entry/agent_v2.py
    → aiagent/engine/runner.py（tool_use 循環）
    → sector_overview 工具讀取 aiagent/skills/sector-overview/SKILL.md
    → 2_processing API（獲取持倉數據）
    → SSE 流式輸出到瀏覽器
```

**類比：** `3_skills/` 是「菜單說明」（告知能做什麼），`aiagent/skills/` 是「烹飪手冊」（指導怎麼做）。

---

### 3.2 `5_deploy/agents/` vs `aiagent/cookbooks/`

兩者都有 `agent.yaml`，但關注對象不同。

| 對比維度 | `5_deploy/agents/` | `aiagent/cookbooks/` |
|---|---|---|
| **關注對象** | 整個 ARISK 平台的 Agent 部署架構 | Chat 功能的 AI 執行模式 |
| **文件格式** | Anthropic Managed Agents YAML | 相同格式，針對 Chat 場景 |
| **子 Agent 職責** | 數據拉取、風控計算、報告生成（系統級）| 數據讀取、計算分析、格式輸出（對話級）|
| **生命週期** | 隨平台部署常駐 | 隨 Chat 會話按需啟動 |
| **來源** | ARISK 原創設計 | 整合自 claude-risk-agent/managed-agent-cookbooks/ |

```
5_deploy/ 關注的是：
  整個 ARISK 系統的 subagent 架構
  ├── risk-agent/subagents/data-puller.yaml     （拉取持倉數據）
  ├── risk-agent/subagents/risk-calculator.yaml  （VaR 計算）
  └── risk-agent/subagents/report-writer.yaml    （生成報告）
  → 解決：系統怎麼持續運行

aiagent/cookbooks/ 關注的是：
  Chat 對話中的 AI 協作模式
  ├── risk-agent/subagents/data-reader.yaml      （只讀查詢）
  ├── risk-agent/subagents/risk-calculator.yaml  （分析計算）
  └── risk-agent/subagents/report-writer.yaml    （唯一可寫葉節點）
  → 解決：一次對話中 AI 怎麼分工
```

---

### 3.3 `6_entry/agent_mode.py` vs `aiagent/engine/`

| 對比維度 | `6_entry/agent_mode.py`（V1）| `aiagent/engine/`（V2）|
|---|---|---|
| **職責** | HTTP 接口、任務隊列管理、狀態輪詢 | AI 思考過程、tool_use 循環、SSE 輸出 |
| **角色** | 「前台」接收請求、調度任務 | 「大廚」執行智能分析 |
| **Claude 使用方式** | 純文字對話（無 tool_use）| tool_use 循環（可調用業務工具）|
| **輸出方式** | 輪詢 task_id | SSE 流式實時推送 |
| **Agent 定義** | 硬編碼系統提示 | 讀取 `agents/*.md` 文件 |
| **演進關係** | 舊版，保留向後兼容 | 新版，整合 aiagent 模塊 |

```
演進關係：
  V1：6_entry/agent_mode.py
    ↓ 直接調用 anthropic.messages.create()
    ↓ 固定系統提示，無工具調用

  V2：6_entry/agent_v2.py（調用 aiagent/）
    ↓ 調用 aiagent/engine/sse_generator()
    ↓ 載入 agents/*.md，支持 9 個 Agent
    ↓ tool_use 循環，調用 5 個 FSI 工具 + sector_overview
    ↓ SSE 實時流式輸出
```

---

### 3.4 `4_mcp/` vs `aiagent/engine/tools.py`

| 對比維度 | `4_mcp/` | `aiagent/engine/tools.py` |
|---|---|---|
| **協議** | MCP（Model Context Protocol）| Claude tool_use + HTTP |
| **連接對象** | Wind 外部市場數據 / 內部 DB 只讀查詢 | 2_processing 業務計算 API |
| **使用者** | Claude Code / 3_skills 技能層 | Chat Agent（aiagent/engine）|
| **啟動方式** | 獨立 MCP Server 進程 | 函數調用（嵌入進程）|
| **類比** | 「食材供應商的送貨通道」 | 「廚房內部的工具台」 |

---

## 四、完整請求流程對比

### 場景 A：Excel 風控分析（走 3_skills + 4_mcp）

```
用戶在 Excel 輸入 /risk BHMMF001 2026-06-25
  ↓
Claude Code 匹配 3_skills/commands/risk.md
  ↓
執行 3_skills/skills/risk-analysis/SKILL.md 技能
  ↓ （可能通過 4_mcp 獲取 Wind 數據）
4_mcp/internal/internal_mcp_server.py（只讀查詢）
  ↓
2_processing API（計算 WAM/WAL/VaR）
  ↓
輸出到 Excel 工作表
```

### 場景 B：Web Chat 風控問答（走 aiagent/）

```
用戶在瀏覽器 /chat 輸入「分析 BHMMF001 的 WAM 狀態」
  ↓
frontend/chat.tsx（SSE fetch POST）
  ↓
backend:8000/api/v1/fsi/agent/v2/stream（JWT 驗證）
  ↓
6_entry:8010/agent/v2/stream（X-API-Key）
  ↓
aiagent/engine/sse_generator()
  ↓
aiagent/engine/runner.py
  ├── 載入 agents/risk-analyst.md（系統提示）
  ├── 調用 Claude API（messages.create + tools）
  ├── tool_use: get_exposure → tools.py → processing:8001
  ├── tool_use: get_var_compare → tools.py → processing:8001
  └── 文字流式輸出
  ↓
SSE 事件流 → 瀏覽器 ReadableStream → 消息氣泡渲染
```

### 場景 C：市場研究（走 aiagent/ + sector-overview 技能）

```
用戶選「市場研究員」Agent，輸入「分析 BHMMF001 的 CD 發行人信用環境」
  ↓
aiagent/engine/runner.py
  ├── 載入 agents/market-researcher.md
  ├── tool_use: sector_overview
  │     → tools.py._execute_sector_overview()
  │     → 讀取 skills/sector-overview/SKILL.md 框架
  │     → 同時調用 get_positions 獲取實際 CD 持倉
  │     → 返回：{ 技能框架 + 持倉上下文 + 分析指令 }
  ├── Claude 結合以上數據輸出結構化研究報告
  └── SSE 流式渲染 Markdown 研究報告
```

---

## 五、整合 claude-risk-agent 後的模塊對應

ARISK `aiagent/` 模塊完整整合了 `claude-risk-agent` 的架構模式，形成一一對應關係：

```
claude-risk-agent/                    ARISK aiagent/
─────────────────────────────────────────────────────────
plugins/agent-plugins/*/agents/*.md   agents/*.md
  ├── pitch-agent.md                    ├── risk-analyst.md（原創）
  ├── market-researcher.md         →    ├── market-researcher.md（整合）
  ├── gl-reconciler.md             →    ├── gl-reconciler.md（整合）
  ├── kyc-screener.md              →    ├── kyc-screener.md（整合）
  ├── statement-auditor.md         →    ├── statement-auditor.md（整合）
  ├── valuation-reviewer.md        →    ├── valuation-reviewer.md（整合）
  └── month-end-closer.md          →    └── month-end-closer.md（整合）

plugins/vertical-plugins/*/skills/    skills/
  ├── fund-admin/{gl-recon,...}    →    ├── fund-admin/
  ├── operations/{kyc-*}           →    ├── operations/
  └── financial-analysis/audit-xls →   └── financial-analysis/audit-xls

managed-agent-cookbooks/*/agent.yaml   cookbooks/
  ├── pitch-agent/                 →    ├── risk-agent/（ARISK 定制）
  └── market-researcher/           →    └── compliance-agent/（ARISK 定制）

scripts/
  ├── check.py                     →    scripts/check.py（適配 ARISK 結構）
  ├── sync-agent-skills.py         →    scripts/sync_skills.py
  ├── validate.py                  →    scripts/validate.py
  └── orchestrate.py               →    scripts/orchestrate.py

claude-for-msft-365-install/           msft365/（完整複製）

MCP 工具（CapIQ, Daloopa, FactSet）     engine/tools.py
  → 外部金融數據                         → ARISK 2_processing API
  （協議：MCP）                           （協議：HTTP + Claude tool_use）
```

**關鍵替換：** claude-risk-agent 使用 MCP 協議連接 CapIQ/FactSet 等外部數據源；ARISK 將其替換為直接調用 `2_processing` 業務計算 API，數據來自自建 PostgreSQL，無需外部 MCP 服務器。

---

## 六、設計原則

### 原則 1：最小權限（Least Privilege）
仿照 claude-risk-agent 的子 Agent 設計——`cookbooks/` 中只有葉節點 `*-writer.yaml` 擁有 Write 工具，讀取和計算 Agent 無寫入權限。

### 原則 2：技能即文件（Skills as Files）
Agent 系統提示、技能定義都是 `.md` 文件，支持版本控制、即時修改生效，無需重新部署。修改 `agents/risk-analyst.md` 即時改變 Agent 行為。

### 原則 3：工具路徑可配置（Configurable Tool Path）
`engine/tools.py` 支持兩種調用路徑，通過環境變量切換：
- `AGENT_TOOL_MODE=direct` → 直連 processing:8001（開發默認）
- `AGENT_TOOL_MODE=via_backend` → 經 backend:8000 統一認證（生產可選）

### 原則 4：技能跨上下文複用
`SKILL.md` 格式在整個 ARISK 架構中統一：
- `3_skills/` 的技能服務 Claude Code
- `aiagent/skills/` 的技能服務 Chat Agent
- 同一格式，不同執行上下文，便於二次開發

### 原則 5：驗證即文檔（Check as Documentation）
`scripts/check.py` 既是 CI 驗證工具，也隱式定義了 `aiagent/` 的完整結構規範——運行它可以隨時了解整個模塊的健康狀態。

---

## 七、一句話總結

| 維度 | 說明 |
|---|---|
| **ARISK 6 層架構** | 解決「數據怎麼存、怎麼算、怎麼傳、怎麼部署、怎麼接入」的**基礎設施問題** |
| **`aiagent/` 模塊** | 解決「Chat 對話中 AI 怎麼思考、用什麼技能、調用什麼工具」的**智能執行問題** |
| **兩者關係** | `aiagent/` 是運行在 6 層架構之上的**業務模塊**，由 `6_entry` 調用，消費 `2_processing` 的計算能力，不替代任何一層 |
| **整合邏輯** | `claude-risk-agent` 提供的是**金融 AI Agent 的設計模式**（提示詞格式、技能框架、多子 Agent 協作）；`aiagent/` 將這些模式落地在 ARISK 的業務數據和 API 體系上 |
