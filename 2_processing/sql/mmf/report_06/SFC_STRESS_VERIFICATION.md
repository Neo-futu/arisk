# SFC 香港 MMF 壓力測試 — 開發與驗證報告（v2：三源行情 + 雙口徑拆分）

> 對應文檔：`2_processing/sql/mmf/doc/lmt-mmf-test-sfc.docx`
> 驗證日期：2026-10-05 · 估值日：2026-06-25 · 組合：BHMMF001 / BHMMF002
> v2 增量：ADTV 三源行情管道（Excel/yfinance/OpenBB/Wind）+ 口徑 A/B 拆分為獨立 sheet/SQL

## 一、雙口徑定義（為什麼有兩個口徑）

| | 口徑 A：流動性分層 | 口徑 B：DLA/WLA 覆蓋能力 |
|---|---|---|
| 回答的問題 | 「整個組合若全部變現，各時間段能變現多少？」（結構形態） | 「1 日/5 日內的贖回，真實能拿到多少錢覆蓋？」（覆蓋能力） |
| 計算 | 每筆持倉**全額市值**按「完全變現天數」歸 5 档桶：⌈市值 ÷ (ADTV×10%×(1−折扣))⌉ | **ADTV 約束下實際可變現額**：MIN(市值, ADTV×10%×(1−折扣)) + 現金/隔夜/到期額 |
| 輸出 | 5 档桶佔組合資產 %，雙場景各求和=100%（SFC 文檔 §1 表格） | DLA%≥7.5% / WLA%≥15%（UT Code §8.2(n)，雙場景） |
| 關鍵差異 | 一筆市值 1 億、日可賣 100 萬的債 → 歸 GT90D（⌈100⌉=100 天） | 同一筆債 → 1 日只認 100 萬（市場深度上限） |
| 用途 | 投資者/監管披露（Indicative Liquidity Profile） | 贖回壓力測試 / LMT 觸發判斷 |
| SQL / Sheet | `12_sfc_bucket_profile.sql` → 「SFC流動性分層」 | `13_sfc_dla_wla.sql` → 「SFC_DLA_WLA合規」 |

兩口徑共享持倉明細（`10_sfc_stress.sql` 落庫 `fsi.sfc_liquidity_stress`），僅匯總視角不同。

## 二、ADTV 三源行情管道

### 2.1 數據鏈路

```
fsi.mktdata_security_quotes（日級原始行情；WIND/YFINANCE/OPENBB 逐日報價）
    └─ fsi.fn_compute_adtv_30d(d) 聚合：過去30日算術平均，≥5日樣本
       → fsi.mktdata_adtv (data_source='MARKET')

Excel 手工導入（已平均的 ADTV 估計值）
    └─ 直接入 fsi.mktdata_adtv (data_source='EXCEL')

022a 種子（品種典型換手率 × 持倉市值）
    └─ fsi.mktdata_adtv (data_source='PROXY')

優先級：MARKET > EXCEL > PROXY
  · MARKET 聚合後自動 DELETE 同證券 EXCEL 行
  · EXCEL upsert 直接覆蓋 PROXY 行
```

### 2.2 三源導入工具（`2_processing/tools/mmf/import_adtv.py`）

| 源 | 命令 | 覆蓋範圍 | 驗證結果 |
|---|---|---|---|
| Excel 手工 | `--source excel --make-template/--file` | 全部品種兜底（模板預填持倉清單） | ✅ 3 證券導入，40032.HK=290萬生效 |
| yfinance | `--source yfinance` | 港交所掛牌品種（代碼映射 `fsi.para_security_alias`） | ✅ 0700.HK 32 行，ADTV=154.9 億（25 日樣本） |
| OpenBB | `--source openbb` | 同 yfinance（provider=yfinance），備用通道 | ✅ 33 行，結果與 yfinance 一致 |
| Wind (MCP) | `--source wind` | 場外債券/CD 專業源（4_mcp wind_get_price） | ✅ 通道就緒（需 Wind 帳號+alias 映射） |

### 2.3 品種覆蓋現實

- **CMU 債券/銀行間 CD**（.CMU 後綴）：Yahoo 無行情（場外品種）→ Excel 手工或 Wind
- **港交所掛牌票據/ETF/股票**：yfinance/OpenBB 可取
- 全部證券至少有 PROXY 代理值兜底，壓力測試永不出空值

## 三、驗證結果

### 3.1 行情管道（3 斷言通過）

| 斷言 | 結果 |
|---|---|
| yfinance 抓取→原始表→聚合 MARKET | ✅ 0700.HK ADTV=15,488,987,782（sample_days=25） |
| Excel 手工→EXCEL 源覆蓋 PROXY | ✅ 40032.HK 2,770,000(PROXY) → 2,900,000(EXCEL) |
| MARKET 覆蓋 EXCEL/PROXY | ✅ fn_compute_adtv_30d 內 DELETE 同證券低優先級行 |

### 3.2 雙口徑輸出（report_06 全 13 查詢成功）

**口徑 A（SFC流動性分層 sheet，每場景 5 行合計=100%）**：
- BHMMF001 Normal：1D 67.3% / 2-7D 11.8% / 8-30D 7.1% / 31-90D 13.8% / GT90D 0%
- BHMMF001 Stressed：1D 37.7%（存款零早破跌出 1D）/ GT90D 19.1%（信用債 ADTV 折扣變現天數翻倍）
- 每組合×場景固定 5 行（空桶補 0），符合 SFC 文檔表格版式

**口徑 B（SFC_DLA_WLA合規 sheet，資產類別貢獻拆分+合規匯總）**：
- BHMMF001 Normal：DLA=24.74% / WLA=26.02% → 合規
- BHMMF001 Stressed：DLA=15.46% / WLA=16.10% → 合規
- Stressed 場景 DLA 貢獻：CASH 44.7% + REV_REPO 42.5% + 隔夜存款 11.8% = 99%（債券貢獻 <1%，ADTV 約束生效）
- 定存 Stressed 零早破：DEPOSIT 1 日可變現從 3 億 → 5,000 萬（僅剩隔夜）

### 3.3 輸出文件

`2_processing/sql/mmf/output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx`

| Sheet | 內容 |
|---|---|
| SFC壓力測試原始 | 50 行持倉×場景明細（28 列，含三源 ADTV 與來源標記） |
| SFC流動性分層 | 口徑 A：5 档桶×雙場景，每場景合計=100% |
| SFC_DLA_WLA合規 | 口徑 B：資產類別 DLA/WLA 貢獻拆分 + 合規匯總行 |
| SFC壓力測試 | 綜述頁：雙口徑總覽 + LMT 治理 + 方法論說明 |

## 四、schema 增量（023/023a）

- `fsi.mktdata_security_quotes` — 證券日級原始行情（quote_date, security_code, source 唯一）
- `fsi.mktdata_adtv_import_log` — 導入審計日誌（rows/securities/adtv_total/file_name 可回溯）
- `fsi.fn_compute_adtv_30d(d DATE, days INT DEFAULT 30)` — 市場源聚合函數（同日多源按 WIND>YFINANCE>OPENBB 取優先級，≥5 日樣本）
- `fsi.para_security_alias` — 證券代碼 ↔ Yahoo/Wind ticker 映射（023a 種子預填港交所品種）

## 五、日常運行

```bash
# 1. 行情更新（三選一或組合）
cd 2_processing/tools/mmf
python import_adtv.py --source excel --make-template adtv.xlsx --date 2026-06-25  # 生成模板
python import_adtv.py --source excel --file adtv.xlsx --date 2026-06-25           # 手工導入
python import_adtv.py --source yfinance --date 2026-06-25                         # 公開行情
python import_adtv.py --source openbb --date 2026-06-25                           # 備用通道
python import_adtv.py --source wind --date 2026-06-25                             # Wind 專業源
python import_adtv.py --aggregate --date 2026-06-25                               # 僅重新聚合

# 2. 生成報表（含雙口徑 SFC sheet）
python run_report.py --report report_06 --port BHMMF001,BHMMF002 --date 2026-06-25
```

Wind 生產接入：在 `fsi.para_security_alias` 維護 Wind code 映射（如 'CN0002001234','WIND','260012.IB'），確保 WIND_USERNAME/WIND_PASSWORD 環境變量後執行 `--source wind`。

---

# 生產驗證記錄（2026-10-05 v3：真實券 + OpenBB/Bloomberg 混合鏈路）

## 持倉真實化
- 每資產類別：ETF（OpenBB 逐日行情驗證通道）+ 單只債券（Bloomberg 導出兜底）
- 12 債券（8 ETF + 4 單債 CUSIP：US912828FT00 美國2Y國債 / US037833BL17 Apple2042 / US594921BO55 Microsoft2033 / HKGB2026 港府債）+ 4 CD（PROXY 兜底）

## 三源行情鏈路（生產驗證）
| 源 | 證券 | 結果 |
|---|---|---|
| OpenBB（openbb_fetcher.py：多provider fallback+重試+並發+覆蓋報告） | 8 ETF | ✅ 264行 25日樣本，8/8 成功 |
| EXCEL 逐日（Bloomberg 導出格式，--source excel-daily） | 4 單債 | ✅ 88行 19日樣本 |
| PROXY（品種換手率代理） | 4 CD（場外本無公開行情） | ✅ 兜底生效 |

## SFC 文檔逐條驗證（估值日 2026-06-25）
1. §1 表格還原：雙場景 5 檔合計=100.00% ✓（BHMMF001 Normal 75.04/12.78/0/6.38/5.81；Stressed 46.00/12.78/0/23.80/17.42）
2. §1(ii) DLA≥7.5%/WLA≥15% 雙場景：4/4 合規 ✓（BHMMF001: 27.64/28.24 → 18.49/18.97）
3. §1(iii) 變現規模=ADTV 約束可覆蓋額 ✓
4. §1(iv) Stressed 假設：零早破（定存 1.5億→0、31-90D 桶）✓；50% haircut（LQD 285M→142.5M）✓；價差擴大（Apple債 1500→7500元）✓
5. §2(a) 10% ADTV 參與率 + 30 日 ADTV：全券 10% ✓，真實 ADTV（美國2Y國債 495億/Apple債 3.4億）✓
6. §2(b) LMT 治理與方法論：Note(i)-(iv) + Basis of Liquidity Classification 完整 ✓

## 輸出
output/report_06/report_06_BHMMF001_BHMMF002_20260625.xlsx（25 sheet：15 展示層 + 10 原始層；SFC 4 表）
