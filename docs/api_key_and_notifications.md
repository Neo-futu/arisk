# API Key 與通知配置

## 1. Key 分層

ARISK 使用兩類不同用途的 `X-API-Key`，禁止混用：

| 類型 | 建立/配置位置 | 用途 | 是否可提供給界面用戶 |
|---|---|---|---|
| 用戶 API Key | Web UI → 系統管理 → API Key 管理 | 本地腳本、Excel 或外部客戶端調用 Backend `/api/v1/*` | 是；每位用戶自行建立和撤銷 |
| `PROCESSING_API_KEY` | 項目根目錄 `.env` | Backend、Entry、Agent 與 Processing 的內部服務間認證 | 否；不得下發到瀏覽器 |

用戶 Key 明文只在建立時顯示一次。Backend 僅保存 SHA-256 雜湊、前綴和末四位，無法還原明文。

## 2. 本地用戶 API Key

1. 啟動本地服務並登入 Web UI。
2. 打開「系統管理 → API Key 管理」。
3. 建立名稱為「本地開發」的 Key，選擇有效期。
4. 立即複製並保存明文；關閉提示後無法再次查看。
5. 使用 Header `X-API-Key` 調用 Backend，Base URL 默認為 `http://localhost:8000/api/v1`。

PowerShell 示例：

```powershell
$headers = @{ "X-API-Key" = "arisk_建立時顯示的密鑰" }
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/v1/fsi/investment/overview/BHMMF001?as_of_date=2026-06-25" `
  -Headers $headers
```

用戶 Key 繼承建立者的身份和權限。停用用戶、Key 到期或在界面撤銷後，請求將被拒絕。

## 3. 內部 Processing Key

在項目根目錄 `.env` 配置同一個高強度值：

```dotenv
PROCESSING_API_URL=http://localhost:8001
PROCESSING_API_KEY=<至少 32 字節的隨機值>
```

Processing 使用 `X-API-Key` 驗證該值。Backend 自動從伺服器環境讀取並代理請求，前端永遠不會取得此值。

生產環境要求：

- 不使用範例值 `internal_key_change_me`；
- 通過 Secret Manager 或 Kubernetes Secret 注入；
- 定期輪換，並同步更新所有內部調用方；
- 不提交到 Git、日誌、測試文件或前端環境變量。

## 4. 通知渠道

通知接口均位於 Backend，支持 JWT 或用戶 `X-API-Key` 認證：

| 渠道 | 接口 | 必要配置 |
|---|---|---|
| 郵件 | `POST /api/v1/notifications/email` | `SMTP_HOST`、`EMAILS_FROM_EMAIL`，按需配置 SMTP 帳密/TLS |
| 飛書 | `POST /api/v1/notifications/feishu` | `FEISHU_WEBHOOK_URL` |
| 企業微信 | `POST /api/v1/notifications/wecom` | `WECOM_WEBHOOK_URL` |

郵件請求：

```json
{
  "recipient": "risk@example.com",
  "title": "風險指標通知",
  "content": "BHMMF001 最大回撤超過內部提示閾值。"
}
```

飛書、企業微信請求：

```json
{
  "title": "投資風險分析",
  "content": "查詢結果摘要或風險提示。"
}
```

Webhook URL 只能由伺服器 `.env` 配置，接口不接受任意 URL，避免 SSRF 和憑證外洩。其他頁面可以直接複用前端客戶端的 `fsiApi.sendNotification(channel, payload)` 添加「發送通知」按鈕。
