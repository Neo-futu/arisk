# Page Checks 使用說明

本目錄提供「每個頁面一個獨立 Python 測試入口」，用於手工驗證整體數據流與業務邏輯。

## 1. 目錄與檔案結構

- `core.py`
  - 頁面檢查核心引擎（公共 HTTP 請求、鑑權、DB 連通、結果彙總、頁面對應檢查函數）。
- `check_page_*.py`
  - 每個頁面一個獨立入口腳本。
  - 例如：
    - `check_page_dashboard.py`
    - `check_page_investment_indicators.py`
    - `check_page_reports.py`
    - `check_page_chat.py`

## 2. core.py 是做什麼

`core.py` 是所有頁面腳本的共用檢查框架，包含：

1. 環境與上下文初始化
- 讀取 `.env` 與環境變量。
- 構造 backend/processing/frontend/autorisk 的 base URL。
- 構造基金與日期參數（`fund_id`、`as_of_date`、`start_date`、`end_date`）。

2. 通用檢查能力
- DB TCP 檢查。
- Processing 健康檢查。
- Backend 健康檢查與登入拿 token。
- MCP gateway 端口檢查。
- Frontend 頁面路由可訪問性檢查。

3. 分層接口驗證
- Processing 直連檢查：`/risk/*`、`/investment/*`、`/positions/*` 等。
- Backend 代理檢查：`/api/v1/fsi/*`、`/api/v1/users/*`、`/api/v1/knowledge/*` 等。

4. 報告輸出
- 每條檢查輸出 `PASS/FAIL`。
- 支持 JSON 報告（`--json`）。

## 3. 現在 db -> processing -> frontend 的數據是怎麼實現的

不是靠 OpenAPI sync 來傳數據。

實際運行鏈路是：

1. `db`
- PostgreSQL 真實業務表（如 `fsi.balance_portfolio_nav` 等）提供原始數據。

2. `processing`
- `2_processing` 直接查 DB，做風控與投資計算，暴露內部 API。

3. `backend`
- `backend` 做鑑權、策略與代理，將前端請求轉發到 `processing`。

4. `frontend`
- 前端頁面調用 `backend` API，渲染結果。

## 4. sync_openapi_contracts 的作用（你問的第 2 點）

`scripts/sync_openapi_contracts.py` 的用途是「同步 API 契約（OpenAPI JSON）」，不是同步業務數據。

它做的是：

- 拉取 backend/processing 的 OpenAPI。
- 更新 `frontend/openapi/*.json`。
- 配合 `openapi-ts` 生成前端型別/客戶端，降低接口字段漂移風險。

結論：

- 業務數據流：DB -> processing -> backend -> frontend（實時 API）。
- OpenAPI sync：只管契約與型別，不承載運行時數據。

## 5. 如何手工驗證頁面數據流與業務邏輯

### 步驟 A：啟動服務

在倉庫根目錄執行：

```powershell
python scripts/dev.py --parts processing entry backend frontend mcp-gateway
```

如需 AutoRisk 頁：

```powershell
cd autorisk
python run.py
```

或另開終端啟動。

### 步驟 B：單頁獨立驗證

示例（都在倉庫根目錄執行）：

```powershell
python scripts/page_checks/check_page_dashboard.py --fund-id BHMMF001
python scripts/page_checks/check_page_investment_indicators.py --fund-id BHMMF001
python scripts/page_checks/check_page_reports.py --fund-id BHMMF001
python scripts/page_checks/check_page_chat.py --fund-id BHMMF001
```

### 步驟 C：全頁批量驗證

```powershell
Get-ChildItem scripts/page_checks/check_page_*.py | ForEach-Object { python $_.FullName --fund-id BHMMF001 }
```

### 可選參數

```powershell
--as-of-date 2026-06-25
--start-date 2026-05-26
--end-date 2026-06-25
--report-id report_03_mmf
--json
```

## 6. 常見問題

1. 運行中突然整棧退出
- 若在 dev watcher 運行時修改了 `scripts/page_checks/core.py`，可能觸發 reload 並導致前端終端出現 `Terminate batch job (Y/N)?`，進而停止。
- 建議：先完成代碼修改，再啟動服務跑整套驗證。

2. 某頁偶發 FAIL，但單獨重跑 PASS
- 常見於服務重載窗口、臨時連接波動。
- 先單頁重跑確認；若連續失敗，再看該頁對應 backend/processing 日誌。

## 7. 與舊腳本關係

- `scripts/run_dataflow_unit_checks.py`
  - 偏全局總覽（核心鏈路檢查）。
- `scripts/page_checks/check_page_*.py`
  - 偏頁面粒度（你要的手工逐頁驗證）。
