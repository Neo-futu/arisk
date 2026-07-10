# aiagent — 用戶層業務 AI

**定位**：ARISK 平台的**用戶層業務 AI**，每個登錄用戶都有自己的 AI 助理，
通過自然語言對話完成日常風控、合規、報告等業務工作。

> **三層業務 AI 的位置**：
> - Platform Agent：系統層業務 AI（自動運維）
> - 3_skills：專家級業務技能（領域知識編碼）
> - **aiagent（本模塊）：用戶層業務 AI（個人對話助理）** ← 你在這裡

---

## 用戶能做什麼

```
用戶（風控主任）問：「BHMMF001 今天的 WAM 多少天，合規嗎？」
          ↓
Chat Agent（risk-analyst 角色）：
  L1 Brain：理解意圖，計劃調用 get_exposure 工具
  L2 Memory：從 3_skills 知識庫搜索 SFC WAM 閾值（≤60天）
  L3 Tools：調用 get_exposure("BHMMF001", today) → 獲取 WAM 實際值
  L4 Output：「WAM = 52天，合規（SFC 上限 60天）」

用戶（合規審查員）問：「對 BHMMF001 做完整合規核查」
          ↓
Chat Agent 調用 execute_skill("mmf-compliance", "BHMMF001", today)
  → 加載 3_skills/mmf-compliance/SKILL.md 的執行步驟
  → 依次核查 WAM/WAL/DLA/WLA/集中度...
  → 輸出標準格式合規報告
```

---

## 四層架構

```
+------------------------------------------------------------------+
| L1: 控制與規劃層 (Brain)                                           |
|  planner.py   — 複雜任務拆解（CoT/Plan-and-Execute）               |
|  runner.py    — 多模型 ReAct 循環（max 10 輪工具調用）              |
|  reflector.py — 輸出質量評估與自我反思                              |
|  用戶個性化：iam.user_agent_config（默認模型/角色/自定義指令）         |
+------------------------------------------------------------------+
| L2: 記憶與知識層 (Memory)                                          |
|  短期記憶：context_manager.py（滑動窗口40輪，自動摘要壓縮）           |
|  長期記憶：vector_store.py（BM25/pgvector，搜索 3_skills 技能知識） |
|  對話歷史：iam.chat_session / iam.chat_message（持久化）            |
|  情景記憶：iam.agent_episode（成功對話經驗，供未來參考）              |
+------------------------------------------------------------------+
| L3: 工具與技能層 (Tools + Skills)                                  |
|  系統業務工具（11個）:                                              |
|    get_system_info / get_exposure / get_var / get_var_compare    |
|    get_positions / get_nav_history / sector_overview             |
|    knowledge_search / execute_skill                              |
|    generate_report / query_internal_db                           |
|  3_skills 技能庫（通過 execute_skill 工具調用）                     |
|  用戶個人工具（iam.user_custom_tool，用戶自定義 HTTP 工具）           |
+------------------------------------------------------------------+
| L4: 編排與通訊層 (Orchestration)                                   |
|  supervisor.py  — 意圖路由（10個專業 Agent 角色）                   |
|  task_state.py  — Redis 狀態機（QUEUED→DONE）                     |
|  stream.py      — SSE 流式輸出（plan/text/tool_call/reflection）   |
|  端點：6_entry:8010/agent/v2/stream                               |
+------------------------------------------------------------------+
```

---

## 10 個業務 Agent 角色

| Agent | 定位 | 引用的 3_skills 技能 |
|-------|------|-------------------|
| `general` | 通用助理（默認）| 所有技能 |
| `risk-analyst` | 風控分析師 | risk-analysis, var-analysis |
| `compliance-officer` | SFC 合規審查員 | mmf-compliance |
| `fund-reporter` | 基金報表助理 | performance-report, xlsx-report |
| `market-researcher` | 市場研究員 | sector-overview |
| `gl-reconciler` | GL 對賬員 | — |
| `kyc-screener` | KYC 篩查員 | — |
| `statement-auditor` | NAV 報表審計 | — |
| `valuation-reviewer` | 估值審查員 | — |
| `month-end-closer` | 月末結賬助手 | — |

---

## 工具清單（11個）

### 業務查詢工具（調用 2_processing 計算引擎）
| 工具 | 說明 |
|------|------|
| `get_system_info` | 在管基金列表 + 當前日期 |
| `get_exposure` | WAM/WAL/DLA/WLA/SFC 合規狀態 |
| `get_var` | Value-at-Risk（3種方法） |
| `get_var_compare` | 三方法 VaR 對比 |
| `get_positions` | 持倉明細 |
| `get_nav_history` | NAV 歷史 |
| `sector_overview` | 市場行業研究（內置 SKILL.md 技能） |

### 知識庫工具（調用 3_skills + fsi.knowledge_chunk）
| 工具 | 說明 |
|------|------|
| `knowledge_search` | BM25/向量搜索 3_skills 業務知識 |
| `execute_skill` | 按名稱加載並執行 3_skills 專家技能 |

### 平台能力工具
| 工具 | 說明 |
|------|------|
| `generate_report` | 觸發 processing 報表生成 |
| `query_internal_db` | 查詢業務數據庫 |

---

## 用戶個性化

每個用戶可以通過 `iam.user_agent_config` 配置自己的 AI：

```json
{
  "default_agent_id": "risk-analyst",
  "default_model_id": "x-ai/grok-4.20",
  "custom_instructions": "我是博匯基金風控主任，主要關注 BHMMF001，請用簡潔中文回覆",
  "memory_enabled": true,
  "rag_enabled": true
}
```

API：`PUT /api/v1/agent-config/me`

用戶還可以添加個人工具（`iam.user_custom_tool`）：
API：`POST /api/v1/custom-tools/`

---

## 請求流程

```
瀏覽器 /chat
  → POST /api/v1/fsi/agent/v2/stream (backend:8000, JWT)
  → POST /agent/v2/stream (6_entry:8010)
  → stream.py [L1 Planner 複雜任務規劃]
  → runner.py [L1 ReAct 循環 + L2 記憶加載 + 用戶配置注入]
  → execute_tool() [L3 工具調用]
      ├── get_exposure/get_var → processing:8001
      ├── knowledge_search/execute_skill → fsi.knowledge_chunk (3_skills)
      └── 用戶自定義工具 → 用戶指定的 HTTP 端點
  → SSE 事件流回前端
```

---

## 快速開始

```bash
# 啟動全部服務
python scripts/dev.py

# 訪問 Chat 頁面
open http://localhost:5173/chat

# 對話示例
「BHMMF001 今天的 WAM 是多少，符合 SFC 要求嗎？」
「用合規核查技能對 BHMMF001 做完整 SFC 審查」
「計算 99% 置信度的 VaR，三種方法對比」
```
