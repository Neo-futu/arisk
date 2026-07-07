# ARISK 測試指南（Agent 與非 Agent 交互）

> 統一本地啟動與端口約定請優先參考：`docs/local_development_stack.md`。

## 1. 目標

本指南說明如何測試以下層級，並驗證在 Agent 與非 Agent（Direct Query）兩種模式下的交互可用性：

- 2_processing
- 3_skills
- 4_mcp
- 5_deploy
- 6_entry

本次已在本地完成一輪實測，日期：2026-07-06。

---

## 2. 前置條件

### 2.1 基礎服務

- PostgreSQL 已啟動，且包含 fsi schema
- 測試基金資料可用（示例：BHMMF001）

### 2.2 Python 依賴（本次測試最小集合）

執行：

pip install fastapi uvicorn anthropic mcp redis

---

## 3. 啟動服務

### 3.1 啟動 2_processing API

PowerShell：

$env:DATABASE_URL='postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk'; $env:PROCESSING_API_KEY='internal_key_change_me'; uvicorn 2_processing.api.main:app --host 127.0.0.1 --port 8001

### 3.2 啟動 6_entry Web API（內部入口）

PowerShell：

$env:PROCESSING_API_URL='http://127.0.0.1:8001'; $env:PROCESSING_API_KEY='internal_key_change_me'; uvicorn 6_entry.web.app:app --host 127.0.0.1 --port 8010

### 3.3 啟動 6_entry React 前端（獨立目錄）

PowerShell：

cd 6_entry/frontend
copy .env.example .env
npm install
npm run dev

前端預設訪問 `http://localhost:5173`，對外 API 走 root backend（`http://127.0.0.1:8000`）。

---

## 4. 分層測試步驟

## 4.1 2_processing（Py 腳本測試）

使用現有測試腳本：

python 2_processing/test/test_var_three_methods.py --fund-id BHMMF001 --as-of-date 2026-06-25 --database-url postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk --min-observations 30

本次測試結果（節選）：

- HISTORICAL_SIMULATION: VaR(%NAV)=0.0201%
- MONTE_CARLO: VaR(%NAV)=0.0232%
- DISTRIBUTION_FORMULA: VaR(%NAV)=0.0226%

判定：通過

---

## 4.2 3_skills（技能完整性檢查）

執行檢查（PowerShell）：

@'
from pathlib import Path
root=Path(r'd:/vsproject/arisk')
checks=[
  root/'3_skills/skills/var-analysis/SKILL.md',
  root/'3_skills/skills/risk-analysis/SKILL.md',
  root/'3_skills/commands/var.md',
]
for p in checks:
  txt=p.read_text(encoding='utf-8')
  print(p.relative_to(root), p.exists(), 'historical' in txt and 'monte_carlo' in txt and 'distribution' in txt)
'@ | python -

本次測試結果：

- var-analysis/SKILL.md：存在，三方法關鍵詞存在
- risk-analysis/SKILL.md：存在，引用 var-analysis 三方法策略
- commands/var.md：存在，包含三方法命令示例

判定：通過

---

## 4.3 4_mcp（內部 MCP 工具測試）

使用 dispatch 直接驗證 get_var_three_methods（PowerShell）：

@'
import asyncio, importlib, asyncpg
m = importlib.import_module('4_mcp.internal.internal_mcp_server')
async def main():
  conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/postgres')
  out = await m._dispatch('get_var_three_methods', {
    'fund_id':'BHMMF001', 'as_of_date':'2026-06-25',
    'confidence':0.99, 'lookback_days':252,
    'min_observations':30, 'simulations':3000, 'currency':'HKD'
  }, conn)
  print(out['fund_id'], len(out['results']))
  await conn.close()
asyncio.run(main())
'@ | python -

本次測試結果：

- 返回 fund_id=BHMMF001
- 返回 results=3（三方法齊全）

判定：通過

---

## 4.4 5_deploy（orchestrator risk-only）

執行：

$env:PROCESSING_API_URL='http://127.0.0.1:8001'; $env:PROCESSING_API_KEY='internal_key_change_me'; python 5_deploy/orchestrate.py BHMMF001 2026-06-25 --risk-only

本次測試結果（節選）：

- status = risk_only_completed
- 包含 exposure + var_results + max_var_pct_nav
- max_var_pct_nav = 0.023199...

判定：通過

---

## 4.5 6_entry（Agent 與非 Agent 交互）

### A. 非 Agent（Direct Query）

請求：

GET http://127.0.0.1:8000/query/risk/var-compare/BHMMF001?as_of_date=2026-06-25

本次測試結果：

- HTTP 200
- results=3
- max_var_pct_nav=0.0232

### B. Agent Skill 模式

瀏覽器頁面（前端）：

GET http://127.0.0.1:8000/agent/skills/var-analysis

API 請求（程序調用）：

POST http://127.0.0.1:8000/agent/skills/var-analysis
Body:
{
  "fund_id": "BHMMF001",
  "as_of_date": "2026-06-25"
}

本次測試結果：

- HTTP 200
- results=3
- 返回 summary（技能格式文本）

判定：通過

---

## 5. 交互使用方式（平台視角）

## 5.1 非 Agent（低延遲查詢）

建議場景：日常巡檢、前端表格、固定口徑查詢。

- 入口：6_entry Direct Query
- 典型路由：
  - GET /query/risk/var-compare/{fund_id}
  - GET /query/risk/var/{fund_id}

調用鏈路：

6_entry (direct_query) -> 2_processing /risk/var

## 5.2 Agent（技能化分析）

建議場景：需要摘要文本、方法對比解讀、可拓展到審核工作流。

- 入口：6_entry Agent Skill
- 典型路由：
  - POST /agent/skills/var-analysis

調用鏈路：

6_entry (agent_mode var skill) -> 2_processing /risk/var（三次） -> skill summary

## 5.3 進階 Agent 編排

- 入口：5_deploy orchestrator
- 測試命令：
  - python 5_deploy/orchestrate.py BHMMF001 2026-06-25 --risk-only

---

## 6. 通過矩陣（本次實測）

- 2_processing VaR 三方法腳本：通過
- 3_skills VaR 技能資產檢查：通過
- 4_mcp get_var_three_methods：通過
- 5_deploy orchestrator --risk-only：通過
- 6_entry Direct Query + Agent Skill：通過

---

## 7. 常見問題

1. 2_processing 起不來
- 檢查 redis、fastapi、uvicorn 是否已安裝
- 檢查 DATABASE_URL 是否指向可連線的 postgres

2. 6_entry 查詢失敗
- 先確認 2_processing 已啟動在 127.0.0.1:8001
- 確認 PROCESSING_API_KEY 一致

3. orchestrator 測試失敗
- 使用 --risk-only 可先驗證前半鏈路
- 若要完整流程，需確保 review API 與報告生成依賴都可用
