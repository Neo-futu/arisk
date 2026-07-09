# aiagent/msft365 — Microsoft 365 整合

整合自 claude-risk-agent/claude-for-msft-365-install。  
為 ARISK 平台提供 Claude Office Add-in 支持，讓用戶在 Excel/Word 中直接調用 ARISK Agent。

## 目錄結構

```
msft365/
├── README.md              ← 本文件
├── commands/              ← Claude Office 命令定義（原版未修改）
│   ├── setup.md           # Enterprise 管理員安裝嚮導
│   ├── manifest.md        # Add-in manifest XML 生成指南
│   ├── consent.md         # Azure admin consent URLs
│   ├── bootstrap.md       # Bootstrap endpoint 規範
│   └── debug.md           # 部署診斷指南
└── bootstrap/             ← FastAPI bootstrap endpoint 參考實現
    ├── app.py             # Bootstrap 服務（JWT 驗證 + RBAC）
    ├── config.py          # ARISK 定制配置（MCP servers, Skills, RBAC rules）
    ├── requirements.txt   # 依賴
    └── README.md          # 運行說明
```

## ARISK 整合說明

### Excel 入口場景

ARISK 已有 `6_entry/excel/bootstrap/bootstrap.md` 定義了 Excel 命令。  
msft365 提供了完整的企業級部署方案：

```
Excel → Claude Office Add-in
  → bootstrap endpoint (app.py, RBAC by Entra group)
  → ARISK MCP servers / Skills
  → aiagent/engine（tool_use 循環）
  → 2_processing API
```

### 快速啟動（本地測試）

```bash
cd aiagent/msft365/bootstrap

# 對真實 Entra 租戶
export TENANT_ID=<your-tenant-guid>
pip install -r requirements.txt
python app.py

# 本地 dev token（無需真實 Entra）
TOKEN=$(python mint_dev_token.py --oid alice --group <group-id>)
python app.py  # 會自動使用 dev_jwks.json
```

### 配置 ARISK Skills

編輯 `config.py` 添加 ARISK 特定 Skills：

```python
SKILLS = {
    "risk-dashboard": {
        "url": "http://localhost:8000/api/v1/fsi/risk/...",
        "description": "ARISK 風控儀表板 skill"
    },
    "compliance-check": {
        "url": "http://localhost:8010/agent/v2/stream",
        "description": "SFC 合規核查 skill（SSE 流式）"
    }
}
```

### 生產部署

參考 `commands/setup.md` 執行完整企業部署：
- Step 1: 選擇 cloud path（Vertex AI / Bedrock / Gateway）
- Step 2: Azure admin consent
- Step 3: 生成 manifest XML
- Step 4: 部署到 Microsoft Admin Center
