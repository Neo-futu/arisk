---
name: var
description: 計算基金 VaR 專項結果，支持 historical / monte_carlo / distribution 三方法對比
---

# /var — VaR 專項命令

## 用法

```
/var [fund_id] [date] [method]
```

**範例：**
```
/var BHMMF001 2026-06-25 historical
/var BHMMF001 2026-06-25 monte_carlo
/var BHMMF001 2026-06-25 distribution
/var BHMMF001 2026-06-25 all
```

## 執行步驟

1. 解析 `fund_id`、`date`、`method`
2. 調用 Processing API `GET /risk/var/{fund_id}`
3. 當 `method=all` 時，依次調用：
   - `method=historical`
   - `method=monte_carlo`
   - `method=distribution`
4. 使用 `var-analysis` 技能模板輸出

## 參數約定

- 置信度預設：`confidence=0.99`
- 持有期預設：`horizon_days=1`
- 蒙特卡洛預設：`simulations=10000`

## 輸出

- VaR(HKD)
- VaR(%NAV)
- CVaR(HKD)
- method / sample_size
