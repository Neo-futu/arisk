# AutoRisk — 智能風控評估服務

AutoRisk 是可獨立運行、API-only 的基金智能風控評估服務，提供從數據接入、規則判定、雙級覆核到執行控制與審計歸檔的標準化閉環：

```text
結構化交易/持倉輸入
  -> 配置化規則引擎
  -> 風控評估草案
  -> AI Risk Officer 初審
  -> AI MIC 終審
  -> 數字簽章 / 執行決策 / 合規歸檔
```

## 決策原則

- GREEN：AI 雙簽，`ALLOW`
- YELLOW：AI 雙簽，`ALLOW_WITH_WARNING`
- RED：AI 雙簽確認後自動 `BLOCK`
- AI 結論分歧：fail-closed，自動 `BLOCK`

FULL_AI 並不代表 AI 可推翻紅線。確定性規則引擎是權威決策來源，LLM 僅生成解釋文字。

## 獨立啟動

```powershell
Set-Location autorisk
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

- 服務：`http://127.0.0.1:8100`
- Swagger：`http://127.0.0.1:8100/docs`
- Health：`http://127.0.0.1:8100/health`
- 開發 API Key：`autorisk-dev-key`

## 可視化風控審核

服務啟動後訪問：`http://127.0.0.1:8100/demo`

頁面輸入觸發來源、基金信息和核心風險指標後，會展示：

- 槓桿率、集中度、VaR、流動性等核心指標
- 規則引擎命中結果與風險等級判定
- AI Risk Officer 與 AI MIC 兩級覆核
- ALLOW、ALLOW_WITH_WARNING 或 BLOCK 最終決策
- 類似電子處方的 AI 風控結論單，明確顯示「准予執行／附條件准予執行／禁止執行」
- 結論 JSON/HTML 下載、下游 `OK` 回執與完整性驗證

演示頁直接調用通用 `POST /api/v1/risk-evals/assess` 接口。生產接入時可由上游系統持續提交不同請求，並透過 `config/rules.json` 或規則重載接口持續迭代風控規則。

## AI 雙級覆核演示

保持服務終端運行，另開一個 PowerShell 終端，在項目根目錄執行：

```powershell
.\autorisk\scripts\demo_ai_review.ps1
```

腳本會提交 GREEN、YELLOW、RED 三個案例，展示 AI Risk Officer 與 AI MIC 的獨立覆核結果，並驗證內容哈希、雙簽、三類報告工件及審計鏈。

預期執行決策：

- GREEN：`ALLOW`
- YELLOW：`ALLOW_WITH_WARNING`
- RED：`BLOCK`

## Docker

```powershell
Set-Location autorisk
Copy-Item .env.example .env
docker compose up --build
```

## 主要能力

- PRE_TRADE / POST_TRADE / EOD / PERIODIC / EVENT 觸發
- JSON 配置化合同、監管與內控規則
- 任意數值型擴展風險指標；新增規則指標無需修改 Python schema
- 規則配置運行時熱重載
- 冪等評估請求
- FULL_AI 與 HYBRID 雙簽模式
- 可選 OpenAI-compatible LLM 評語
- HMAC-SHA256 兩級簽章
- append-only SHA-256 審計鏈
- JSON / Markdown / HTML 完整報告工件
- 可機器解析、可列印的結論單 JSON / HTML 工件
- 綁定報告哈希與最終決策的幂等執行回執
- 報告、簽章、工件、審計鏈完整性驗證
- API Key 認證與可選簽名 webhook
- 第三方 Python SDK

## API

- `POST /api/v1/risk-evals/assess`
- `GET /api/v1/risk-evals/reports`
- `GET /api/v1/risk-evals/reports/{report_id}`
- `GET /api/v1/risk-evals/reports/{report_id}/conclusion`
- `GET /api/v1/risk-evals/reports/{report_id}/conclusion/download?format=json|html`
- `POST /api/v1/risk-evals/reports/{report_id}/feedback`
- `GET /api/v1/risk-evals/reports/{report_id}/feedback`
- `GET /api/v1/risk-evals/reports/{report_id}/verify`
- `POST /api/v1/risk-evals/reports/{report_id}/sign/first`
- `POST /api/v1/risk-evals/reports/{report_id}/sign/second`
- `POST /api/v1/risk-evals/reports/{report_id}/reject`
- `GET /api/v1/risk-evals/rules`
- `POST /api/v1/risk-evals/rules/reload`
- `GET /api/v1/risk-evals/audit`
- `GET /api/v1/risk-evals/audit/verify`

## 測試

```powershell
Set-Location autorisk
python -m pytest tests -q
```

## 文檔

- [完整需求說明書](docs/requirements_spec.md)
- [技術架構](docs/architecture.md)
- [API 使用指南](docs/api_guide.md)

## 合規提示

FULL_AI 適合內部自動控制、沙盒與已獲制度授權的場景。如果法律、監管或公司制度要求持牌自然人簽署，請使用 `AUTORISK_WORKFLOW_MODE=HYBRID`，AI 僅提供草案與覆核建議。
