# 3_skills — 專家級業務技能庫

**定位**：ARISK 平台的**業務領域專家技能**，由風控、合規、量化等領域專家編寫，
將專業知識和操作流程編碼為 AI 可執行的結構化技能。

> 類比：如果把 AI Agent 比作員工，3_skills 就是這個員工的**資深業務手冊**——
> 由行業專家親自撰寫，說明具體怎麼做 VaR 分析、怎麼核查 SFC 合規，精確到每一步調用哪個工具。

---

## 三層業務 AI 中的位置

```
Platform Agent（系統層業務 AI）
  ↕ 自動運維時引用 3_skills 知識做業務判斷

3_skills（專家級業務技能）← 本模塊
  - 領域專家編寫的業務 SOP（VaR計算/合規核查/業績分析...）
  - 索引入知識庫後，AI 可搜索引用

aiagent / Chat Agent（用戶層業務 AI）
  ↕ 可搜索 3_skills 知識
  ↕ 需要即時數據時通過 4_mcp 取得外部 / 內部資料

注意：3_skills 現在支持獨立 skill-agent 編排運行，
與 aiagent 的 execute_skill 工具解耦，屬於兩套 agent runtime。
```

---

## 技能列表（按業務領域）

### 風控類
| 技能 | 說明 |
|------|------|
| `risk-analysis` | MMF 風控全面分析：WAM/WAL/VaR/集中度/SFC合規 |
| `var-analysis` | VaR 三方法詳解：歷史模擬/蒙特卡洛/參數法，含 CVaR |

### 合規類
| 技能 | 說明 |
|------|------|
| `mmf-compliance` | SFC 守則第8.2章完整核查：期限/集中度/流動性/信貸質素 |
| `human-review` | 人工審核觸發條件與流程 |

### 報表類
| 技能 | 說明 |
|------|------|
| `performance-report` | 業績報告生成：NAV/收益歸因/基準對比 |
| `xlsx-report` | Excel 報表生成規範和數據映射 |

---

## 技能文件結構

每個 SKILL.md 由三部分組成，對應「知識→步驟→輸出」：

```markdown
---
name: var-analysis        ← 技能 ID（execute_skill 工具調用時使用）
category: risk
description: 一句話描述
tools: get_var, get_var_compare   ← 需要調用的業務工具
triggers: [VaR, 歷史模擬法, ...]  ← 觸發關鍵詞
---

## 業務知識         ← 領域專家的知識（Why/What）
SFC 規定、計算原理、適用場景...

## 執行步驟         ← AI 執行指南（How）
Step 1: 調用 get_var(fund_id, ...)
Step 2: 對比三種方法...
Step 3: 按閾值判斷...

## 輸出格式         ← 標準化模板（Output）
| 方法 | VaR | CVaR | ... |
```

---

## 技能如何被使用

### Chat Agent 使用方式

**方式一：knowledge_search（搜索引用）**
```
用戶問：「SFC 對 WAL 的要求是多少？」
→ Agent 自動調用 knowledge_search("WAL SFC 守則要求")
→ 從 fsi.knowledge_chunk 返回 mmf-compliance 中的相關段落
→ 回答：「根據 SFC 守則第8.2(f)條，WAL ≤ 120 天」
```

### 3_skills 獨立 Agent 使用方式（推薦）

3_skills 提供獨立編排 runtime：

```
python 3_skills/commands/run_skill_agent.py --query "請做 BHMMF001 合規核查" --skill mmf-compliance
```

編排模塊位置：

- `3_skills/runtime/skill_registry.py`：技能註冊與匹配
- `3_skills/runtime/orchestrator.py`：任務規劃與執行計劃輸出
- `3_skills/commands/run_skill_agent.py`：CLI 調用入口

該 runtime 不依賴 aiagent，不接入 aiagent 的 execute_skill。

### Platform Agent 使用方式

```
系統監控員（monitor）查詢合規閾值：
→ 調用 knowledge_search("SFC WAM WAL 閾值")
→ 獲取 risk-analysis SKILL.md 中的閾值定義
→ 與快照數據對比，判斷是否需要告警
```

### 4_mcp 使用方式

`3_skills` 的核心價值是「業務 SOP 與判斷規則」，不是自己去做底層連接。
當技能需要最新行情、評級、持倉、NAV 或其他內外部資料時，應優先透過 `4_mcp/gateway` 取數，再由技能步驟做業務判斷。

```
技能需要即時行情 → 4_mcp/wind
技能需要內部持倉 / 快照 → 4_mcp/internal
技能需要統一入口 / 授權 → 4_mcp/gateway
```

---

## 如何添加新技能

### 方式一：直接編寫（開發者 + 領域專家）
```bash
mkdir 3_skills/skills/credit-analysis
vim 3_skills/skills/credit-analysis/SKILL.md  # 按上方格式編寫

# 索引入知識庫
python -m aiagent.memory.knowledge_indexer \
  --path 3_skills/skills/credit-analysis/SKILL.md \
  --source skill_doc --doc-type skill
```

### 方式二：Expert Chat 生成（推薦）
訪問 `http://localhost:5173/expert`：
1. 領域專家用自然語言描述業務知識
2. AI 自動提取結構化 SKILL.md 格式
3. 點擊「保存為 3_skills 技能」→ 生成 `3_skills/skills/*.md` 文件並索引入庫

---

## 索引機制（技能如何進入知識庫）

```
3_skills/skills/mmf-compliance/SKILL.md
        ↓ aiagent/memory/knowledge_indexer.py
fsi.knowledge_document（文檔記錄）
fsi.knowledge_chunk（分塊文本，BM25/向量可搜索）
        ↓ knowledge_search 工具 / execute_skill 工具
Chat Agent 和 Platform Agent 在業務對話中引用
```

**當前索引狀態**：6 個技能已索引（41 個文本塊，BM25 搜索可用）
