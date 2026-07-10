# ARISK AI Agent 雙層業務架構

ARISK 平台採用**雙層 AI Agent 架構**，兩層都是業務功能的 AI 化實現，
面向不同對象，各自實現完整的四層 AI Agent 框架，並**可以互相擴展**。

```
┌──────────────────────────────────────────────────────────────────┐
│  Platform Agent（系統層業務）                                       │
│  對象：系統開發人員、運維                                            │
│  作用：① 運行系統業務（ETL/快照/合規監控/報表）                       │
│        ② 擴展系統業務（添加工具/技能/Agent 到 aiagent）               │
│  技能庫：3_skills/skills/（系統級）                                  │
│  代碼：platform_agent/                                             │
└──────────────────────────┬───────────────────────────────────────┘
                           │
          ┌────────────────┴────────────────┐
          │ Chat Agent 調用 Platform 業務服務  │
          │ Platform Agent 擴展 Chat 工具集   │
          └────────────────┬────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  Chat Agent（用戶層業務）                                           │
│  對象：風控主任、合規審查員、報告員、研究員                             │
│  作用：① 執行用戶業務（分析/審查/報告/研究）                           │
│        ② 擴展個人業務（添加個人工具/技能到自己的 Agent）                │
│  技能庫：aiagent/skills/（用戶級）+ 用戶個人技能                       │
│  代碼：aiagent/                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 一、Platform Agent — 系統層業務 AI

### L1 — 控制與規劃層 (Brain)

**業務規則引擎（確定性）：**
- VaR 計算（歷史模擬/蒙特卡洛/參數法）
- WAM / WAL / DLA / WLA 計算
- SFC 合規閾值核查

**AI 決策層（LLM 驅動）：**
- 系統調度員（scheduler）— 協調 Celery 任務依賴和執行順序
- 系統監控員（monitor）— 識別數據異常、服務降級、合規預警
- ETL 協調員（etl-coordinator）— 數據質量驗證、異常處理決策

```
文件：platform_agent/agents/ | platform_agent/engine/platform_runner.py
```

### L2 — 記憶與知識層 (Memory)

**業務數據庫（機構長期記憶）：**
- PostgreSQL fsi schema — 97 張業務表（持倉/風控快照/合規/報表）
- TimescaleDB — NAV 歷史序列、VaR 趨勢時序

**操作緩存（短期記憶）：**
- Redis DB0 — 行情緩存（30min TTL）、用戶 Session
- Redis DB1/DB2 — Celery Broker + Result Backend

**知識索引（系統技能知識）：**
- fsi.knowledge\_chunk — 3\_skills/*.md 已索引（pgvector）

```
文件：1_datastorage/ | 2_processing/api/deps.py
```

### L3 — 工具與技能層 (Tools + Skills)

**系統運維工具（9個，platform\_agent/engine/system\_tools.py）：**

| 工具 | 業務功能 |
|------|---------|
| `trigger_celery_task` | 觸發風控快照/ETL/AI異常檢測 |
| `get_task_status` | 監控任務執行進度 |
| `check_system_health` | 服務健康核查 |
| `query_business_db` | 業務數據質量驗證 |
| `trigger_report` | 觸發報表生成 |
| `get_queue_stats` | Celery 隊列監控 |
| `scaffold_system_tool` | **擴展：生成新業務工具模板** |
| `scaffold_system_skill` | **擴展：生成新技能模板** |
| `scaffold_agent_role` | **擴展：生成新 Agent 角色模板** |

**系統級技能（3\_skills/skills/）：**

| 技能 | 層 | 說明 |
|------|---|------|
| `etl-positions` | Platform | 每日持倉 ETL 執行流程 |
| `compliance-monitor` | Platform | SFC 合規自動監控 |
| `daily-risk-ops` | Platform | 每日風控快照流程 |
| `mmf-compliance` | Platform | MMF 守則核查 |
| `var-analysis` | Platform | VaR 計算分析 |
| `risk-analysis` | Platform | 風控指標分析 |
| `performance-report` | Platform | 業績報告生成 |
| `human-review` | Platform | 人工審核協調 |

```
文件：3_skills/skills/ | platform_agent/engine/system_tools.py
```

### L4 — 編排與通訊層 (Orchestration)

**Celery 任務調度（核心編排）：**
- Beat 定時：daily-risk-snapshot(18:30) / load-positions(09:00) / price-cache(每小時)
- AI 觸發：run\_ai\_anomaly\_detection / run\_agent\_task
- 重試機制：max\_retries=3，超時控制 time\_limit=600s

**服務網格：**
- processing:8001 — 計算引擎（X-API-Key 認證）
- 6_entry:8010 — 內部路由（Agent/Direct 分流）
- backend:8000 — 對外認證網關（JWT）

**Platform Agent SSE 端點：**
- `POST 6_entry:8010/platform/v1/stream` — 實時流式業務協調
- `GET 6_entry:8010/platform/v1/agents` — 可用系統 Agent 列表

```
文件：2_processing/workers/ | 6_entry/web/routers/platform_v1.py
```

---

## 二、Chat Agent — 用戶層業務 AI

### L1 — 控制與規劃層 (Brain)

**多模型 LLM 路由（7個 Provider）：**

| Provider | 模型 | 適用場景 |
|---------|------|---------|
| Anthropic Claude | sonnet-4-6（默認）/opus/haiku | 複雜分析、合規審查 |
| xAI Grok（OpenRouter）| grok-4.20 / grok-4.3 | 香港無地區限制 |
| OpenAI GPT | gpt-4o / gpt-4o-mini | 可選 |
| Google Gemini | gemini-2.0-flash | 可選 |
| Kimi / DeepSeek | moonshot / deepseek | 長文本 / 推理增強 |

**智能規劃（Plan-and-Execute）：**
- `planner.py` — 複雜任務拆解（多步驟分析計劃）
- 前端顯示 `plan` SSE 事件，用戶可見執行計劃

**ReAct 推理（max 10 輪）：**
- `runner.py` — 思考→調用工具→觀察→繼續思考
- `reflector.py` — 輸出質量評估，數據為空時自動提示

**用戶個性化（iam.user\_agent\_config）：**
- 每人設置默認模型、默認角色、自定義指令
- 自定義指令自動注入每次對話的 system prompt
- 示例：「我是博匯基金風控主任，主要關注 BHMMF001，
         請用簡潔的中文回覆，數字保留兩位小數」

```
文件：aiagent/engine/{planner,runner,reflector}.py
```

### L2 — 記憶與知識層 (Memory)

**對話上下文（短期記憶）：**
- `context_manager.py` — 滑動窗口 40 輪，超限自動摘要壓縮
- 壓縮策略：用 claude-haiku 摘要舊消息（節省 Token）

**對話歷史（持久化記憶）：**
- `iam.chat_session` — 用戶所有對話列表（右側歷史面板）
- `iam.chat_message` — 完整消息記錄（role/content/tool\_calls）

**業務知識庫（語義記憶 RAG）：**
- `vector_store.py` — pgvector 混合搜索（向量60% + BM25 40%）
- 搜索 `fsi.knowledge_chunk`（已索引 3\_skills + aiagent/agents）
- 示例：「WAL 上限的 SFC 條款」→ 返回守則原文

**情景記憶（Episodic Memory）：**
- `iam.agent_episode` — 保存成功對話的 query+summary+tool\_calls
- 下次相似問題時，Agent 可參考過去成功路徑

```
文件：aiagent/memory/ | iam.chat_session/chat_message/agent_episode
```

### L3 — 工具與技能層 (Tools + Skills)

**系統業務工具（10個，共享給所有用戶）：**

| 工具 | 調用來源 | 業務說明 |
|------|---------|---------|
| `get_system_info` | Platform L2 | 在管基金列表+當前日期 |
| `get_exposure` | Platform L3 計算 | WAM/WAL/DLA/WLA/合規 |
| `get_var` | Platform L3 計算 | Value-at-Risk（3種方法） |
| `get_var_compare` | Platform L3 計算 | 三方法 VaR 對比 |
| `get_positions` | Platform L2 數據 | 持倉明細 |
| `get_nav_history` | Platform L2 數據 | NAV 歷史 |
| `knowledge_search` | Chat L2 RAG | SFC守則/技能知識語義搜索 |
| `generate_report` | Platform L3 報表 | 觸發報表生成 |
| `query_internal_db` | Platform L2 數據 | 原始數據查詢 |
| `sector_overview` | aiagent SKILL.md | 市場行業研究 |

**用戶個人工具（iam.user\_custom\_tool，每用戶獨立）：**
- 用戶自定義 HTTP API 工具
- 示例：查詢公司內網系統、調用彭博 API、讀自定義 Excel
- API：`POST /api/v1/custom-tools/`
- Chat Agent 每次請求前自動從 DB 加載並合并到 tool\_use

**用戶級技能（aiagent/skills/ + 個人樣本）：**

| 技能 | 層 | 說明 |
|------|---|------|
| `risk-analysis` | Chat | WAM/WAL/VaR 分析流程 |
| `sfc-compliance` | Chat | SFC 合規核查 |
| `sector-overview` | Chat | 市場行業概覽 |
| `var-analysis` | Chat | VaR 詳細分析 |
| `gl-recon` | Chat | GL 對賬 |
| `nav-tieout` | Chat | NAV 報表核對 |
| `kyc-doc-parse` | Chat | KYC 文件解析 |
| `kyc-rules` | Chat | KYC 合規規則 |
| **portfolio-morning-brief** | 用戶樣本 | 每日晨報（可個性化） |
| **compliance-weekly-review** | 用戶樣本 | 週度合規審查 |

```
文件：aiagent/engine/tools.py | aiagent/skills/ | iam.user_custom_tool
```

### L4 — 編排與通訊層 (Orchestration)

**智能 Agent 路由（Supervisor）：**
- `supervisor.py` — 意圖識別，路由到最合適的專業 Agent
- 自動 Handoff：「VaR + 合規」→ risk-analyst → compliance-officer

**10 個專業 Chat Agent 角色：**

| Agent | 業務定位 |
|-------|---------|
| `general` | 通用助理 |
| `risk-analyst` | 風控分析（WAM/WAL/VaR/SFC）|
| `compliance-officer` | SFC 合規審查 |
| `fund-reporter` | 基金報表助理 |
| `market-researcher` | 市場研究員 |
| `gl-reconciler` | GL 對賬員 |
| `kyc-screener` | KYC 合規篩查 |
| `statement-auditor` | NAV 報表審計 |
| `valuation-reviewer` | 組合估值審查 |
| `month-end-closer` | 月末結賬助手 |

**任務狀態機（Redis）：**
- `task_state.py` — QUEUED→PLANNING→EXECUTING→REFLECTING→DONE
- 長任務優先走 Celery（持久化+重試），降級 asyncio

**流式通訊（SSE）：**
- `stream.py` — 完整事件：start/plan/text/tool\_call/tool\_result/supervisor/handoff/reflection/done
- 端點：`POST 6_entry:8010/agent/v2/stream`

```
文件：aiagent/orchestrator/ | engine/stream.py | 6_entry/web/routers/agent_v2.py
```

---

## 三、雙層業務對照表

| 維度 | Platform Agent（系統層）| Chat Agent（用戶層）|
|------|----------------------|-------------------|
| **對象** | 系統開發人員 / 運維 | 風控主任 / 合規員 / 報告員 |
| **觸發** | Celery Beat 定時 / 事件驅動 | 用戶對話輸入 |
| **L1 Brain** | 規則引擎 + AI 調度決策 | 多模型 LLM + ReAct + Planner |
| **L2 Memory** | fsi 業務數據庫 + TimescaleDB | 對話歷史 + RAG + 情景記憶 |
| **L3 Tools** | 系統運維 + scaffold 擴展工具 | 業務查詢 + 個人自定義工具 |
| **L3 Skills** | `3_skills/`（系統級業務技能）| `aiagent/skills/`（用戶級業務技能）|
| **L4 Orchestration** | Celery + 服務網格 | Supervisor + Redis 狀態機 + SSE |
| **個性化** | 無（全局共享）| 有（per-user config + tools + skills）|
| **擴展方式** | scaffold 工具 → 代碼審查 → 提交 | UI 配置 / API 直接生效 |

---

## 四、可擴展性設計

### 系統開發人員 → 擴展系統業務功能

```
Platform Agent 對話
  → scaffold_system_tool("get_credit_rating", "查詢信用評級", "/risk/credit")
  → 生成代碼模板
  → 開發者複制到 aiagent/engine/tools.py
  → 重啟 6_entry → 所有用戶 Chat Agent 立即可用新工具
```

### 用戶 → 擴展個人業務能力

```
用戶通過 Chat 頁面（設置）或 API：
  → POST /api/v1/agent-config/me      設置默認模型/角色/自定義指令
  → POST /api/v1/custom-tools/         添加個人 HTTP 工具
  → 下次對話立即生效（無需重啟任何服務）
```

---

## 五、目錄結構全景

```
fsi-risk-platform/
│
├── 1_datastorage/          Platform L2: 存儲定義
├── 2_processing/           Platform L1+L3+L4: 計算引擎+Celery
├── 3_skills/               Platform L3 Skills: 系統業務技能庫
│   └── skills/
│       ├── etl-positions/     持倉 ETL 技能
│       ├── compliance-monitor/ 合規監控技能
│       ├── mmf-compliance/    MMF 守則核查
│       ├── var-analysis/      VaR 分析
│       └── ...
├── 4_mcp/                  Platform L3: MCP 外部數據接入
├── 5_deploy/               Platform L4: 部署編排
├── 6_entry/                Platform L4 + Chat L4: 服務網關
│
├── platform_agent/         Platform Agent 實現
│   ├── agents/             系統 Agent 角色提示
│   ├── engine/             執行引擎 + 系統工具
│   └── skills/             Platform Agent 特定技能
│
├── aiagent/                Chat Agent 實現
│   ├── agents/             用戶業務 Agent 角色提示（10個）
│   ├── engine/             LLM執行引擎+工具+Planner+Reflector
│   ├── memory/             Context管理+向量存儲+知識索引
│   ├── orchestrator/       Supervisor+Redis狀態機
│   ├── skills/             用戶級業務技能庫
│   │   ├── risk-analysis/  風控分析技能
│   │   ├── sector-overview/ 市場研究技能
│   │   ├── fund-admin/     基金管理技能
│   │   └── user-samples/   ← 用戶技能樣本（參考模板）
│   │       ├── portfolio-morning-brief.md
│   │       └── compliance-weekly-review.md
│   └── cookbooks/          多 Agent 部署配置
│
├── backend/                Platform L4: JWT 認證網關
└── frontend/               用戶界面
    └── src/routes/_layout/
        └── chat.tsx        Chat Agent 對話界面
```

---

## 六、初始化和啟動

```bash
# 啟動全部服務（Platform + Chat）
python scripts/dev.py

# Platform Agent — 初始化知識庫（一次性）
python -m aiagent.memory.knowledge_indexer    # 索引 3_skills 到 RAG

# Platform Agent — Celery Worker（系統業務自動化）
celery -A 2_processing.workers.celery_app worker --loglevel=info
celery -A 2_processing.workers.celery_app beat --loglevel=info

# Platform Agent — 觸發系統業務（通過 SSE API）
curl -X POST http://localhost:8010/platform/v1/stream \
  -d '{"messages":[{"role":"user","content":"觸發今日風控快照"}],"agent":"scheduler"}'

# Chat Agent — 用戶對話（通過前端）
open http://localhost:5173/chat
```

---

## 七、技能添加指南

### 添加系統級技能（Platform L3）

```bash
# 1. 在 3_skills/skills/ 創建新技能目錄
mkdir 3_skills/skills/new-skill

# 2. 創建 SKILL.md（或通過 Platform Agent scaffold_system_skill 生成）
# 3. 重新索引知識庫
python -m aiagent.memory.knowledge_indexer
```

### 添加用戶級技能（Chat L3）

```bash
# 系統默認技能（所有用戶共享）
mkdir aiagent/skills/category/new-skill
# 創建 SKILL.md，重索引

# 用戶個人工具（通過 API，即時生效）
curl -X POST /api/v1/custom-tools/ \
  -d '{"tool_name":"my_tool","description":"...","endpoint":"http://..."}'
```
