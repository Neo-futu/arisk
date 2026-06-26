---
name: bootstrap
description: FSI Risk Platform — Excel 環境初始化，偵測可用 MCP 和技能
---

# /bootstrap — Excel 環境初始化

## 執行步驟

1. **檢查 MCP 連接**
   - 測試 `fsi-gateway` MCP 連接
   - 測試 `internal-db` MCP 連接
   - 測試 `wind` MCP 連接（如已配置）

2. **載入可用技能**
   - `risk-analysis` — WAM/WAL/VaR/合規
   - `mmf-compliance` — SFC 守則第8.2章核查
   - `performance-report` — 業績歸因
   - `xlsx-report` — 報表生成

3. **確認 Processing API**
   - 健康檢查：`GET {PROCESSING_API_URL}/health`

4. **返回狀態摘要**

```
FSI Risk Platform — Excel 環境就緒 ✅

可用連接：
  ✅ FSI Gateway MCP
  ✅ Internal DB MCP
  ⚠️ Wind MCP（未配置，使用緩存數據）
  ✅ Processing API (http://localhost:8001)

可用命令：
  /risk [fund_id] [date]       — 風控快照
  /positions [fund_id] [date]  — 持倉列表
  /compliance [fund_id] [date] — MMF 合規核查
  /performance [fund_id]       — 業績分析
```

## 注意事項

- Excel 寫入操作僅由被授權的 write-holder 子 agent 執行
- 持倉數據屬於機密信息，請勿截圖分享
