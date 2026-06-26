---
name: xlsx-report
description: 生成格式化 xlsx 報表（headless 模式）：風控日報、業績月報、持倉明細。
triggers:
  - 生成 Excel
  - generate xlsx
  - 生成報表
  - export report
  - 導出
  - 風控日報
  - 業績月報
---

# XLSX 報表生成技能

## 支援報表類型

| 報表 | 說明 | 輸出文件 |
|------|------|---------|
| `risk_daily` | 風控日報（WAM/WAL/暴露/合規） | `risk_daily_{fund}_{date}.xlsx` |
| `position_detail` | 持倉明細 | `positions_{fund}_{date}.xlsx` |
| `performance_monthly` | 業績月報 | `perf_monthly_{fund}_{ym}.xlsx` |
| `compliance_report` | MMF 合規報告 | `compliance_{fund}_{date}.xlsx` |

## 生成流程

1. 確認報表類型和參數（fund_id, date）
2. 調用 Processing API 取數據
3. 使用 `openpyxl` 生成格式化 xlsx
4. 上傳到 S3（`fsi-risk-artefacts/reports/`）
5. 返回下載鏈接

## 格式規範

- 表頭使用深藍色背景 (#1F3864)，白色字體
- 數字右對齊，保留 2-4 位小數
- 違規單元格標紅（#FF0000 背景）
- 包含生成時間戳和數據來源說明
- Sheet 1: 彙總 / Sheet 2+: 明細

## 注意事項

- 生成操作由被授權的 write-holder subagent 執行
- xlsx 含有持倉數據，屬於敏感信息，下載鏈接有效期 1 小時
