# ARISK 知識庫建立指南

知識庫是 Chat Agent 的「記憶」—— 存儲業務領域知識，讓 Agent 能夠引用正確的業務知識回答用戶問題。

---

## 一、知識庫架構

```
知識輸入（3種方式）
    ↓                ↓                ↓
後台開發           Expert Chat      文件上傳
SKILL.md           專家對話提取      PDF/Word/MD
    ↓                ↓                ↓
knowledge_indexer.py / POST /api/v1/knowledge/ingest
    ↓
fsi.knowledge_document（文檔索引）
fsi.knowledge_chunk（分塊文本 + 向量/BM25）
    ↓
knowledge_search 工具（Chat Agent 調用）
    ↓
Chat Agent 引用知識回答用戶問題
```

### 搜索機制

| 條件 | 搜索方式 | 說明 |
|------|---------|------|
| 安裝了 pgvector | 向量（60%）+ BM25（40%）| 語義理解更準確 |
| **未安裝 pgvector（現狀）** | **BM25 全文搜索** | **完全可用，適合關鍵詞搜索** |

**當前狀態**：PostgreSQL 18.4，pgvector 未安裝，使用 BM25。已索引 17 個文檔，41 個文本塊。

---

## 二、知識庫建立方式

### 方式一：後台開發 SKILL.md（系統技能知識）

適合：開發者為系統添加標準業務知識模板。

**步驟：**

```bash
# 1. 在對應目錄創建技能文檔
# 系統層（Platform Agent 使用）：
mkdir 3_skills/skills/new-skill-name
vim 3_skills/skills/new-skill-name/SKILL.md

# 用戶層（Chat Agent 使用）：
mkdir aiagent/skills/category/new-skill-name
vim aiagent/skills/category/new-skill-name/SKILL.md

# 2. SKILL.md 格式模板：
cat > 3_skills/skills/credit-analysis/SKILL.md << 'EOF'
---
name: credit-analysis
category: analysis
layer: platform        # platform | chat
description: 香港銀行業 CD 發行人信用分析技能
tools: get_exposure, get_positions, knowledge_search
version: "1.0"
---

# 信用分析技能

## 觸發條件
- 「信用分析」/ 「CD 發行人評級」/ 「credit analysis」

## 核心知識
- 香港主要銀行評級（匯豐/恒生/中銀/渣打）
- CD 期限與信用溢價關係
- HKMA 監管要求

## 執行步驟
1. 確認發行人名單
2. 查詢信用評級數據
3. 對比行業基準
4. 輸出評估結論
EOF

# 3. 重新索引（更新到知識庫）
python -m aiagent.memory.knowledge_indexer

# 或只索引新文件
python -m aiagent.memory.knowledge_indexer \
  --path 3_skills/skills/credit-analysis/SKILL.md \
  --source skill_doc \
  --doc-type skill
```

**索引後驗證：**
```python
import asyncio
from aiagent.memory.vector_store import hybrid_search

async def test():
    results = await hybrid_search("CD 發行人信用評級")
    for r in results[:3]:
        print(r['title'], r['score'])

asyncio.run(test())
```

---

### 方式二：Expert Chat（前台專家添加知識）

適合：業務專家（非開發者）通過界面分享領域知識和實戰經驗。

**訪問入口：** `http://localhost:5173/expert`

**操作流程：**

```
1. 填寫「技能主題」（如：MMF 信用風險評估方法）
2. 選擇層級：用戶業務技能 / 系統業務技能
3. 在對話框中描述業務知識：
   - 「我們評估 CD 發行人信用時，會看 Moody's/S&P 評級、HKMA 授權類別...」
   - 「遇到評級下調時，我們的處理流程是...」
   - 「香港本地銀行的特殊考慮因素...」
4. 點擊「從對話中提取技能」→ AI 整理成 SKILL.md 格式
5. 審查提取結果，可手動修改
6. 點擊「保存到知識庫」→ 立即生效
```

**Expert Chat 特點：**
- 無需會寫代碼，自然語言描述即可
- AI 自動提取結構化知識點
- 可審查後再保存，確保質量
- 索引後立即可被所有用戶的 Chat Agent 使用

---

### 方式三：文件上傳（直接攝取文檔）

適合：快速導入現有文件（SFC 守則、基金章程、分析報告等）。

**通過 Expert Chat 界面上傳：**
1. 訪問 `http://localhost:5173/expert`
2. 右側「上傳文件到知識庫」區域
3. 支持：`.pdf` `.docx` `.md` `.txt`
4. 上傳後自動索引，顯示索引塊數

**通過 CLI 上傳：**
```bash
# 上傳 SFC 守則 PDF（需先安裝 pdfminer.six）
pip install pdfminer.six
python -m aiagent.memory.knowledge_indexer \
  --path "docs/SFC_MMF_Code_8.2.pdf" \
  --source sfc_regulation \
  --doc-type regulation

# 上傳 Word 文件（需先安裝 python-docx）
pip install python-docx
python -m aiagent.memory.knowledge_indexer \
  --path "docs/fund_prospectus.docx" \
  --source fund_doc \
  --doc-type prospectus
```

**通過 API 上傳：**
```bash
# 文本內容直接攝取
curl -X POST http://localhost:8000/api/v1/knowledge/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "SFC 守則 WAL 上限規定",
    "content": "根據《單位信託及互惠基金守則》第8.2.3條，貨幣市場基金的加權平均有效期（WAL）不得超過120天...",
    "source": "sfc_regulation",
    "doc_type": "regulation"
  }'

# 文件上傳
curl -X POST http://localhost:8000/api/v1/knowledge/ingest-file \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@SFC_code.pdf" \
  -F "source=sfc_regulation" \
  -F "doc_type=regulation"
```

---

## 三、知識庫管理

### 查看已索引文檔

```bash
# API
curl http://localhost:8000/api/v1/knowledge/documents \
  -H "Authorization: Bearer $TOKEN"

# 數據庫直查
psql -d fsi_risk -c "
SELECT title, source, chunk_count, has_vectors, created_at
FROM fsi.knowledge_document
ORDER BY created_at DESC;"
```

### 刪除過時文檔

```bash
# API（需超管權限）
curl -X DELETE http://localhost:8000/api/v1/knowledge/{document_id} \
  -H "Authorization: Bearer $TOKEN"
```

### 重新全量索引

```bash
# 清空並重新索引所有 3_skills 和 agents
psql -d fsi_risk -c "DELETE FROM fsi.knowledge_document WHERE source IN ('skill_doc', 'agent_prompt')"
python -m aiagent.memory.knowledge_indexer
```

---

## 四、pgvector 安裝（升級向量搜索）

當前使用 BM25 全文搜索已可正常工作。若需升級到向量語義搜索：

### Windows（PostgreSQL 18）
```
1. 訪問：https://github.com/pgvector/pgvector/releases
2. 下載對應 PostgreSQL 版本的安裝包
3. 執行安裝
4. 重啟 PostgreSQL 服務
5. 執行：psql -d fsi_risk -c "CREATE EXTENSION vector"
6. 重新執行索引（自動生成嵌入向量）：
   python -m aiagent.memory.knowledge_indexer
```

### Embedding 模型說明

| 模型 | 需要 | 維度 | 質量 |
|------|------|------|------|
| OpenAI text-embedding-3-small | OPENAI_API_KEY | 1536d | 最佳 |
| sentence-transformers | pip install sentence-transformers | 384d→padding 1536d | 良好（本地） |
| 無模型 | 無 | — | 使用 BM25（當前狀態）|

---

## 五、知識搜索效果測試

在 Chat Agent 中測試知識搜索效果：

**對話測試：**
```
用戶: SFC 守則對 MMF 的 WAL 上限是多少？
Agent → knowledge_search("WAL SFC 守則要求")
     → 返回：「根據第 8.2.3 條，WAL ≤ 120 天」
     → 回答：「根據 SFC《單位信託及互惠基金守則》第 8.2.3 條規定，
              MMF 的加權平均有效期（WAL）不得超過 120 天...」
```

**直接 API 測試：**
```python
import asyncio
from aiagent.memory.vector_store import hybrid_search

async def test_knowledge():
    tests = [
        "SFC MMF 合規要求",
        "VaR 歷史模擬法",
        "GL 對賬步驟",
    ]
    for q in tests:
        results = await hybrid_search(q, top_k=2)
        print(f"查詢: {q}")
        for r in results:
            print(f"  [{r['title']}] {r['content'][:80]}")
        print()

asyncio.run(test_knowledge())
```

---

## 六、知識來源標識

| source 值 | 說明 | 索引方式 |
|-----------|------|---------|
| `skill_doc` | 3_skills/*.md（系統技能知識）| CLI indexer |
| `agent_prompt` | aiagent/agents/*.md（Agent 規則）| CLI indexer |
| `expert_chat` | 專家對話提取的知識 | Expert Chat 界面 |
| `sfc_regulation` | SFC 守則等法規文件 | CLI / API 上傳 |
| `fund_doc` | 基金章程、招股書 | CLI / API 上傳 |
| `manual` | 操作手冊、內部文件 | CLI / API 上傳 |
