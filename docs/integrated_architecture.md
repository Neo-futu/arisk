# ARISK — Agent for Risk & Investment Analysis System

**阿雷斯 · 智能風控和投資分析系統**

本文檔以 `full-stack-fastapi-template` 的前後端分離工程方式為參考，定義 ARISK 的整合後結構。目標是同時保留分層能力平台的獨立可運行性，又提供單一、清晰、產品化的 Web 入口。

## 1. 設計原則

1. 根目錄 `frontend/` 是唯一對瀏覽器開放的 Web UI。
2. 根目錄 `backend/` 是唯一對瀏覽器開放的 Web API。
3. `2_processing/` 是唯一業務計算與 SQL 核心。
4. `6_entry/` 保留為內部入口層，承載 Agent / Direct / CLI / Excel，不再直接作為正式 Web 產品入口。
5. `4_mcp/` 僅做能力接入與工具暴露，不承載業務真相。
6. 所有對外 Web 能力應優先經由 `frontend -> backend` 這條主鏈路整合。

## 2. 目錄責任

```text
frontend/            唯一 Web UI（Dashboard + Chat）
backend/             唯一 Web API（JWT / BFF / FSI proxy）
6_entry/             內部入口服務（Agent / Direct / CLI / Excel）
5_deploy/            Agent 編排與部署
4_mcp/               MCP 工具層
3_skills/            Skill / Prompt 資產層
2_processing/        計算、SQL、風控、報表生成核心
1_datastorage/       PostgreSQL / Redis / S3 / schema / migrations
```

### frontend/

- 對應 `full-stack-fastapi-template` 的正式 SPA 前端
- 承載：儀表板、風控、持倉、合規、報表、Agent Chat
- 僅調用 `backend/api/v1/*`
- 不直接調 `2_processing/`，不直接調 `6_entry/`

### backend/

- 對應 `full-stack-fastapi-template` 的正式 FastAPI 後端
- 承載：JWT 認證、用戶管理、BFF 聚合、代理路由
- `/api/v1/fsi/risk/*`、`/api/v1/fsi/positions/*` 代理到 `2_processing/`
- `/api/v1/fsi/agent/*` 代理到 `6_entry/`

### 6_entry/

- 不再承擔對外 Web 首入口
- 內部保留：
  - Agent 路由
  - Direct Query 路由
  - CLI
  - Excel bootstrap
- 可單獨啟動以支持 Agent / Excel / 測試

### 2_processing/

- 唯一風控計算核心
- VaR、暴露、合規、報表數據拼裝和 SQL 應盡量只落在此層
- 其他層不複製計算邏輯

## 3. 推薦服務拓撲

```text
Browser
  ↓ http://localhost:5173
frontend/
  ↓ /api/v1/*
backend/            http://localhost:8000
  ├── /api/v1/fsi/risk/*      → 2_processing  http://localhost:8001
  ├── /api/v1/fsi/positions/* → 2_processing  http://localhost:8001
  └── /api/v1/fsi/agent/*     → 6_entry       http://localhost:8010

6_entry/
  ├── agent routers
  ├── direct routers
  ├── cli
  └── excel bootstrap

5_deploy/ / 4_mcp/ / 3_skills/
  ↓
2_processing/
  ↓
1_datastorage/
```

## 4. 與開源模板的對照

`full-stack-fastapi-template` 提供的核心工程優點包括：

- 前後端分離
- root `backend/` + `frontend/` 為產品主入口
- 文檔集中
- 配置與開發流程清晰

FSI 在此基礎上的擴展是：

- 保留業務分層能力平台（1 到 6 層）
- 增加 `2_processing/` 作為風控核心
- 增加 `4_mcp/` 和 `5_deploy/` 作為 Agent / MCP 能力層
- 增加 `6_entry/` 作為內部入口與多通道接入層

因此，FSI 不是替換這個模板，而是在模板的產品殼之下增加一套專業金融風控能力平台。

## 5. 啟動順序

### Web 產品鏈路

1. 啟動 `2_processing/` on `:8001`
2. 啟動 `6_entry/` on `:8010`
3. 啟動 `backend/` on `:8000`
4. 啟動 `frontend/` on `:5173`

### 非 Web 能力鏈路

1. 啟動 `2_processing/`
2. 啟動 `4_mcp/`
3. 啟動 `5_deploy/` 或 `6_entry/cli`

## 6. 目錄治理規則

1. Web 頁面只新增在 `frontend/src/routes/`
2. 對外 Web API 只新增在 `backend/app/api/routes/`
3. 計算邏輯與 SQL 只新增在 `2_processing/`
4. `6_entry/` 不再新增正式產品前端頁面
5. `6_entry/frontend/` 僅作過渡性測試或實驗用，不作正式入口

## 7. 近期收斂建議

1. 將 `backend` 的設定模型擴展為統一接入 `PROCESSING_API_URL`、`ENTRY_API_URL` 等整合配置
2. 持續把 `6_entry` 的對外 Web 能力回收到 `frontend + backend`
3. 讓 `README.md`、`CLAUDE.md`、測試文檔全部以這份整合架構為準
4. 為 `frontend` 與 `backend` 補齊對應的本地開發與 E2E 文檔