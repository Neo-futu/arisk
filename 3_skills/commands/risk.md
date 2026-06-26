---
name: risk
description: 計算並顯示基金風控快照（暴露、WAM/WAL、VaR、MMF合規）
---

# /risk — 風控快照命令

## 用法

```
/risk [fund_id] [date]
```

**範例：**
```
/risk BHMMF 2026-06-24
/risk BHMMF
```

## 執行步驟

1. 解析 fund_id（如未提供，詢問用戶）
2. 解析日期（默認昨個交易日）
3. 調用 Processing API：
   - `GET {PROCESSING_API_URL}/positions/{fund_id}?as_of_date={date}` — 取持倉
   - `GET {PROCESSING_API_URL}/risk/exposure/{fund_id}?as_of_date={date}` — 暴露計算
   - `GET {PROCESSING_API_URL}/risk/var/{fund_id}?as_of_date={date}&confidence=0.99` — VaR
4. 應用 `risk-analysis` SKILL 格式化輸出
5. 如有合規違規，突出顯示並建議措施

## 輸出

結構化風控報告，包含：
- WAM/WAL（與守則上限對比）
- 流動性比例
- 集中度 Top 10
- 資產類型分佈
- VaR / CVaR
- 合規狀態 ✅/❌
