# ARISK Frontend (React)

獨立前端目錄：`6_entry/frontend`

技術棧：

- React + TypeScript
- Vite

## 功能

- Direct Query 模式：調用 `GET /query/risk/var-compare/{fund_id}`
- Agent Skill 模式：調用 `POST /agent/skills/var-analysis`
- 同頁展示三方法 VaR 表格與 Agent summary

## 啟動

1. 安裝依賴

```bash
cd 6_entry/frontend
npm install
```

2. 配置 API 基址

```bash
cp .env.example .env
```

默認：

`VITE_ENTRY_API_BASE=http://127.0.0.1:8000`

3. 啟動開發服務

```bash
npm run dev
```

## 目錄結構

```text
src/
  api/
    varApi.ts           # API 請求封裝
  components/
    VarResultTable.tsx  # 結果表格組件
  types/
    var.ts              # 型別定義
  App.tsx               # 主頁（Direct / Agent 雙模式）
```
