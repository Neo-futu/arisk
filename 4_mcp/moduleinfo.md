<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 4_mcp — 外部 / 內部數據連接層

## 模塊定位

MCP 是 ARISK 的 **Tool Connectivity Layer**。Agent / Skills 只透過本層取數，**不得用 MCP 取代 RiskEngine**。VaR / NAV / PnL / Stress / Valuation / Limit 的計算走 `4_business` → `3_riskengine`。

FSI 風控業績平台的**統一數據連接層**。MCP（Model Context Protocol）在這裡的意義不是再做一個業務層，而是把所有**外部數據源**與**內部數據庫**封裝成標準化工具，讓 Agent / Skills 只透過一致協議取數，不直接綁死在底層實作上。

換句話說：
- **外部連接**：Wind、行情、財務、評級、指數等
- **內部連接**：只讀業務資料、風控快照、組合持倉等
- **職責邊界**：只負責連接與調度，不承擔業務決策、不承擔知識推理

```
3_skills / Agent / Platform Agent
  ↓ MCP Tool 調用
【4_mcp】  ← 統一數據連接層
    ├── wind/          外部：Wind API 行情/財務數據
    ├── internal/      內部：Postgres 只讀查詢
    └── Gateway        統一路由入口
```

---

## 目錄結構

```
4_mcp/
├── .mcp.json                MCP 服務器配置（供 Claude Code / Agent 使用）
├── client.py                MCP 客戶端適配器（gateway 優先，stdio 回退）
├── gateway/
│   └── mcp_gateway.py       統一 HTTP Gateway（/mcp/{server}/{tool}）
├── wind/
│   └── wind_mcp_server.py   WindAPI MCP Server
└── internal/
    └── internal_mcp_server.py  內部 Postgres 只讀 MCP Server
```

---

## MCP 服務器說明

### `wind` — WindAPI 數據連接器

**啟動方式：** `python -m 4_mcp.wind.wind_mcp_server`

**認證：** `WIND_USERNAME` + `WIND_PASSWORD` 環境變量

**提供工具（MCP Tools）：**

| 工具名 | 功能 | 主要參數 |
|---|---|---|
| `wind_get_price` | 股票/債券/基金歷史收盤價 | codes, start_date, end_date, fields |
| `wind_get_fx` | 外匯匯率歷史數據 | currency_pair, start_date, end_date |
| `wind_get_bond_info` | 債券靜態信息（票息/評級/到期日） | bond_code |
| `wind_get_index_components` | 指數成分股及權重 | index_code, date |
| `wind_get_yield_curve` | 收益率曲線（HIBOR/SHIBOR/國債） | curve_id, date |

**數據覆蓋：**
- 港股、A股、美股、債券、基金、指數
- HIBOR / SHIBOR / SOFR 利率數據
- 信用評級（中誠信、聯合資信、S&P等）
- 財務數據（PE/PB/每股現金流等）

---

### `internal-db` — 內部數據庫只讀連接器

**啟動方式：** `python -m 4_mcp.internal.internal_mcp_server`

**實現約束：** SQL 已下沉到 `2_processing/tools/internal/sql_queries.py`。`internal_mcp_server.py` 負責 MCP 工具調度與只讀取數。Agent 路徑的風險指標由 RiskEngine 計算，不經 MCP 取代引擎。

**認證：** `MCP_GATEWAY_SECRET` Bearer Token

**設計原則：只讀**，Agent 通過此 MCP 查詢已清洗的業務數據，不能寫入。

**提供工具（MCP Tools）：**

| 工具名 | 功能 | 對應數據表 |
|---|---|---|
| `get_nav_history` | 查詢組合 NAV 歷史 | `balance_portfolio_nav` |
| `get_positions` | 查詢持倉（按科目關鍵詞可選過濾） | `balance_valuation_sheet` |
| `get_risk_snapshot` | 查詢風控快照 | `svc_risk_snapshot` |
| `get_var_three_methods` | 計算三方法 VaR（歷史/蒙特卡洛/分佈公式） | `balance_portfolio_nav` |
| `get_fund_list` | 查詢活躍基金清單 | `para_portfolio` |

---

## MCP 配置（`.mcp.json`）

```json
{
  "mcpServers": {
    "wind": {
      "description": "WindAPI 行情、財務、指數數據連接器",
      "command": "python",
      "args": ["-m", "4_mcp.wind.wind_mcp_server"],
      "env": {
        "WIND_USERNAME": "${WIND_USERNAME}",
        "WIND_PASSWORD": "${WIND_PASSWORD}"
      }
    },
    "internal-db": {
      "description": "內部 Postgres 數據庫 MCP（只讀）",
      "command": "python",
      "args": ["-m", "4_mcp.internal.internal_mcp_server"],
      "env": {
        "DATABASE_URL": "${DATABASE_URL}",
        "MCP_GATEWAY_SECRET": "${MCP_GATEWAY_SECRET}"
      }
    },
    "fsi-gateway": {
      "description": "統一 MCP Gateway — 路由到 wind / internal-db / redis",
      "url": "http://localhost:${MCP_GATEWAY_PORT:-8002}/mcp",
      "headers": {
        "Authorization": "Bearer ${MCP_GATEWAY_SECRET}"
      }
    }
  }
}
```

---

## MCP Gateway

**`fsi-gateway`** 是統一入口，作為 HTTP Streamable MCP 端點運行，Agent 只需連接 Gateway，無需分別連接多個 MCP Server。

```
Agent
  ↓ HTTP /mcp
fsi-gateway (port 8002)
  ├── → wind MCP server（行情數據）
  ├── → internal-db MCP server（業務數據）
  └── → Redis（緩存查詢）
```

**優勢：**
- 統一認證（Bearer Token）
- 請求路由和負載均衡
- 速率限制和監控
- 單點配置，客戶端無感知後端變化

---

## 與其他層的交互

| 調用方 | 調用哪個 MCP | 用途 |
|---|---|---|
| `3_skills` / `aiagent` | `fsi-gateway` → `wind` | 拉取最新行情/評級/指數等外部資料 |
| `3_skills` / `platform_agent` | `fsi-gateway` → `internal-db` | 查詢清洗後的內部業務數據 |
| `2_processing` ETL | 直接調用 Wind Python SDK | 批量歷史數據載入（不走 MCP） |
| `5_deploy` / orchestration | `fsi-gateway` | 任務編排或多 Agent 執行時的統一數據入口 |

---

## 環境變量

| 變量 | 說明 |
|---|---|
| `WIND_USERNAME` | Wind 終端用戶名 |
| `WIND_PASSWORD` | Wind 終端密碼 |
| `DATABASE_URL` | Postgres 連接串（只讀用戶） |
| `MCP_GATEWAY_PORT` | Gateway 端口，默認 8002 |
| `MCP_GATEWAY_SECRET` | Gateway Bearer Token |

---

## 快速啟動

```bash
# 啟動 MCP Gateway（統一入口，推薦）
python -m 4_mcp.gateway.mcp_gateway

# 啟動 Wind MCP Server
python -m 4_mcp.wind.wind_mcp_server

# 啟動 Internal DB MCP Server
python -m 4_mcp.internal.internal_mcp_server

# Claude Code 中使用（.mcp.json 已配置）
# Agent 啟動時自動連接所有 MCP Server
```

## 統一再分拆（建議模式）

- 先統一：在應用層設置 `MCP_GATEWAY_URL=http://127.0.0.1:8002`，client 會優先走 gateway
- 再分拆：若 gateway 不可用，`4_mcp/client.py` 會自動回退到 stdio 直連 `internal` / `wind`

這樣可以先收斂入口、再逐步拆分服務，不會阻塞現有流程。
