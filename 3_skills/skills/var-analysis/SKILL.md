---
name: var-analysis
description: VaR 專項分析技能：歷史法（252日）、蒙特卡洛法、分佈公式法，輸出 VaR/CVaR 與方法口徑說明。
triggers:
  - VaR
  - var
  - cvar
  - expected shortfall
  - 歷史法
  - 蒙特卡洛
  - 分佈公式
  - parametric
  - monte carlo
  - risk percentile
---

# VaR 專項分析技能

## 適用場景

- 用戶只關心 VaR/CVaR（不需要完整暴露報告）
- 需要比較多種 VaR 方法（historical / monte_carlo / distribution）
- 需要說明 VaR 業務含義與方法差異
- 組合剛運行、樣本不足時，需要 `INSUFFICIENT_DATA` 兜底口徑

## 核心調用

調用 Processing API：

- `GET /risk/var/{fund_id}?as_of_date=YYYY-MM-DD&method=historical&confidence=0.99&horizon_days=1`
- `GET /risk/var/{fund_id}?as_of_date=YYYY-MM-DD&method=monte_carlo&confidence=0.99&horizon_days=1&simulations=20000`
- `GET /risk/var/{fund_id}?as_of_date=YYYY-MM-DD&method=distribution&confidence=0.99&horizon_days=1`

其中：

- `method` 支援：`historical` / `monte_carlo` / `distribution`（兼容 `parametric`）
- `confidence` 預設 `0.99`
- `horizon_days` 預設 `1`
- `simulations` 僅蒙特卡洛法使用，預設 `10000`

## 方法口徑（最小可用）

1. **Historical Simulation**
   - 用過去收益序列的左尾分位數（99% → 1% 左尾）
   - 輸出：`HISTORICAL_SIMULATION`

2. **Monte Carlo**
   - 用歷史樣本估計 μ/σ，模擬收益分佈後取左尾分位
   - 輸出：`MONTE_CARLO`

3. **Distribution Formula**
   - 假設收益服從正態分佈，使用封閉解
   - 輸出：`DISTRIBUTION_FORMULA`

## 啟動期樣本不足處理

- 當樣本數不足（小於 `min_observations`）時返回：
  - `method=INSUFFICIENT_DATA`
  - `var_hkd=0`
  - `cvar_hkd=0`
  - `sample_size=0`
- 報告中需明確標註「樣本不足，僅供參考，不可作正式限額判斷」

## 建議輸出模板

```
## VaR 專項分析 — {fund_id} · {as_of_date}

| 方法 | VaR(HKD) | VaR(%NAV) | CVaR(HKD) | 樣本數 |
|------|----------|-----------|-----------|--------|
| Historical | ... | ... | ... | ... |
| Monte Carlo | ... | ... | ... | ... |
| Distribution | ... | ... | ... | ... |

### 口徑說明
- 置信度：99%
- 持有期：1天
- VaR(%NAV) 以 as_of_date 當日 NAV 為分母

### 風險解讀
- 一般損失門檻（VaR）
- 尾部平均損失（CVaR）
```

## 注意事項

- 該技能只做風險度量，不替代合規判斷。
- 對外披露應固定單一方法作主口徑，其他方法作對比輔助。
- 當樣本不足時，不得將 VaR 作為限額觸發依據。
