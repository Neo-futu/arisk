---
name: risk-analysis
version: "1.0"
description: MMF 風控指標分析技能 — WAM/WAL/VaR/暴露/SFC 合規
tools: get_exposure, get_var, get_var_compare
agent: risk-analyst
---

# 風控分析技能

## 觸發條件

以下問題觸發此技能：
- WAM / WAL / 加權平均期限
- VaR / 風險價值
- 流動性 / DLA / WLA
- SFC 合規 / 守則第 8.2 章
- 暴露分析 / 集中度
- 風控快照

## 執行步驟

1. **確認參數**：fund_id + as_of_date（從上下文獲取或詢問用戶）
2. **拉取暴露**：`get_exposure(fund_id, as_of_date)`
3. **VaR 分析**（可選）：`get_var_compare(fund_id, as_of_date, confidence=0.99)`
4. **合規判斷**：對照 SFC 閾值，標注違規項
5. **輸出報告**：結構化 Markdown 格式

## 輸出格式

```
## 風控快照 — {fund_id} · {date}

**WAM**: {value} 天（限額 ≤60 天）{status}
**WAL**: {value} 天（限額 ≤120 天）{status}
**DLA**: {value}%（下限 ≥7.5%）{status}
**WLA**: {value}%（下限 ≥15%）{status}

**VaR（99% 置信度，1 天持有期）**
| 方法 | VaR | CVaR |
|---|---|---|
| 歷史模擬 | {var_h} | {cvar_h} |
| 蒙特卡洛 | {var_mc} | {cvar_mc} |
| 參數法 | {var_p} | {cvar_p} |

**合規狀態**：{COMPLIANT / BREACH_LIST}
```
