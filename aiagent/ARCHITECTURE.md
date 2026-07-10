# ARISK AI Agent 四層架構

> 完整架構說明。開發日誌和接入指南請見 README.md。

## 架構圖

```
+------------------------------------------------------------------+
| Layer 1: 控制與規劃層 (Brain / Planning)                          |
|  planner.py   — CoT 任務拆解 (Plan-and-Execute)                   |
|  runner.py    — 多模型 ReAct 循環 (Reason→Act→Observe, max 10輪) |
|  reflector.py — 自我反思與輸出質量評估                            |
+------------------------------------------------------------------+
| Layer 2: 記憶與知識層 (Memory / Knowledge)                        |
|  memory/context_manager.py — 短期：滑動窗口 + LLM 摘要壓縮        |
|  memory/vector_store.py    — 長期：pgvector RAG（混合搜索）        |
|  DB: fsi.knowledge_chunk (向量) + iam.agent_episode (情景記憶)    |
+------------------------------------------------------------------+
| Layer 3: 工具與技能層 (Tools / Skills)                            |
|  engine/tools.py — 8 個 FSI 業務工具                              |
|  skills/         — SKILL.md 模板庫                               |
+------------------------------------------------------------------+
| Layer 4: 編排與通訊層 (Orchestration / Multi-Agent)               |
|  orchestrator/supervisor.py  — 意圖路由 + Multi-Agent Handoff     |
|  orchestrator/task_state.py  — Redis 狀態機                       |
|  engine/stream.py            — SSE 流式輸出（含 plan/reflection） |
+------------------------------------------------------------------+
```

## 請求流程

```
Browser /chat
  → backend:8000  [JWT 認證]
  → 6_entry:8010  [agent_v2.py]
  → stream.py     [Layer 4 入口]
      ├─ Planner.create_plan()      [L1: 複雜任務規劃]
      ├─ run_agent()                [L1: ReAct 循環]
      │    ├─ ContextManager        [L2: 短期記憶]
      │    ├─ LLM API               [L1: 推理]
      │    └─ execute_tool()        [L3: 工具執行]
      │         └─ knowledge_search [L2: RAG]
      └─ Reflector.detect_issues()  [L1: 自我反思]
  → save_episode()                  [L2: 情景記憶]
```

## 新增 SSE 事件

| 事件 | 說明 |
|---|---|
| `plan` | 執行計劃（title + steps 列表） |
| `supervisor` | Supervisor 路由決策信息 |
| `handoff` | Agent 交接（from → to） |
| `reflection` | 輸出質量評估結果 |

## 數據庫表（Layer 2）

| 表 | Schema | 說明 |
|---|---|---|
| `knowledge_document` | fsi | 知識文檔索引 |
| `knowledge_chunk` | fsi | 分塊 + `vector(1536)` 嵌入 |
| `agent_episode` | iam | 情景記憶（過去成功分析） |
| `chat_session` | iam | 用戶會話（已有） |
| `chat_message` | iam | 歷史消息（已有） |

## 工具清單（Layer 3）

| 工具 | 說明 |
|---|---|
| `get_system_info` | 基金列表 + 當前日期 |
| `get_exposure` | 風險暴露（WAM/WAL/合規） |
| `get_var` | Value-at-Risk |
| `get_var_compare` | 三方法 VaR 對比 |
| `get_positions` | 持倉明細 |
| `get_nav_history` | NAV 歷史 |
| `sector_overview` | 市場行業概覽（SKILL.md） |
| `knowledge_search` | **RAG 知識庫搜索**（新增） |

## 環境變量

```bash
ANTHROPIC_API_KEY=     # 必填，Layer 1 主模型
OPENAI_API_KEY=        # 可選，Layer 2 Embedding
REDIS_URL=redis://localhost:6379/0  # Layer 4 狀態機
PROCESSING_API_URL=http://localhost:8001
AGENT_TOOL_MODE=direct  # direct | via_backend
```
