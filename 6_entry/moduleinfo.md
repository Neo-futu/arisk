# 6_entry — 入口層

## 模塊定位

FSI 風控業績平台六層架構的**第六層（最頂層）**，是所有用戶和外部系統的**統一接入點**。提供四種入口形式：Web Chat UI、Excel 插件、Python CLI、以及 Direct API。同一業務功能根據需求複雜度自動路由至 Agent 模式或 Direct Query 模式。

```
用戶 / 外部系統
    ↓   ↓   ↓   ↓
  Web  Excel CLI  API
【6_entry】  ← 本層（統一入口）
    ├── Agent 模式  →  5_deploy/orchestrate
    └── Direct Query →  2_processing API
```

---

## 目錄結構

```
6_entry/
├── web/                        Web 入口（FastAPI）
│   ├── app.py                    應用主體（CORS/路由/靜態文件）
│   ├── static/
│   │   └── index.html            前端頁面（Chat UI + 報表瀏覽器）
│   └── routers/
│       ├── agent_mode.py         Agent 模式路由（複雜任務）
│       ├── direct_query.py       Direct Query 路由（標準查詢）
│       ├── review_ui.py          人工審核收件箱 UI
│       └── op_logs_ui.py         操作日誌查看界面
├── cli/
│   └── run.py                  Python CLI（終端直接觸發計算）
└── excel/
    └── bootstrap/
        └── bootstrap.md         Excel 環境初始化命令定義
```

---

## 四種入口詳解

### 1. Web Chat UI（`web/`）

**啟動：** `uvicorn 6_entry.web.app:app --port 8000`

**路由體系：**

| 前綴 | 模式 | 適用場景 |
|---|---|---|
| `POST /agent/analyze` | **Agent 模式** | 複雜分析、需推理判斷 |
| `POST /agent/report` | **Agent 模式** | 多步驟報告生成 |
| `GET /query/risk/{fund_id}` | **Direct Query** | 標準風控查詢（低延遲） |
| `GET /query/holdings/{fund_id}` | **Direct Query** | 持倉查詢 |
| `GET /query/performance/{fund_id}` | **Direct Query** | 業績查詢 |
| `GET /review/inbox` | 審核 UI | 待審核請求列表 |
| `POST /review/{id}/decide` | 審核 UI | 批准/拒絕審核請求 |
| `GET /op-logs` | 日誌 UI | 操作日誌查看 |

**Agent 模式 vs Direct Query 路由決策：**
```
請求 → 意圖分析
  ├── 標準查詢（確定性）→ Direct Query → 2_processing API（毫秒級）
  └── 複雜分析（需推理）→ Agent 模式 → 5_deploy orchestrator（秒級）
```

**前端（`static/index.html`）：**
- Chat 對話界面（輸入框 + 消息流）
- 報表結果展示（支持表格/圖表）
- 審核通知徽章

---

### 2. Excel 插件（`excel/`）

**入口：** Excel 中通過 Claude Code 插件調用

**初始化流程（`/bootstrap`）：**
1. 檢測 MCP 連接狀態（`fsi-gateway` / `internal-db` / `wind`）
2. 載入可用技能（`risk-analysis` / `mmf-compliance` / `performance-report` / `xlsx-report`）
3. 確認 Processing API 健康狀態
4. 返回可用命令清單

**可用快捷命令：**

| 命令 | 說明 |
|---|---|
| `/risk [fund_id] [date]` | 風控快照（WAM/WAL/VaR/合規狀態） |
| `/compliance [fund_id]` | MMF 合規核查報告 |
| `/positions [fund_id] [date]` | 持倉明細（按資產類別） |
| `/performance [fund_id]` | 業績歸因分析 |

**安全約束：**
- Excel 寫入（填充單元格/生成工作表）僅由 write-holder 子 Agent 執行
- 持倉數據標記為機密，禁止截圖分享

---

### 3. Python CLI（`cli/run.py`）

**適用場景：** 運維、批量任務、腳本化調用、調試

**用法：**
```bash
# 風控快照
python 6_entry/cli/run.py risk --fund BHMMF --date 2026-06-25

# 持倉列表
python 6_entry/cli/run.py positions --fund BHMMF

# 執行 ETL
python 6_entry/cli/run.py etl --date 2026-06-25

# 觸發每日計算
python 6_entry/cli/run.py compute --all-funds
```

**輸出格式：**
```
============================================================
  風控快照 — BHMMF · 2026-06-25
============================================================
  總 NAV:          HKD 2,704,500,000
  WAM:             52.3 天  (限額: ≤60天) ✅
  WAL:             68.1 天  (限額: ≤120天) ✅
  每日流動資產:     18.5%  (下限: ≥7.5%) ✅
  每週流動資產:     29.6%  (下限: ≥15%) ✅
  最大單一發行人:   18.5%  (上限: ≤20%) ✅
  合規狀態:        ✅ 全部合規
============================================================
```

直接調用 `2_processing` API（`PROCESSING_API_URL`），無需 Agent。

---

### 4. Direct API（`web/routers/direct_query.py`）

**適用場景：** 外部系統集成、前端 SPA 直接調用、第三方報表工具

**認證：** `X-API-Key` Header（`WEB_SECRET_KEY` 環境變量）

**核心接口：**

```
GET  /query/risk/{fund_id}                   風控快照
GET  /query/risk/{fund_id}/exposure          暴露明細
GET  /query/holdings/{fund_id}/{asset_class} 持倉數據
GET  /query/performance/{fund_id}            業績指標
GET  /query/market/fx-rates                  匯率
GET  /query/market/yield-curves              收益率曲線
```

所有接口轉發到 `2_processing` API，Entry 層做認證、日誌、響應格式標準化。

---

## 人工審核收件箱

`review_ui.py` 提供審核員的工作界面：

```
GET  /review/inbox          待審核請求列表（按優先級排序）
GET  /review/{id}           審核請求詳情（含小富AI建議）
POST /review/{id}/claim     認領審核任務
POST /review/{id}/approve   批准
POST /review/{id}/reject    拒絕（附拒絕原因）
POST /review/{id}/escalate  升級
```

**小富 AI 審核建議展示：**
- 風險等級（LOW / MEDIUM / HIGH / CRITICAL）
- 建議操作（APPROVE / REJECT / ESCALATE / REQUIRE_HUMAN）
- 分析摘要（觸發原因、潛在風險、整改建議）
- 審核員可採納建議或覆蓋

---

## 與其他層的交互

| 方向 | 交互說明 |
|---|---|
| **→ `5_deploy`** | Agent 模式請求轉發至 orchestrator |
| **→ `2_processing`** | Direct Query 直接調用計算 API |
| **→ `3_skills`** | Excel/Web Chat 使用技能庫命令 |
| **← 用戶** | Web 瀏覽器 / Excel / Terminal / API 客戶端 |

---

## 環境變量

| 變量 | 說明 |
|---|---|
| `WEB_PORT` | Web 服務端口，默認 8000 |
| `WEB_SECRET_KEY` | Web API 認證密鑰 |
| `CORS_ORIGINS` | 允許的跨域來源（逗號分隔） |
| `PROCESSING_API_URL` | 下游計算服務地址 |
| `PROCESSING_API_KEY` | 計算服務認證密鑰 |
| `ANTHROPIC_API_KEY` | Claude API（Agent 模式） |

---

## 快速啟動

```bash
# 啟動 Web 入口
uvicorn 6_entry.web.app:app --host 0.0.0.0 --port 8000 --reload

# CLI 查看風控快照
python 6_entry/cli/run.py risk --fund BHMMF

# API 文檔
# 訪問 http://localhost:8000/docs
```
