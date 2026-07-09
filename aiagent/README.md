# aiagent — ARISK AI Agent 管理中樞

整合 [claude-risk-agent](https://github.com/anthropics/claude-risk-agent) 的 Agent 架構模式，
為 ARISK 平台提供業務定制的 AI Agent 能力。

---

## 目錄結構

```
aiagent/
├── agents/                        # Agent 系統提示（.md，frontmatter + 工作流）
│   ├── risk-analyst.md            # ARISK 風控分析師
│   ├── compliance-officer.md      # SFC 合規審查員
│   ├── fund-reporter.md           # 基金報表助理
│   ├── market-researcher.md       # 市場研究員（整合 claude-risk-agent）
│   ├── gl-reconciler.md           # 基金 GL 對賬員
│   ├── kyc-screener.md            # KYC 合規篩查員
│   ├── statement-auditor.md       # NAV 報表審計員
│   ├── valuation-reviewer.md      # 組合估值審查員
│   └── month-end-closer.md        # 月末結賬助手
│
├── skills/                        # 技能定義（SKILL.md，與 claude-risk-agent 格式一致）
│   ├── sector-overview/           # 行業/市場概覽（整合 market-researcher 核心技能）
│   ├── risk-analysis/             # 風控指標分析
│   ├── fund-admin/                # 基金會計（gl-recon, nav-tieout, roll-forward, variance-commentary）
│   ├── operations/                # 合規運營（kyc-doc-parse, kyc-rules）
│   └── financial-analysis/        # 財務分析（audit-xls）
│
├── engine/                        # 執行引擎（Python）
│   ├── tools.py                   # FSI 業務工具定義 + 執行器（含 sector_overview）
│   ├── runner.py                  # tool_use 執行循環（最多 10 輪）
│   └── stream.py                  # SSE 流式輸出封裝
│
├── cookbooks/                     # Managed Agent 多子 Agent 部署範本
│   ├── risk-agent/                # 風控 Agent（data-reader + calculator + writer）
│   └── compliance-agent/          # 合規 Agent（data-reader + compliance-writer）
│
├── scripts/                       # 開發工具（整合自 claude-risk-agent/scripts/）
│   ├── check.py                   # 完整性驗證（agents/skills/cookbooks/engine）
│   ├── sync_skills.py             # 從 claude-risk-agent 同步技能
│   ├── validate.py                # Agent 輸出 schema 校驗
│   └── orchestrate.py             # 多 Agent handoff 事件循環
│
└── msft365/                       # Microsoft 365 整合（整合自 claude-for-msft-365-install）
    ├── bootstrap/app.py           # FastAPI bootstrap endpoint（JWT + RBAC）
    └── commands/                  # Claude Office 命令（setup/manifest/consent/bootstrap/debug）
```

---

## 與 claude-risk-agent 的對應關係

| claude-risk-agent | ARISK aiagent | 說明 |
|---|---|---|
| `agents/*.md` frontmatter | `agents/*.md` **相同格式** | Agent 系統提示，可直接互換 |
| `SKILL.md` 技能定義 | `skills/*/SKILL.md` **相同格式** | 技能描述和工作流程 |
| MCP 工具（CapIQ, Daloopa, FactSet）| `engine/tools.py` FSI HTTP API | 工具執行層替換：MCP → processing:8001 |
| `orchestrate.py` handoff 事件循環 | `engine/runner.py` tool_use 循環 | 標準 messages API，更通用 |
| Claude Managed Agents API（beta）| `anthropic.messages.create()` + tools | 無需 beta，生產可用 |
| `managed-agent-cookbooks/*/agent.yaml` | `cookbooks/*/agent.yaml` **相同格式** | CMA 部署範本 |
| `scripts/check.py` | `scripts/check.py` | 完整性驗證工具 |
| `claude-for-msft-365-install/` | `msft365/` | Office Add-in 整合 |

---

## Agent 完整列表

| Agent ID | 中文名稱 | 主要工具 | 來源 |
|---|---|---|---|
| `risk-analyst` | ARISK 風控分析師 | get_exposure, get_var, get_var_compare | 原創 |
| `compliance-officer` | SFC 合規審查員 | get_exposure, get_positions | 原創 |
| `fund-reporter` | 基金報表助理 | get_exposure, get_nav_history | 原創 |
| `market-researcher` | 市場研究員 | sector_overview, get_positions | claude-risk-agent 整合 |
| `gl-reconciler` | 基金 GL 對賬員 | get_positions, get_nav_history | claude-risk-agent 整合 |
| `kyc-screener` | KYC 合規篩查員 | get_positions, get_exposure | claude-risk-agent 整合 |
| `statement-auditor` | NAV 報表審計員 | get_exposure, get_positions, get_nav_history | claude-risk-agent 整合 |
| `valuation-reviewer` | 組合估值審查員 | get_exposure, get_positions | claude-risk-agent 整合 |
| `month-end-closer` | 月末結賬助手 | get_exposure, get_positions, get_nav_history | claude-risk-agent 整合 |

---

## 功能示例：市場研究員 + sector-overview 技能

### 使用場景

在 `/chat` 頁面選擇「市場研究員」Agent，輸入：

> 分析 BHMMF001 的主要 CD 發行人信用環境和 HIBOR 走勢

### Agent 執行流程

```
用戶輸入
  ↓
market-researcher Agent（agents/market-researcher.md）
  ↓ 調用 sector_overview 工具
    → 載入 skills/sector-overview/SKILL.md 框架
    → 調用 get_positions 拉取 BHMMF001 持倉（實際 CD 發行人列表）
    → 返回：{ skill框架 + 持倉上下文 + 分析指令 }
  ↓ 調用 get_positions 工具（如需明細）
    → 按 asset_type=cd 過濾，獲取存款證持倉
  ↓ Claude 結合以上數據輸出
    → 利率環境分析（HIBOR 走勢）
    → 主要 CD 發行人信用背景
    → 集中度和風險分析
    → 投資含義
  ↓ 結構化 Markdown 研究報告
```

### 頁面展示效果

重啟服務後訪問 `http://localhost:5173/chat`，選 Agent → 基金 → 日期，輸入問題即可看到：

- **流式文字輸出**：逐字渲染，實時顯示分析過程
- **工具調用卡片**：`sector_overview` / `get_positions` 卡片可展開查看 API 返回數據
- **Markdown 格式**：輸出含表格、標題、代碼塊的結構化研究報告

### 示例輸出結構

```markdown
## 香港 CD 發行人信用環境分析 — BHMMF001 · 2026-06-25

**執行摘要**
當前 BHMMF001 持有 4 筆 CD，發行人覆蓋恒生銀行、中銀香港、花旗銀行...

### 一、HIBOR 利率環境
- 隔夜 HIBOR：4.2%（近期走勢...）
- 1 個月 HIBOR：4.35%

### 二、主要 CD 發行人信用分析
| 發行人 | 評級 | 市值 HKD | 佔 NAV |
|---|---|---|---|
| 恒生銀行 | AA- | 150,000,000 | 5.5% |
...

### 三、投資含義
...

*研究說明：持倉數據來源 ARISK 數據庫；評級基於 Claude 知識庫截止日期。*
```

---

## 完整數據流

```
瀏覽器 /chat 頁面（chat.tsx）
  ↓ fetch POST（SSE，Bearer JWT）
backend:8000/api/v1/fsi/agent/v2/stream
  ↓ httpx 流式代理（X-API-Key）
6_entry:8010/agent/v2/stream（agent_v2.py）
  ↓ sse_generator()
aiagent/engine/runner.py（tool_use 循環）
  ├── 載入 agents/{name}.md 系統提示
  ├── 調用 anthropic.messages.create() with tools
  ├── tool_use → aiagent/engine/tools.py
  │     ↓ direct 模式（AGENT_TOOL_MODE=direct）
  │   processing:8001（FastAPI 計算引擎）
  │     ↓ PostgreSQL fsi schema
  └── 返回 tool_result → 繼續循環
  ↓ SSE 事件流（text / tool_call / tool_result / done）
前端 ReadableStream 解析
  ├── text 事件 → 追加到消息氣泡（Markdown 渲染）
  ├── tool_call → 顯示工具調用卡片（可展開）
  └── done → 停止流式輸出
```

---

## 工具調用路徑

### 路徑 A：Direct（默認，低延遲）

```
6_entry:8010 → aiagent/engine/tools.py → processing:8001
```

- 優點：最低延遲，無認證跳轉
- 適用：開發環境、內部服務
- 配置：`AGENT_TOOL_MODE=direct`（默認）

### 路徑 B：Via Backend（可選，統一認證）

```
6_entry:8010 → aiagent/engine/tools.py → backend:8000 → processing:8001
```

- 優點：統一 JWT 認證層，符合生產安全要求
- 適用：需要完整審計日誌、對外暴露場景
- 配置：`AGENT_TOOL_MODE=via_backend` + 需要傳入 JWT token

### 環境變量

```bash
# .env
AGENT_TOOL_MODE=direct              # direct | via_backend
PROCESSING_API_URL=http://localhost:8001
PROCESSING_API_KEY=internal_key_change_me
BACKEND_URL=http://localhost:8000   # via_backend 模式需要
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

---

## SSE 事件格式

```json
{"type": "start",       "agent": "market-researcher"}
{"type": "text",        "content": "正在分析 BHMMF001 的 CD 發行人..."}
{"type": "tool_call",   "name": "sector_overview", "input": {"topic": "香港 CD 發行人信用環境", "fund_id": "BHMMF001"}, "id": "tu_001"}
{"type": "tool_result", "name": "sector_overview", "result": {"skill": "sector-overview", "template": "...", "portfolio_context": {...}}, "id": "tu_001"}
{"type": "tool_call",   "name": "get_positions",   "input": {"fund_id": "BHMMF001", "as_of_date": "2026-06-25", "asset_type": "cd"}, "id": "tu_002"}
{"type": "tool_result", "name": "get_positions",   "result": {"positions": [...]}, "id": "tu_002"}
{"type": "text",        "content": "## 香港 CD 發行人信用環境分析\n\n..."}
{"type": "done"}
```

---

## 快速開始

### 啟動服務

```bash
python scripts/dev.py   # 一鍵啟動 processing:8001 + 6_entry:8010 + backend:8000 + frontend:5173
```

### 在代碼中直接使用

```python
# 在 6_entry 中使用 SSE 生成器
import sys; sys.path.insert(0, str(REPO_ROOT))
from aiagent.engine import sse_generator

return StreamingResponse(
    sse_generator(
        messages=[{"role": "user", "content": "分析 BHMMF001 的 CD 發行人信用環境"}],
        agent_name="market-researcher",
        context={"fund_id": "BHMMF001", "as_of_date": "2026-06-25"},
    ),
    media_type="text/event-stream",
)
```

### 驗證模塊完整性

```bash
python aiagent/scripts/check.py
# 輸出：[OK] All checks passed! (9 agents, 9 skills, 2 cookbooks)
```

### 從 claude-risk-agent 同步技能

```bash
python aiagent/scripts/sync_skills.py --list   # 查看可同步的技能
python aiagent/scripts/sync_skills.py --force  # 強制同步覆蓋
```

---

## 二次開發指南

### 新增 Agent

1. 在 `agents/` 新建 `{name}.md`（遵循 frontmatter 格式）
2. 在 `engine/runner.py` 的 `AGENT_NAMES` 字典中註冊
3. 運行 `python aiagent/scripts/check.py` 驗證

### 新增工具

1. 在 `engine/tools.py` 的 `TOOLS` 列表中加入工具定義（Claude tool_use JSON schema）
2. 在 `_call_direct()` 中加入對應的 HTTP 調用
3. 新工具自動對所有 Agent 可用

### 新增技能（Skill）

1. 在 `skills/{category}/{skill-name}/` 新建 `SKILL.md`（遵循 frontmatter 格式）
2. 如需在 tool_use 中觸發，在 `tools.py` 加入對應工具，並在 `execute_tool()` 中讀取 SKILL.md
3. 參考：`sector_overview` 工具讀取 `skills/sector-overview/SKILL.md` 的實現方式

### 新增 Cookbook（多子 Agent 部署）

1. 在 `cookbooks/{name}/` 新建 `agent.yaml`（遵循 managed-agent-cookbooks 格式）
2. 在 `subagents/` 下定義各子 Agent yaml
3. 注意：只有葉節點 writer 子 Agent 擁有 Write 工具（最小權限原則）
