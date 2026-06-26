# 3_skills — 能力技能層

## 模塊定位

FSI 風控業績平台六層架構的**第三層**，是 Claude Agent 的**業務能力庫**。將平台的風控、合規、業績分析能力封裝為可複用的技能（SKILL）和快捷命令（Command），供 Agent 模式和 Excel/Web 入口直接調用。

```
6_entry (Excel / Web)
    ↓  /risk  /compliance  /performance
【3_skills】  ← 本層（技能 + 命令）
    ↓  調用 Processing API
2_processing  →  1_datastorage
```

---

## 目錄結構

```
3_skills/
├── .claude-plugin/
│   └── plugin.json          技能包聲明（名稱/版本/技能路徑/MCP配置）
├── skills/                  SKILL.md 技能定義
│   ├── risk-analysis/       風控分析技能
│   ├── mmf-compliance/      MMF 合規核查技能
│   ├── performance-report/  業績歸因報告技能
│   ├── xlsx-report/         Excel 報表生成技能
│   └── human-review/        人工審核工作流技能
└── commands/                快捷命令定義
    ├── risk.md              /risk 命令
    └── compliance.md        /compliance 命令
```

---

## 技能詳解（`skills/`）

每個技能是一份 `SKILL.md`，定義觸發關鍵詞、執行步驟、輸出格式。Agent 根據用戶意圖自動匹配技能。

### `risk-analysis` — 風控分析

**觸發詞**：風險分析、risk analysis、VaR、WAM、WAL、暴露、集中度、合規

**執行流程：**
```
持倉拉取 → 暴露計算 → VaR 計算 → SFC 合規判斷 → 報告輸出
```

**調用接口：**
- `GET /positions/{fund_id}?as_of_date=` — 當日持倉
- `GET /risk/exposure/{fund_id}?as_of_date=` — 暴露分析
- `GET /risk/var/{fund_id}?confidence=0.99` — VaR（99%，1天）

**內置 SFC MMF 守則第 8.2 章閾值：**

| 指標 | 要求 | 違規代碼 |
|---|---|---|
| WAM 加權平均期限 | ≤ 60 天 | `WAM_BREACH` |
| WAL 加權平均有效期 | ≤ 120 天 | `WAL_BREACH` |
| 每日流動資產 | ≥ 7.5% NAV | `DAILY_LIQUID_BREACH` |
| 每週流動資產 | ≥ 15% NAV | `WEEKLY_LIQUID_BREACH` |
| 單一實體 | ≤ 10%（重要財務機構 ≤ 25%） | `SINGLE_ENTITY_BREACH` |
| 同集團合計 | ≤ 20% NAV | `GROUP_BREACH` |
| 工具剩餘期限 | ≤ 397 天 | `MATURITY_BREACH` |
| 資產抵押證券 | ≤ 15% NAV | `ABS_BREACH` |

---

### `mmf-compliance` — MMF 合規核查

專注 SFC《單位信託及互惠基金守則》第 8.2 章的完整合規核查：
- 詳細逐項驗證每條守則要求
- 信貸質素標準核查（S&P A-3 / Fitch F3 / Moody's P-3 或以上）
- 生成合規報告，違規項目突出顯示並附整改建議

---

### `performance-report` — 業績歸因報告

**功能：**
- 收益貢獻拆解（各資產類別 MTM / 利息 / 已實現 / 外匯）
- Brinson 行業歸因（配置效應 / 選股效應 / 交互效應）
- 個券損益前/後十大
- 同類排名及分位數

**調用接口：**
- `GET /performance/attribution/{fund_id}?begin=&end=`
- `GET /performance/contribution/{fund_id}?begin=&end=`

---

### `xlsx-report` — Excel 報表生成

**功能：**
- 將任何查詢結果格式化輸出到 Excel
- 支持多 Sheet（風控/持倉/歸因/月報）
- 套用預定義模版（對應 SmartReport 風格）
- **安全約束**：Excel 寫入操作僅由被授權的 `write-holder` 子 Agent 執行

---

### `human-review` — 人工審核工作流

**觸發條件（審核觸發矩陣）：**

| 場景 | 觸發條件 | SLA |
|---|---|---|
| `COMPLIANCE_BREACH` | SFC 守則任何違規 | 30 分鐘 |
| `HIGH_RISK` | VaR > NAV 5% | 30 分鐘 |
| `REPORT_PUBLISH` | 報告對外發布前 | 120 分鐘 |
| `DATA_WRITE` | 批量數據寫入前 | 60 分鐘 |
| `DATA_LOAD` | 新持倉文件載入 | 60 分鐘 |

**執行步驟：**
1. Agent 計算發現觸發條件
2. 調用 `POST /review/requests` 創建審核請求
3. Agent 在 `checkpoint.block()` 處暫停
4. 小富 AI 審核員（Claude）自動分析，給出 `APPROVE / REJECT / ESCALATE / REQUIRE_HUMAN`
5. 人工審核員在 Web UI 查看並決策
6. 審核通過 → Agent 繼續；拒絕 → Agent 中止並記錄

---

## 快捷命令（`commands/`）

在 Claude Code / Excel / Web Chat 中直接使用：

| 命令 | 說明 | 示例 |
|---|---|---|
| `/risk [fund_id] [date]` | 風控快照（WAM/WAL/VaR/合規） | `/risk BHMMF 2026-06-24` |
| `/compliance [fund_id] [date]` | MMF 合規核查 | `/compliance BHMMF` |
| `/positions [fund_id] [date]` | 持倉列表 | `/positions BHMMF` |
| `/performance [fund_id]` | 業績分析 | `/performance BHMMF` |

---

## 技能包聲明（`plugin.json`）

```json
{
  "name": "fsi-risk-skills",
  "version": "0.1.0",
  "skills": { "path": "skills/", "pattern": "*/SKILL.md" },
  "commands": { "path": "commands/", "pattern": "*.md" },
  "mcp": "../4_mcp/.mcp.json"
}
```

技能包由 `5_deploy` 的 Agent YAML 引用，統一版本管理。

---

## 設計原則

1. **技能 vs 命令**：技能（SKILL）是 Agent 自動匹配的能力描述；命令（Command）是用戶主動調用的快捷操作
2. **讀寫分離**：技能只讀查詢，寫操作（xlsx/DB）必須通過 write-holder 子 Agent + 人工審核
3. **技能源唯一**：所有 SKILL.md 在 `3_skills/skills/` 修改，`5_deploy` 的 Agent Bundle 引用此處，禁止直接改副本
4. **無直接DB訪問**：技能層通過 `2_processing` API 或 `4_mcp` 內部DB獲取數據，不直接查詢 Postgres
