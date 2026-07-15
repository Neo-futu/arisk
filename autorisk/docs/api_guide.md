# AutoRisk API 使用指南

服務地址：`http://127.0.0.1:8100`  
開發 API Key：`autorisk-dev-key`（生產必須替換）

## 啟動

```powershell
Set-Location autorisk
Copy-Item .env.example .env
python run.py
```

API 文檔：`http://127.0.0.1:8100/docs`

## 建立全自動評估

```powershell
$body = @{
  request_id = "OMS-20260715-0001"
  trigger_source = "PRE_TRADE"
  fund_code = "990001.HK"
  fund_name = "平衡增長一號基金"
  indicators = @{
    leverage_ratio = 1.10
    single_stock_concentration = 0.09
    var_95_1d = 0.018
    liquidity_ratio = 0.25
  }
  proposed_trade = @{
    symbol = "700.HK"
    side = "BUY"
    notional_hkd = 10000000
  }
  market_snapshot = @{
    snapshot_time = "2026-07-15T09:42:18Z"
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8100/api/v1/risk-evals/assess" `
  -Headers @{ "X-API-Key" = "autorisk-dev-key" } `
  -ContentType "application/json" `
  -Body $body
```

結果中的 `execution_decision`：

- `ALLOW`
- `ALLOW_WITH_WARNING`
- `BLOCK`

相同 `request_id` 重試不會建立重複報告。

## AI 風控審核結論單

評估完成後可獲取類似電子處方的最終結論單。結論單將完整報告壓縮為明確、可執行的指令：

- `APPROVED / PROCEED`：准予執行；
- `APPROVED_WITH_CONDITIONS / PROCEED_WITH_CONTROLS`：落實列示控制措施後方可執行；
- `NOT_APPROVED / DO_NOT_PROCEED`：禁止執行。

```powershell
$reportId = "<report_id>"
$headers = @{ "X-API-Key" = "autorisk-dev-key" }

$conclusion = Invoke-RestMethod `
  "http://127.0.0.1:8100/api/v1/risk-evals/reports/$reportId/conclusion" `
  -Headers $headers

Invoke-WebRequest `
  "http://127.0.0.1:8100/api/v1/risk-evals/reports/$reportId/conclusion/download?format=json" `
  -Headers $headers `
  -OutFile "$reportId.conclusion.json"

Invoke-WebRequest `
  "http://127.0.0.1:8100/api/v1/risk-evals/reports/$reportId/conclusion/download?format=html" `
  -Headers $headers `
  -OutFile "$reportId.conclusion.html"
```

結論單包含：最終處置指令、有效期、控制要求、規則命中、兩級簽署、報告內容哈希、結論單哈希和 feedback 契約。

## 回傳 OK JSON 回執

下游 OMS、交易系統或人工處置台完成處理後，應回傳其實際看到的 `report_content_hash` 和 `execution_decision`。AutoRisk 會拒絕哈希或決策不一致的回執。

```json
{
  "idempotency_key": "OMS-EXEC-20260715-0001",
  "status": "OK",
  "actor_id": "oms-production",
  "observed_report_hash": "<conclusion.verification.report_content_hash>",
  "observed_decision": "ALLOW_WITH_WARNING",
  "processed_at": "2026-07-15T12:00:00Z",
  "message": "已落實控制措施並按結論處理",
  "metadata": {
    "downstream_order_id": "ORDER-10001"
  }
}
```

```powershell
$feedbackBody = Get-Content .\feedback.json -Raw
$receipt = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8100/api/v1/risk-evals/reports/$reportId/feedback" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $feedbackBody
```

成功返回：

```json
{
  "schema_version": "1.0",
  "receipt_type": "AUTORISK_FEEDBACK_RECEIPT",
  "receipt_id": "ACK-...",
  "report_id": "RC-...",
  "status": "OK",
  "accepted": true,
  "message": "已落實控制措施並按結論處理",
  "feedback_hash": "...",
  "receipt_hash": "..."
}
```

同一 `report_id + idempotency_key` 重試相同內容會返回原回執；同一冪等鍵提交不同內容會返回 `409 Conflict`。回執獨立存儲，不會改寫已簽署報告或破壞原內容哈希，並追加至審計哈希鏈。

## 查詢與驗證

```powershell
$headers = @{ "X-API-Key" = "autorisk-dev-key" }
Invoke-RestMethod "http://127.0.0.1:8100/api/v1/risk-evals/reports" -Headers $headers
Invoke-RestMethod "http://127.0.0.1:8100/api/v1/risk-evals/reports/<report_id>" -Headers $headers
Invoke-RestMethod "http://127.0.0.1:8100/api/v1/risk-evals/reports/<report_id>/verify" -Headers $headers
Invoke-RestMethod "http://127.0.0.1:8100/api/v1/risk-evals/audit/verify" -Headers $headers
```

## HYBRID 人工雙簽

先設置：

```powershell
$env:AUTORISK_WORKFLOW_MODE = "HYBRID"
```

初審：

```json
{
  "signer_id": "risk-officer-001",
  "signer_role": "RISK_OFFICER",
  "decision": "APPROVE",
  "notes": "已核對持倉與交易指令"
}
```

終審：

```json
{
  "signer_id": "mic-001",
  "signer_role": "MIC",
  "decision": "APPROVE",
  "notes": "批准放行；紅燈覆蓋原因必填"
}
```

## Python SDK

```python
from client import AutoRiskClient

with AutoRiskClient(api_key="autorisk-dev-key") as client:
    report = client.assess({
        "request_id": "OMS-20260715-0002",
        "trigger_source": "PRE_TRADE",
        "fund_code": "990001.HK",
        "indicators": {
            "leverage_ratio": 1.0,
            "single_stock_concentration": 0.05,
            "var_95_1d": 0.01,
            "liquidity_ratio": 0.30
        }
    })
    print(report["report_id"], report["execution_decision"])
```

## 回調

設置 `AUTORISK_CALLBACK_ENABLED=true` 並在請求提供 `callback_url`。回調 Header：

- `X-AutoRisk-Event: risk-evaluation.completed`
- `X-AutoRisk-Signature: <HMAC-SHA256>`

接收方應使用 `AUTORISK_SIGNING_SECRET` 驗證原始 JSON body。
