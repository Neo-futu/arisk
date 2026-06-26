---
name: compliance
description: SFC《單位信託及互惠基金守則》第8.2章合規全面核查
---

# /compliance — MMF 合規核查命令

## 用法

```
/compliance [fund_id] [date]
```

## 執行步驟

1. 取基金持倉和風控快照
2. 應用 `mmf-compliance` SKILL 逐條對照第8.2章
3. 生成合規報告，標注每一條款通過/違規狀態
4. 如有違規，提供具體的整改建議

## 重要聲明

本命令生成的合規報告基於持倉數據計算，僅供初步參考。最終合規判斷請以合規部門出具的正式意見為準。
