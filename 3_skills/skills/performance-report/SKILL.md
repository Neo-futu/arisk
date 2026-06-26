---
name: performance-report
description: 基金業績歸因分析、基準比較、多期收益彙總。業績相關請求自動觸發。
triggers:
  - 業績
  - performance
  - 收益
  - return
  - 歸因
  - attribution
  - 基準
  - benchmark
  - 超額收益
  - alpha
---

# 業績分析技能

## 分析流程

1. **取業績數據** → `GET /performance/{fund_id}?period_type=1M&as_of_date=YYYY-MM-DD`
2. **計算歸因** → `GET /performance/{fund_id}/attribution?start=...&end=...`
3. **基準比較** → 並排對比基金與基準收益
4. **生成表格** → 多期收益 + Sharpe + Info Ratio

## 支援期間類型

| 代碼 | 說明 |
|------|------|
| `1D` | 昨日 |
| `1W` | 近一週 |
| `1M` | 近一個月 |
| `3M` | 近三個月 |
| `YTD` | 年初至今 |
| `1Y` | 近一年 |
| `SI` | 成立以來 |

## 輸出格式

```
## 業績報告 — {基金名} · {日期}

### 多期收益彙總
| 期間 | 基金收益 | 基準收益 | 超額收益 |
|------|---------|---------|---------|
| 1M   | X.XX%   | X.XX%   | X.XX%   |
...

### 風險調整指標
| 指標 | 數值 |
|------|------|
| Sharpe Ratio (1Y) | X.XX |
| Information Ratio (1Y) | X.XX |
| Tracking Error (1Y) | X.XX% |

### 業績歸因（Brinson-Hood-Beebower）
| 行業 | 配置效應 | 選股效應 | 合計 |
|------|---------|---------|------|
...
```
