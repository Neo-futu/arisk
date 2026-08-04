# ARISK Frontend

根目錄 `frontend/` 是本項目的唯一瀏覽器 Web 入口，承擔 Dashboard 與 Chat 工作台。

## 技術棧

- Vite + React + TypeScript
- TanStack Router + React Query
- Tailwind + shadcn/ui

## 依賴

- Node.js 20+（推薦）或 Bun

## 啟動步驟（本地）

1. 安裝依賴

```bash
cd frontend
npm install
```

2. 啟動開發服務

```bash
npm run dev
```

3. 訪問

- Frontend: `http://localhost:5173`
- Backend API（由前端調用）: `http://localhost:8000`

## 構建

```bash
npm run build
```

說明：build 腳本採用 `vite build && tsc -p tsconfig.build.json`，確保 TanStack Router 路由樹先生成，再進行型別檢查。

## API 契約與型別生成

本項目採用分層契約策略：

- `backend` OpenAPI -> `frontend/src/client`（身份、管理等 API）
- `2_processing` OpenAPI -> `frontend/src/contracts/processing`（風控/投資計算域 API）

步驟：

```bash
cd frontend
npm run contracts:refresh
```

等價分步命令：

```bash
cd frontend
npm run contracts:sync
npm run contracts:generate
```

僅同步單一來源（服務分開啟動時使用）：

```bash
cd frontend
npm run contracts:sync:backend
npm run contracts:sync:processing
```

說明：

- `contracts:sync` 會從 `http://localhost:8000/openapi.json` 和 `http://localhost:8001/openapi.json` 拉取契約快照。
- 契約快照保存在 `frontend/openapi/backend.json` 和 `frontend/openapi/processing.json`。

## 關鍵環境變量

可在 `frontend/.env` 設置：

```env
VITE_API_URL=http://localhost:8000
```

如果留空，預設走同源或由應用內默認值決定。

## 目錄入口

- 主入口：`frontend/src/main.tsx`
- 路由：`frontend/src/routes/`
- FSI API 封裝：`frontend/src/fsiClient.ts`

## 啟動腳本（推薦）

在倉庫根目錄直接啟動整體服務：

```bash
python scripts/dev.py --profile web
```

Windows PowerShell：

```powershell
./scripts/dev.ps1 -Profile web
```
