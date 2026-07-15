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
