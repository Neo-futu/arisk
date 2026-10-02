# SFC 香港 MMF 壓力測試 — 開發與驗證報告

> 對應文檔：`2_processing/sql/mmf/doc/lmt-mmf-test-sfc.docx`
> （Indicative Liquidity Profile + Basis of Liquidity Classification）
> 驗證日期：2026-10-02 · 估值日：2026-06-25 · 組合：BHMMF001 / BHMMF002

## 一、背景與差距

### 1.1 既有實現（report_03_mmf 17/42/44 SQL + liquidity_stress.py）

| 項目 | 既有實現 | SFC 文檔要求 |
|---|---|---|
| 利率衝擊 | +50bp 久期近似 `mv × (1 - dur × 0.005)` | ✅ 保留（行業標準久期近似法） |
| 變現係數 | 按資產類別硬編碼（GOVT=0.2/CD=0.2/CORP=0.8） | ⚠️ 保留為靜態兼容口徑 |
| ADTV 市場交易量 | **無**（僅類別固定變現天數映射） | ❌ 需 30 日 ADTV × 10% 參與率 |
| 5 檔流動性分層 | **無**（僅個券明細） | ❌ 需 1D/2-7D/8-30D/31-90D/>90D 雙場景 |
| 存款早破 | 引用不存在的 `is_penalty_on_early_redeem` 列（SQL 報錯） | ❌ 需零早破 Stressed 假設 |
| DLA/WLA | 僅 Normal 場景 | ❌ 需雙場景均 ≥7.5%/15% |

### 1.2 本次新增（report_06 SFC 壓力測試模塊）

1. **ADTV 行情表** `fsi.mktdata_adtv`：30 日平均日成交額（Wind/MCP 入庫更新，無行情時 PROXY 代理值：品種典型換手率 × 持倉市值）
2. **參數配置表** `fsi.sfc_liquidity_bucket_def`：8 類資產 × 2 場景（市場參與率 10%、ADTV 折扣 Stressed 50%、存款早破比例、買賣價差 bp、靜態變現係數）
3. **明細結果表** `fsi.sfc_liquidity_stress`：持倉 × 場景級（50 行/估值日）
4. **合規匯總表** `fsi.sfc_liquidity_compliance`：組合 × 場景級（5 檔分層 + DLA/WLA）
5. **SQL**：`10_sfc_stress.sql`（計算+落庫+返回明細）、`11_sfc_compliance_summary.sql`（展示層數據）
6. **Excel**：`Template.xlsx` 新增「SFC壓力測試原始」（明細）+「SFC壓力測試」（SFC 文檔表格版式）兩個 sheet
7. **修復**：`balance_deposit` 補 `is_penalty_on_early_redeem` 列（4 個既有 SQL 06_01/06_04/06_08/06_09 因此恢復可用）

## 二、業務邏輯（雙口徑）

### 2.1 口徑 A：流動性分層（SFC 文檔 §1(i)，非累計、資產端 sum to 100%）

每筆持倉全額市值歸入「完全變現所需天數」桶：

| 資產 | Normal 天數 | Stressed 天數 |
|---|---|---|
| 現金 | 0（1D） | 0（1D） |
| 隔夜存款 / 逆回購 | 1（1D） | 1（1D） |
| 可早破存款 | 0（1D） | 合約剩餘天數（**零早破**） |
| 有罰息定存 | 合約剩餘天數（§2(a)） | 合約剩餘天數 |
| 債券/CD（≤5 日到期） | 到期天數 | 到期天數 |
| 債券/CD（二級變現） | `⌈市值 / (ADTV×10%)⌉` | `⌈市值 / (ADTV×10%×50%)⌉`（**變現天數翻倍**） |

### 2.2 口徑 B：DLA / WLA（UT Code §8.2(n) 雙場景硬約束）

- `realizable_1d = MIN(市值, ADTV×10%×(1-折扣)) + 現金 + 隔夜 + 1 日到期`
- `realizable_5d = MIN(市值, ADTV×10%×(1-折扣)×5) + 現金 + 隔夜 + 5 日到期 + 可早破存款`
- DLA% ≥ 7.5%、WLA% ≥ 15%（Normal 與 Stressed 均須滿足）

### 2.3 利率變化（+50bp）與變現係數

- `stressed_mv = mv × (1 - duration × 50/10000)`；存款/現金/逆回購利率敏感度為 0
- `stressed_loss_adj = stressed_loss × liq_ratio_static`（GOVT/CD=0.2、CORP=0.8、FLOAT=0.05、DEPOSIT=0）

## 三、驗證結果（6 項核心斷言全部通過）

| # | 斷言 | 結果 |
|---|---|---|
| 1 | 雙場景 DLA/WLA 合規 | ✅ 4/4 合規（BHMMF001: 24.7/26.0 → 15.5/16.1；BHMMF002: 28.2/29.7 → 17.2/17.9） |
| 2 | Stressed DLA < Normal DLA | ✅ -9.28pct / -10.99pct（符合壓力收緊預期） |
| 3 | 信用債 Stressed 推至 GT90D | ✅ 3 只 0.6166 億：31-90D → GT90D（變現天數 50d→100d 翻倍） |
| 4 | 存款 Normal 早破(1D) vs Stressed 零早破 | ✅ 定存 1D→31-90D/GT90D 且 1 日可變現歸零；隔夜存款保持 1D |
| 5 | 利率損失與修正損失 | ✅ 如 BNYHFN26213.CMU：損失 111.38 萬 × 0.8 = 89.11 萬 |
| 6 | ADTV 50% haircut 精確生效 | ✅ 全部證券 Stressed/Normal tradable_size 比值 = 0.500 |

### 輸出文件

`2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx`

- 「SFC壓力測試原始」sheet：50 行 × 28 列（25 持倉 × 雙場景），含市值/久期/利率衝擊/ADTV/參與率/折扣/可變現規模/1日5日可變現額/時間桶/變現係數/修正損失
- 「SFC壓力測試」sheet：SFC 文檔 §1 版式 — 5 檔分層 × 雙場景（組合×場景行）+ DLA/WLA 合規狀態 + Note(i)-(iv) 與方法論說明
- 其餘 9 個既有查詢（06_01~06_09）全部正常（4 個因補列修復）

### 回歸驗證

`report_03_mmf`（17 壓力測試持倉 / 42 壓力結果 / 44 SFC 合規 / 45 集中度）全部通過，無回歸。

## 四、生產接入（Wind/MCP 行情）

1. 行情管道每日 `INSERT INTO fsi.mktdata_adtv (adtv_date, security_code, adtv_30d, sample_days, data_source) VALUES (..., 'WIND') ON CONFLICT DO UPDATE`（30 日 turnover 算術平均）
2. 未入庫證券自動回退 PROXY 代理值（`data_source='PROXY'`，明細表 adtv_source 列可審計）
3. 壓力參數調整直接改 `fsi.sfc_liquidity_bucket_def`（如參與率、折扣、價差），無需改 SQL

## 五、運行方式

```bash
# 建表（冪等）
python 1_datastorage/postgres/migrations/migrate.py   # 022/022a 已納入 schema 目錄
# 生成報表（含 SFC 壓力測試 sheet）
cd 2_processing/tools/mmf
python run_report.py --report report_06 --port BHMMF001,BHMMF002 --date 2026-06-25
```
