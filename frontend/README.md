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
