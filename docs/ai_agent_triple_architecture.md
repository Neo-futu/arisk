# ARISK 三層業務 AI 架構

ARISK 平台由三個層面的業務 AI 組成，各自定位清晰，協同工作。

---

## 三層定位

```
┌──────────────────────────────────────────────────────────────────┐
│  Platform Agent（系統層業務 AI）                                    │
│  自動化運行平台業務：ETL/風控快照/合規監控/報表生成                    │
│  代碼：platform_agent/                                            │
│  端點：6_entry:8010/platform/v1/stream                            │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  3_skills（專家級業務技能）                                          │
│  領域專家編寫的業務知識和操作技能：VaR/合規/審核/報告流程              │
│  代碼：3_skills/skills/*.md                                       │
│  被索引到：fsi.knowledge_chunk（知識庫）                            │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  aiagent / Chat Agent（用戶層業務 AI）                              │
│  每個用戶的個人 AI 助理：對話式風控分析/合規核查/報告生成              │
│  代碼：aiagent/                                                   │
│  端點：6_entry:8010/agent/v2/stream                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三層關係圖

```
Platform Agent                    3_skills                    aiagent
（系統層業務 AI）                 （專家業務技能）              （用戶層業務 AI）
      │                               │                            │
      │ 自動調用                       │                            │
      ├─ trigger_celery_task          │                            │
      ├─ check_system_health          │                            │
      └─ knowledge_search ───────────┼──────── knowledge_search ──┤
                                     │                            │
                                     │ 索引                        │ execute_skill
                                     ▼                            ▼
                              fsi.knowledge_chunk（知識庫）
                              （BM25/pgvector 搜索）
                                     │
                              Expert Chat 也可寫入
                                     │
                              3_skills/skills/*.md ←─ 開發者編寫
                                                  ←─ Expert Chat 生成
```

---

## 各層四層架構對比

### Platform Agent L1-L4

| 層 | 實現 | 說明 |
|---|---|---|
| L1 Brain | scheduler/monitor/etl-coordinator | 任務協調、異常識別、告警判斷 |
| L2 Memory | fsi 業務數據庫 + 3_skills 知識庫 | 業務數據 + 合規閾值知識 |
| L3 Tools | 9個系統工具 + knowledge_search | 運維操作 + 業務知識查詢 |
| L4 Orchestration | Celery Beat + Redis + 服務網格 | 定時調度 + 任務隊列 |

### 3_skills L1-L4（知識資產層）

| 層 | 實現 | 說明 |
|---|---|---|
| L1 知識組織 | SKILL.md frontmatter（name/triggers/tools） | 技能元數據，供 AI 識別觸發 |
| L2 知識存儲 | 文件 + fsi.knowledge_chunk（索引後） | SKILL.md 文件 + 數據庫索引 |
| L3 知識訪問 | knowledge_search + execute_skill 工具 | AI 搜索引用 + 按名稱執行 |
| L4 知識管理 | knowledge_indexer + Expert Chat + API | 索引/更新/添加技能 |

### aiagent L1-L4

| 層 | 實現 | 說明 |
|---|---|---|
| L1 Brain | planner + runner + reflector | 任務規劃 + ReAct + 質量評估 |
| L2 Memory | context_manager + vector_store + agent_episode | 短期+長期+情景記憶 |
| L3 Tools | 11個業務工具（含 knowledge_search/execute_skill）| 業務查詢 + 3_skills 技能調用 |
| L4 Orchestration | supervisor + task_state + SSE | 多Agent路由 + 狀態機 + 流式輸出 |

---

## 知識庫（fsi.knowledge_chunk）三個來源

```
來源一：3_skills/skills/*.md（專家業務技能）
  → knowledge_indexer.py 分塊索引
  → source = "skill_doc"

來源二：aiagent/agents/*.md（Agent 角色知識）
  → knowledge_indexer.py 分塊索引
  → source = "agent_prompt"

來源三：Expert Chat 直接輸入（專家對話知識）
  → POST /api/v1/knowledge/ingest
  → source = "expert_chat"
  → 可同時保存為 3_skills/skills/*.md 文件
```

**搜索**：`knowledge_search` 工具 → BM25 全文搜索（pgvector 可選）
**調用**：`execute_skill(skill_name)` → 加載 SKILL.md 執行指南

---

## 3_skills 技能添加方式

```
方式一：直接編寫 SKILL.md（開發者 + 領域專家）
  mkdir 3_skills/skills/credit-analysis
  vim 3_skills/skills/credit-analysis/SKILL.md
  python -m aiagent.memory.knowledge_indexer

方式二：Expert Chat 生成（領域專家自助）
  訪問 http://localhost:5173/expert
  描述業務知識 → AI 提取 → 點擊「保存為 3_skills 技能」
  → 自動生成 3_skills/skills/*.md + 索引入庫

方式三：API 直接上傳
  POST /api/v1/knowledge/ingest（純文本）
  POST /api/v1/knowledge/ingest-file（PDF/Word/MD）
```

---

## 系統目錄結構

```
fsi-risk-platform/
│
├── platform_agent/          系統層業務 AI
│   ├── agents/              scheduler / monitor / etl-coordinator
│   ├── engine/              platform_runner.py + system_tools.py
│   └── skills/              系統運維操作手冊（私有，不索引）
│
├── 3_skills/                專家級業務技能
│   ├── skills/              SKILL.md 技能文件（被索引入知識庫）
│   │   ├── mmf-compliance/  SFC 合規專家技能
│   │   ├── risk-analysis/   風控分析師技能
│   │   ├── var-analysis/    量化分析師技能
│   │   └── ...
│   └── commands/            CLI 命令定義
│
├── aiagent/                 用戶層業務 AI
│   ├── agents/              10個業務 Agent 角色提示
│   ├── engine/              runner/planner/reflector/tools/stream
│   ├── memory/              context_manager/vector_store/knowledge_indexer
│   ├── orchestrator/        supervisor/task_state
│   └── skills/              Chat Agent 操作指南（私有，不索引）
│
└── 知識庫（在數據庫中）
    ├── fsi.knowledge_document  文檔目錄
    └── fsi.knowledge_chunk     分塊文本（BM25/向量可搜索）
```

---

## 啟動命令

```bash
# 全部服務
python scripts/dev.py

# 知識庫初始化（首次運行）
python -m aiagent.memory.knowledge_indexer

# Platform Agent 自動化調度
celery -A 2_processing.workers.celery_app worker --loglevel=info
celery -A 2_processing.workers.celery_app beat   --loglevel=info

# 訪問入口
open http://localhost:5173/chat    # 用戶層 Chat Agent
open http://localhost:5173/expert  # Expert Chat（添加 3_skills 技能）
```
