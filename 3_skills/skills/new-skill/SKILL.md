---
name: calculate-fund-maximum-drawdown
category: fund-risk-metrics
layer: platform
description: 根據基金 NAV 歷史數據計算指定時間區間的最大回撤（Maximum Drawdown）
tools: [get_nav_history]
version: "1.0"
---

# 基金最大回撤計算

## 觸發條件
- 用戶詢問基金 NAV 在一段時間區間的最大回撤（MDD）
- 需要評估基金的下行風險或波動性
- 提供基金代碼（如 BHMMF001）及明確的起訖日期

## 核心知識
- 最大回撤（MDD）衡量從歷史高峰到後續低谷的最大累計損失幅度
- 公式：`MDD = max[(NAV_t - Peak_t) / Peak_t]`，結果以負值百分比表示
- Peak_t 為從區間開始到時間 t 為止的滾動最高 NAV 值
- 計算過程需先取得每日 NAV 序列，再計算滾動高峰與每日回撤
- 最終取所有回撤中的最小值（最負值）即為 MDD
- 此為事後計算，非預測值，強烈依賴實際歷史數據
- 貨幣市場基金的 MDD 通常接近 0，但仍需以實際數據驗證

## 執行步驟
1. 確認基金 `fund_id` 及查詢區間（`start_date`、`end_date`，格式 YYYY-MM-DD）
2. 調用 `get_nav_history(fund_id, start_date, end_date)` 獲取 NAV 時間序列
3. 計算滾動高峰（Running Peak / cummax）
4. 對每個時點計算回撤率 `(NAV_t - Peak_t) / Peak_t`
5. 找出所有回撤值中的最小值作為 MDD，並可記錄發生的高點與低點日期
6. 以百分比形式呈現結果並提供解釋

## 注意事項
- MDD 高度依賴所選時間區間，短期區間可能低估真實風險
- 若工具返回空數據（sample_size=0），需檢查是否為非交易日或基金無持倉
- 計算結果為歷史事實，非未來績效保證
- 需注意數據品質與完整性，尤其在含假日或停牌期間
- 如需同時提供發生日期、恢復時間等附加分析，應進一步 уточ 用戶需求