---
name: risk-analysis
description: 貨幣市場基金風控分析：VaR、WAM/WAL、集中度、MMF 合規（SFC 第8.2章）。持倉暴露請求時自動觸發。
triggers:
  - 風險分析
  - risk analysis
  - VaR
  - WAM
  - WAL
  - 暴露
  - exposure
  - 集中度
  - concentration
  - 合規
  - compliance
  - 守則 8.2
---

# 風控分析技能

## 分析流程

1. **取持倉** → 調用 `GET /positions/{fund_id}?as_of_date=YYYY-MM-DD`
2. **計算暴露** → 調用 `GET /risk/exposure/{fund_id}?as_of_date=YYYY-MM-DD`
3. **計算 VaR** → 優先調用 `var-analysis` 技能（historical / monte_carlo / distribution）
4. **合規判斷** → 對照 SFC 守則第 8.2 章閾值
5. **生成報告** → 結構化輸出表格 + 違規預警

## SFC 守則第 8.2 章關鍵閾值

| 指標 | 守則要求 | 違規觸發 |
|------|---------|---------|
| 加權平均期限（WAM） | ≤ 60 天 | WAM_BREACH |
| 加權平均有效期（WAL） | ≤ 120 天 | WAL_BREACH |
| 每日流動資產 | ≥ 7.5% NAV | DAILY_LIQUID_BREACH |
| 每週流動資產 | ≥ 15% NAV | WEEKLY_LIQUID_BREACH |
| 單一實體工具+存款 | ≤ 10% NAV（重要財務機構可至 25%） | SINGLE_ENTITY_BREACH |
| 同集團合計 | ≤ 20% NAV | GROUP_BREACH |
| 個別工具剩餘期限 | ≤ 397 天（政府證券 ≤ 2 年） | MATURITY_BREACH |
| 資產抵押證券合計 | ≤ 15% NAV | ABS_BREACH |
| 其他貨幣市場基金 | ≤ 10% NAV | MMF_INVEST_BREACH |

## 信貸質素標準（參考第 7.36(j) 條）

短期工具最低投資級別：
- S&P: **A-3** 或以上
- Fitch: **F3** 或以上
- Moody's: **P-3** 或以上
- 中資評級機構：工具評級 A-1 或以上 / 發行人 AA+ 或以上

## 輸出格式

```
## 風控快照 — {基金名} · {日期}

**總資產淨值**: HKD {NAV:,.0f}

### 組合期限指標
| 指標 | 數值 | 上限 | 狀態 |
|------|------|------|------|
| WAM  | X.X 天 | 60 天 | ✅/❌ |
| WAL  | X.X 天 | 120 天 | ✅/❌ |

### 流動性
| 類型 | 比例 | 下限 | 狀態 |
|------|------|------|------|
| 每日流動資產 | X.X% | 7.5% | ✅/❌ |
| 每週流動資產 | X.X% | 15% | ✅/❌ |

### 集中度 Top 10 發行人
...

### 資產類型分佈
...

### VaR（99%, 1天, 歷史模擬）
**VaR**: HKD X,XXX,XXX (X.XX% NAV)
**CVaR**: HKD X,XXX,XXX

### VaR 方法對比（可選）
| 方法 | VaR(HKD) | VaR(%NAV) | CVaR(HKD) | 樣本數 |
|------|----------|-----------|-----------|--------|
| historical | ... | ... | ... | ... |
| monte_carlo | ... | ... | ... | ... |
| distribution | ... | ... | ... | ... |

### 合規狀態
{✅ 全部合規 | ❌ 發現 N 項違規}
```

## 注意事項

- 分析結果僅供參考，不構成投資建議
- 合規判斷以最新版 SFC 守則為準，如有疑問請諮詢合規部門
- VaR 使用歷史模擬法，基於 252 個交易日數據
- 若用戶明確要求方法對比，調用 `var-analysis` 技能輸出三方法結果
