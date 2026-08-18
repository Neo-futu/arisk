# 投資風險頁面模塊核驗與留檔

本文用於生產環境核驗與記錄：每個頁面、每個模塊的功能、主要數據表、以及可直接執行的 SQL / Python 驗證示例。

## 1. 核驗範圍

- 前端菜單：投資風險分析下全部頁面
- 服務鏈路：frontend -> backend -> processing -> PostgreSQL
- 核驗基準：
  - 前端頁面模塊實現
  - processing 對應 API 的實際查表邏輯

推薦啟動命令（含核驗常用服務）：

python scripts/dev.py --parts processing entry backend frontend autorisk mcp-gateway

---

## 2. 頁面與模塊清單

說明：本章每一行就是一個可獨立核驗的功能模塊。`SQL 示例` 是該模塊的局部核驗片段，不是整頁全量 SQL。

### 2.0 儀表板頁（/）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| 基金/日期選擇與最近有效日回退 | 查詢指定日期之前最近可用風控數據日期 | fsi.balance_portfolio_nav | SQL-DB-01 | PY-DB-01 |
| 總 NAV | 展示基金在查詢日的總資產淨值（HKD） | fsi.balance_portfolio_nav | SQL-DB-NAV-01 | PY-DB-01 |
| 風控 KPI（NAV/WAM/WAL/合規） | 展示核心風控與合規狀態 | fsi.balance_portfolio_nav, fsi.balance_portfolio_asset, fsi.balance_bond, fsi.balance_cd, fsi.balance_deposit, fsi.balance_repo, fsi.balance_cash | SQL-DB-02 | PY-DB-01 |
| SFC 合規明細 | 顯示 WAM/WAL/日流動性/週流動性規則 | 同上 | SQL-DB-02 | PY-DB-01 |
| 資產配置（%NAV） | 顯示資產類別占比結構 | fsi.balance_portfolio_asset, fsi.balance_portfolio_mmf | SQL-DB-03 | PY-DB-01 |

### 2.1 模塊總覽頁（/investment-risk）

| 模塊 | 功能 | 主要數據來源 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|---|
| 實戰風控儀表盤（基金/日期/回退） | 選基金、選日期，回退到最近有數據日 | overview API + fallback | fsi.balance_portfolio_nav, fsi.para_portfolio, fsi.balance_portfolio_asset, fsi.balance_stock | SQL-OV-01 | PY-OV-01 |
| 風險趨勢圖 | 展示業績區間收益趨勢 | overview.performance | 同上 | SQL-OV-02 | PY-OV-01 |
| 風險因子構成 | 展示資產構成占比 | overview.asset_allocation | fsi.balance_portfolio_asset | SQL-OV-03 | PY-OV-01 |
| 完整分析清單 | 本地風險項篩選、導出 | 前端本地列表 | 無（前端靜態） | N/A | N/A |
| 快速分析入口 | 跳轉至各功能頁 | 前端路由 | 無 | N/A | N/A |
| 主題卡片區 | 展示五大主題能力 | 前端配置內容 | 無 | N/A | N/A |
| 系統架構整合區 | 展示層級說明 | 前端文案 | 無 | N/A | N/A |

### 2.2 組合概況頁（/investment-risk/overview）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（基金、淨資產、單位淨值、當日收益） | 概覽核心投資信息 | fsi.para_portfolio, fsi.balance_portfolio_nav | SQL-OV-01 | PY-OV-01 |
| 區間收益走勢 | 顯示 cumulative return 時序 | fsi.balance_portfolio_nav | SQL-OV-02 | PY-OV-TS-01 |
| 資產配置結構（圖） | 顯示資產權重 | fsi.balance_portfolio_asset | SQL-OV-03 | PY-OV-01 |
| 總體業績（表） | 多區間收益明細 | fsi.balance_portfolio_nav | SQL-OV-02 | PY-OV-01 |
| 資產配置（表） | 類別、市值、佔比 | fsi.balance_portfolio_asset | SQL-OV-03 | PY-OV-01 |
| 前十大個股（搜索/導出） | 持倉股明細 | fsi.balance_stock | SQL-OV-04 | PY-OV-01 |
| 股票行業配置 | 行業聚合分佈 | fsi.balance_stock | SQL-OV-05 | PY-OV-01 |

### 2.3 風險指標頁（/investment-risk/indicators）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（收益、波動、回撤、換手、Beta） | 風險核心指標總覽 | fsi.balance_portfolio_nav, fsi.transact_stock, fsi.balance_stock, fsi.mktdata_quotes, fsi.mktdata_index_quotes, fsi.para_portfolio_benchmark | SQL-RI-01 | PY-RI-01 |
| 核心風險輪廓（圖） | 聚合展示收益/波動/回撤/換手/VaR | 同上 + VaR 結果 | SQL-RI-01 | PY-RI-01 + PY-VAR-01 |
| 滾動波動率時序 | 時序波動追蹤 | fsi.balance_portfolio_nav | SQL-RI-02 | PY-RI-TS-01 |
| 回撤與滾動 VaR 時序摘要 | 近端風險時序 | fsi.balance_portfolio_nav | SQL-RI-02 | PY-RI-TS-01 |
| 股票交易換手率明細 | 買賣額、平均股票餘額 | fsi.transact_stock, fsi.balance_stock | SQL-RI-03 | PY-RI-01 |
| 個股 Beta 貢獻 | 個股 Beta 與權重 | fsi.balance_stock, fsi.mktdata_quotes, fsi.mktdata_index_quotes | SQL-RI-04 | PY-RI-01 |
| VaR 三方法對比 | historical / monte_carlo / distribution | fsi.balance_portfolio_nav（回退：fsi.nav_history / fsi.raw_nav） | SQL-VAR-01 | PY-VAR-01 |

### 2.4 績效歸因頁（/investment-risk/attribution）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（組合/基準/超額/Brinson 三效應） | 歸因總覽 | fsi.balance_portfolio_nav, fsi.para_portfolio_benchmark, fsi.mktdata_index_quotes | SQL-AT-01 | PY-AT-01 |
| 超額收益累積時序 | active return 累積曲線 | fsi.balance_portfolio_nav, fsi.mktdata_index_quotes | SQL-AT-02 | PY-AT-TS-01 |
| 日度損益貢獻時序 | 逐日貢獻 | fsi.transact_pnl_item | SQL-AT-03 | PY-AT-TS-01 |
| 各類資產收益貢獻 | 按資產類別匯總 PnL | fsi.transact_pnl_item | SQL-AT-04 | PY-AT-01 |
| 行業配置收益與超配（Brinson） | 行業級配置/選股/交互效應 | fsi.balance_stock, fsi.mktdata_quotes, fsi.mktdata_index_component, fsi.mktdata_stock_static | SQL-AT-05 | PY-AT-01 |
| 個股損益前後十大 | 股票損益排名 | fsi.transact_pnl_item, fsi.mktdata_stock_static | SQL-AT-06 | PY-AT-01 |
| 日均十大重倉股 | 平均權重與持倉天數 | fsi.balance_stock | SQL-AT-07 | PY-AT-01 |

### 2.5 利率與信用敏感度頁（/investment-risk/rates-credit）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（債券持倉、久期、DV01、CS01、HHI） | 利率/信用敏感度核心數值 | fsi.balance_portfolio_nav, fsi.balance_bond | SQL-RC-01 | PY-RC-01 |
| KRD 曲線視圖 | 期限桶權重展示 | fsi.balance_bond | SQL-RC-02 | PY-RC-01 |
| 評級分布 | 信用評級權重 | fsi.balance_bond | SQL-RC-03 | PY-RC-01 |
| KRD 期限桶暴露（表） | 桶級明細 | fsi.balance_bond | SQL-RC-02 | PY-RC-01 |
| 發行人集中度 Top10 | issuer 集中度與權重 | fsi.balance_bond | SQL-RC-04 | PY-RC-01 |

### 2.6 流動性與壓力測試頁（/investment-risk/liquidity-stress）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（TTL 10/25/50、覆蓋比） | 流動性關鍵門檻 | fsi.balance_portfolio_nav, fsi.balance_portfolio_asset | SQL-LS-01 | PY-LS-01 |
| TTL 壓測曲線 | 變現時間曲線 | fsi.balance_portfolio_asset | SQL-LS-02 | PY-LS-01 |
| 流動性階梯結構（圖） | 累積 NAV 佔比 | fsi.balance_portfolio_asset | SQL-LS-02 | PY-LS-01 |
| 壓測摘要 | 贖回/利率衝擊/壓測後 NAV | fsi.balance_portfolio_nav, fsi.balance_bond | SQL-LS-03 | PY-LS-01 |
| 流動性階梯明細（表） | 資產類別分層明細 | fsi.balance_portfolio_asset | SQL-LS-02 | PY-LS-01 |

### 2.7 風險預算與前置試算頁（/investment-risk/pretrade-budget）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（決策、久期、交易衝擊） | 試算輸出總覽 | fsi.balance_portfolio_nav, fsi.balance_bond | SQL-PT-01 | PY-PT-01 |
| 久期與限額軌跡 | 當前/試算後/限額對比 | fsi.balance_bond | SQL-PT-02 | PY-PT-01 |
| 前置試算決策摘要 | 交易假設與告警顯示 | 計算結果 | SQL-PT-01 | PY-PT-01 |
| 限額對比（表） | 指標門檻對比 | 計算結果 + 持倉數據 | SQL-PT-02 | PY-PT-01 |

### 2.8 宏觀與市場動態頁（/investment-risk/macro-dynamics）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（regime、波動、樣本） | 宏觀狀態摘要 | fsi.mktdata_index_quotes, fsi.balance_portfolio_nav | SQL-MA-01 | PY-MA-01 |
| 宏觀指標收益輪廓 | 各宏觀指標收益/波動 | fsi.mktdata_index_quotes | SQL-MA-02 | PY-MA-01 |
| 基金對市場關聯 | 基金與指數相關性 | fsi.mktdata_index_quotes, fsi.balance_portfolio_nav | SQL-MA-03 | PY-MA-01 |
| 宏觀指標明細（表） | 指標級詳細數據 | fsi.mktdata_index_quotes | SQL-MA-02 | PY-MA-01 |
| 跨市場關聯 Top | 市場對相關性明細 | fsi.mktdata_index_quotes | SQL-MA-03 | PY-MA-01 |

### 2.9 基本面因子與行為風險頁（/investment-risk/factor-behavior）

| 模塊 | 功能 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|
| KPI 卡片（Momentum/LowVol/Size/HHI） | 因子與集中度概覽 | fsi.balance_stock, fsi.mktdata_quotes | SQL-FB-01 | PY-FB-01 |
| 風格因子暴露（圖） | 因子暴露量化 | fsi.balance_stock, fsi.mktdata_quotes | SQL-FB-01 | PY-FB-01 |
| 行業集中度結構（圖） | 行業權重分佈 | fsi.balance_stock | SQL-FB-02 | PY-FB-01 |
| 交易擁擠度 Top（表） | 擁擠標的排序 | fsi.transact_stock, fsi.balance_stock | SQL-FB-03 | PY-FB-01 |

### 2.10 指標驗證頁（/investment-risk/validation）

| 模塊 | 功能 | 主要數據來源 | 主要數據表 | SQL 示例 | Python 示例 |
|---|---|---|---|---|---|
| 指標過濾/分組 | 按分類選擇指標批量執行 | processingIndicatorCatalog + endpointKey | 視 endpoint 而定 | 對應各頁 SQL | 對應各頁 Python |
| 單指標執行 | 調用 endpoint 返回摘要/原始結果 | fsiApi 對應接口 | 視 endpoint 而定 | 對應各頁 SQL | 對應各頁 Python |
| 全量執行摘要 | 統計通過/失敗/耗時 | 前端運行結果 | 無（執行層） | N/A | N/A |

---

## 3. 模塊級 SQL 驗證片段（可直接改 fund_id/date 執行）

使用方式：

1. 先在第 2 章定位需要核驗的頁面與模塊。
2. 執行該模塊對應 SQL 片段（例如 SQL-AT-06）。
3. 只修該模塊，不必一次跑完整頁全部 SQL。

### SQL-DB-01 儀表板最近有效日

```sql
SELECT MAX(evaluate_date) AS latest_date
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date <= '2026-06-25';
```

### SQL-DB-NAV-01 儀表板總 NAV

```sql
SELECT evaluate_date,
       net_asset AS total_nav_hkd,
       unit_nav,
       acc_unit_nav
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25';
```

### SQL-DB-02 儀表板合規核心數據

```sql
SELECT net_asset
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25';

SELECT
  SUM(CASE WHEN asset_class::text IN ('CASH','DEPOSIT','CD','REPO') THEN COALESCE(market_value_base, market_value, 0) ELSE 0 END) AS liquid_mv,
  SUM(COALESCE(market_value_base, market_value, 0)) AS total_mv
FROM fsi.balance_portfolio_asset
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25';
```

### SQL-DB-03 儀表板資產配置

```sql
SELECT asset_class::text,
       SUM(COALESCE(market_value_base, market_value, 0)) AS mv
FROM fsi.balance_portfolio_asset
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25'
GROUP BY asset_class::text
ORDER BY mv DESC;
```

### SQL-OV-01 基金與 NAV 基礎

```sql
SELECT p.port_id, p.port_name, p.port_type, p.base_currency,
       n.evaluate_date, n.unit_nav, n.acc_unit_nav, n.net_asset
FROM fsi.para_portfolio p
LEFT JOIN fsi.balance_portfolio_nav n
  ON p.port_id = n.port_id
WHERE p.port_id = 'BHMMF001'
ORDER BY n.evaluate_date DESC
LIMIT 10;
```

### SQL-OV-02 NAV 區間序列

```sql
SELECT evaluate_date, COALESCE(acc_unit_nav, unit_nav) AS nav, net_asset
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-01-01' AND '2026-06-25'
ORDER BY evaluate_date;
```

### SQL-OV-03 資產配置

```sql
SELECT asset_class, SUM(COALESCE(market_value_base, market_value, 0)) AS mv
FROM fsi.balance_portfolio_asset
WHERE port_id = 'BHMMF001' AND evaluate_date = '2026-06-25'
GROUP BY asset_class
ORDER BY mv DESC;
```

### SQL-OV-04 前十大個股

```sql
SELECT security_code, security_name, sector,
       COALESCE(market_value_base, market_value, 0) AS mv,
       COALESCE(weight_pct, 0) AS weight_pct
FROM fsi.balance_stock
WHERE port_id = 'BHMMF001' AND evaluate_date = '2026-06-25'
ORDER BY weight_pct DESC
LIMIT 10;
```

### SQL-OV-05 股票行業配置

```sql
SELECT COALESCE(sector, '未分類') AS sector,
       COUNT(*) AS positions,
       SUM(COALESCE(market_value_base, market_value, 0)) AS mv,
       SUM(COALESCE(weight_pct, 0)) AS weight_pct
FROM fsi.balance_stock
WHERE port_id = 'BHMMF001' AND evaluate_date = '2026-06-25'
GROUP BY COALESCE(sector, '未分類')
ORDER BY weight_pct DESC;
```

### SQL-RI-01 風險指標基礎（NAV + 換手）

```sql
-- NAV 區間
SELECT evaluate_date, COALESCE(acc_unit_nav, unit_nav) AS nav
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
ORDER BY evaluate_date;

-- 股票交易
SELECT SUM(COALESCE(trade_amount_base, trade_amount, 0)) AS stock_trade_amt
FROM fsi.transact_stock
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25';
```

### SQL-RI-02 風險時序

```sql
SELECT evaluate_date, COALESCE(acc_unit_nav, unit_nav) AS nav
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-01-01' AND '2026-06-25'
ORDER BY evaluate_date;
```

### SQL-RI-03 股票餘額與交易

```sql
SELECT evaluate_date,
       SUM(COALESCE(market_value_base, market_value, 0)) AS stock_mv
FROM fsi.balance_stock
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
GROUP BY evaluate_date
ORDER BY evaluate_date;
```

### SQL-RI-04 Beta 估算數據

```sql
-- 取最新持倉股票與其行情
SELECT q.price_date, q.security_code, q.close_price
FROM fsi.mktdata_quotes q
WHERE q.price_type = 'CLOSE'
  AND q.price_date BETWEEN '2026-03-27' AND '2026-06-25'
  AND EXISTS (
      SELECT 1
      FROM fsi.balance_stock b
      WHERE b.port_id = 'BHMMF001'
        AND b.security_code = q.security_code
  )
ORDER BY q.security_code, q.price_date;
```

### SQL-VAR-01 VaR 序列數據

```sql
SELECT evaluate_date, net_asset
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2025-06-25' AND '2026-06-25'
  AND net_asset IS NOT NULL
ORDER BY evaluate_date;
```

### SQL-AT-01 歸因基礎（基金 + 基準）

```sql
SELECT evaluate_date, COALESCE(acc_unit_nav, unit_nav) AS nav
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
ORDER BY evaluate_date;

SELECT benchmark_id, begin_date, end_date
FROM fsi.para_portfolio_benchmark
WHERE port_id = 'BHMMF001'
ORDER BY begin_date DESC;
```

### SQL-AT-02 累積收益時序

```sql
SELECT price_date, close_price
FROM fsi.mktdata_index_quotes
WHERE index_code = '請替換為基準代碼'
  AND price_date BETWEEN '2026-03-27' AND '2026-06-25'
ORDER BY price_date;
```

### SQL-AT-03 日度損益貢獻

```sql
SELECT evaluate_date,
       SUM(COALESCE(net_pnl_base, net_pnl, 0)) AS net_pnl
FROM fsi.transact_pnl_item
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
GROUP BY evaluate_date
ORDER BY evaluate_date;
```

### SQL-AT-04 資產收益貢獻

```sql
SELECT COALESCE(asset_class::text, 'OTHER') AS asset_class,
       SUM(COALESCE(mtm_delta, 0)) AS mtm_delta,
       SUM(COALESCE(interest_income, 0)) AS interest_income,
       SUM(COALESCE(realized_gain, 0)) AS realized_gain,
       SUM(COALESCE(fx_pnl, 0)) AS fx_pnl,
       SUM(COALESCE(net_pnl_base, net_pnl, 0)) AS net_pnl
FROM fsi.transact_pnl_item
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
GROUP BY COALESCE(asset_class::text, 'OTHER')
ORDER BY net_pnl DESC;
```

### SQL-AT-05 行業 Brinson 原始數據

```sql
SELECT security_code, COALESCE(sector, '未分類') AS sector,
       AVG(COALESCE(weight_pct, 0))/100.0 AS avg_weight
FROM fsi.balance_stock
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
GROUP BY security_code, COALESCE(sector, '未分類');
```

### SQL-AT-06 個股損益排名

```sql
SELECT p.security_code,
       COALESCE(MAX(s.security_name), p.security_code, '未分類') AS security_name,
       COALESCE(MAX(s.sector_level1), '未分類') AS sector,
       SUM(COALESCE(p.net_pnl_base, p.net_pnl, 0)) AS net_pnl
FROM fsi.transact_pnl_item p
LEFT JOIN fsi.mktdata_stock_static s ON s.security_code = p.security_code
WHERE p.port_id = 'BHMMF001'
  AND p.evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
  AND p.asset_class::text = 'STOCK'
GROUP BY p.security_code
ORDER BY net_pnl DESC
LIMIT 20;
```

### SQL-AT-07 日均重倉

```sql
SELECT security_code,
       MAX(security_name) AS security_name,
       COALESCE(sector, '未分類') AS sector,
       AVG(COALESCE(weight_pct, 0)) AS avg_weight_pct,
       COUNT(DISTINCT evaluate_date) AS holding_days
FROM fsi.balance_stock
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
GROUP BY security_code, COALESCE(sector, '未分類')
ORDER BY avg_weight_pct DESC
LIMIT 10;
```

### SQL-RC-01 利率信用核心

```sql
SELECT net_asset
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date <= '2026-06-25'
ORDER BY evaluate_date DESC
LIMIT 1;

SELECT COUNT(*) AS bond_rows,
       SUM(COALESCE(market_value_base, market_value, 0)) AS bond_mv
FROM fsi.balance_bond
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25';
```

### SQL-RC-02 KRD 期限桶

```sql
SELECT maturity_bucket,
       SUM(COALESCE(market_value_base, market_value, 0)) AS mv,
       SUM(COALESCE(duration, 0) * COALESCE(market_value_base, market_value, 0)) AS duration_weighted_mv
FROM fsi.balance_bond
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25'
GROUP BY maturity_bucket
ORDER BY maturity_bucket;
```

### SQL-RC-03 評級分布

```sql
SELECT COALESCE(rating, 'NR') AS rating,
       SUM(COALESCE(market_value_base, market_value, 0)) AS mv
FROM fsi.balance_bond
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25'
GROUP BY COALESCE(rating, 'NR')
ORDER BY mv DESC;
```

### SQL-RC-04 發行人集中度

```sql
SELECT COALESCE(issuer_name, 'UNKNOWN') AS issuer,
       SUM(COALESCE(market_value_base, market_value, 0)) AS mv
FROM fsi.balance_bond
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25'
GROUP BY COALESCE(issuer_name, 'UNKNOWN')
ORDER BY mv DESC
LIMIT 10;
```

### SQL-LS-01 流動性門檻基礎

```sql
SELECT net_asset
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date <= '2026-06-25'
ORDER BY evaluate_date DESC
LIMIT 1;
```

### SQL-LS-02 流動性階梯

```sql
SELECT asset_class::text,
       SUM(COALESCE(market_value_base, market_value, 0)) AS mv
FROM fsi.balance_portfolio_asset
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25'
GROUP BY asset_class::text
ORDER BY mv DESC;
```

### SQL-LS-03 利率衝擊敏感資產

```sql
SELECT SUM(COALESCE(market_value_base, market_value, 0) * COALESCE(duration, 0)) AS dv01_base
FROM fsi.balance_bond
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25';
```

### SQL-PT-01 前置試算輸入基礎

```sql
SELECT net_asset
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date <= '2026-06-25'
ORDER BY evaluate_date DESC
LIMIT 1;
```

### SQL-PT-02 久期與發行人暴露

```sql
SELECT issuer_name,
       SUM(COALESCE(market_value_base, market_value, 0)) AS mv,
       AVG(COALESCE(duration, 0)) AS avg_duration
FROM fsi.balance_bond
WHERE port_id = 'BHMMF001'
  AND evaluate_date = '2026-06-25'
GROUP BY issuer_name
ORDER BY mv DESC
LIMIT 20;
```

### SQL-MA-01 宏觀 regime 基礎

```sql
SELECT evaluate_date, COALESCE(acc_unit_nav, unit_nav) AS nav
FROM fsi.balance_portfolio_nav
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-01-01' AND '2026-06-25'
ORDER BY evaluate_date;
```

### SQL-MA-02 宏觀指標行情

```sql
SELECT index_code, price_date, close_price
FROM fsi.mktdata_index_quotes
WHERE index_code IN ('HSI', 'HSTECH', 'US10Y', 'DXY')
  AND price_date BETWEEN '2026-01-01' AND '2026-06-25'
ORDER BY index_code, price_date;
```

### SQL-MA-03 跨市場關聯原始序列

```sql
SELECT index_code, price_date, close_price
FROM fsi.mktdata_index_quotes
WHERE price_date BETWEEN '2026-01-01' AND '2026-06-25'
ORDER BY index_code, price_date;
```

### SQL-FB-01 因子暴露輸入（持倉 + 行情）

```sql
SELECT b.evaluate_date, b.security_code, b.security_name, b.sector,
       b.weight_pct, q.close_price
FROM fsi.balance_stock b
LEFT JOIN fsi.mktdata_quotes q
  ON q.security_code = b.security_code
 AND q.price_type = 'CLOSE'
 AND q.price_date = b.evaluate_date
WHERE b.port_id = 'BHMMF001'
  AND b.evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
ORDER BY b.evaluate_date, b.security_code;
```

### SQL-FB-02 行業集中度

```sql
SELECT COALESCE(sector, '未分類') AS sector,
       AVG(COALESCE(weight_pct, 0)) AS avg_weight_pct
FROM fsi.balance_stock
WHERE port_id = 'BHMMF001'
  AND evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
GROUP BY COALESCE(sector, '未分類')
ORDER BY avg_weight_pct DESC;
```

### SQL-FB-03 交易擁擠度輸入

```sql
SELECT t.security_code,
       SUM(COALESCE(t.trade_quantity, 0)) AS trade_qty,
       AVG(COALESCE(b.quantity, 0)) AS avg_position_qty
FROM fsi.transact_stock t
LEFT JOIN fsi.balance_stock b
  ON b.port_id = t.port_id
 AND b.security_code = t.security_code
 AND b.evaluate_date = t.evaluate_date
WHERE t.port_id = 'BHMMF001'
  AND t.evaluate_date BETWEEN '2026-03-27' AND '2026-06-25'
GROUP BY t.security_code
ORDER BY trade_qty DESC
LIMIT 20;
```

---

## 4. Python 驗證示例（直接調 processing，無需 JWT）

前置條件：processing 已啟動在 8001，且 X-API-Key 有效。

建議按模塊單獨執行，不必一次請求全部頁面 API。

### PY-DB-01 儀表板暴露與最近有效日

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}

latest = requests.get(
  "http://127.0.0.1:8001/risk/exposure-latest-date/BHMMF001",
  headers=headers,
  params={"as_of_date": "2026-06-25"},
  timeout=20,
).json()

effective_date = latest.get("effective_date", "2026-06-25")

exposure = requests.get(
  "http://127.0.0.1:8001/risk/exposure/BHMMF001",
  headers=headers,
  params={"as_of_date": effective_date},
  timeout=20,
).json()

print({"latest": latest, "exposure": exposure})
```

### PY-OV-01 組合概況

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/overview/BHMMF001"
params = {"as_of_date": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-OV-TS-01 組合概況時序

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/overview-timeseries/BHMMF001"
params = {"start": "2026-01-01", "end": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-RI-01 風險指標

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/risk-indicators/BHMMF001"
params = {"start": "2026-03-27", "end": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-RI-TS-01 風險指標時序

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/risk-indicators-timeseries/BHMMF001"
params = {"start": "2026-03-27", "end": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-VAR-01 VaR 三方法

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/risk/var-compare/BHMMF001"
params = {"as_of_date": "2026-06-25", "confidence": 0.99, "horizon_days": 1}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-AT-01 績效歸因

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/attribution/BHMMF001"
params = {"start": "2026-03-27", "end": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-AT-TS-01 歸因時序

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/attribution-timeseries/BHMMF001"
params = {"start": "2026-03-27", "end": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-RC-01 利率與信用敏感度

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/rates-credit/BHMMF001"
params = {"as_of_date": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-LS-01 流動性壓測

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/liquidity-stress/BHMMF001"
params = {"as_of_date": "2026-06-25", "redemption_pct": 20, "rate_shock_bps": 50}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-PT-01 前置試算

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/pretrade-check/BHMMF001"
params = {
    "as_of_date": "2026-06-25",
    "trade_amount": 10000000,
    "trade_side": "BUY",
    "asset_class": "BOND_CORP",
    "duration_years": 2,
    "issuer_name": "UNKNOWN_ISSUER",
}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-MA-01 宏觀與市場動態

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/macro-dynamics/BHMMF001"
params = {"start": "2026-03-27", "end": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

### PY-FB-01 因子與行為風險

```python
import requests

headers = {"X-API-Key": "internal_key_change_me"}
url = "http://127.0.0.1:8001/investment/factor-behavior/BHMMF001"
params = {"start": "2026-03-27", "end": "2026-06-25"}
print(requests.get(url, headers=headers, params=params, timeout=20).json())
```

---

## 5. 使用建議（核驗流程）

1. 先跑 Python 示例，確認 API 層可返回。
2. 再跑 SQL，確認每個模塊背後原始數據可追溯。
3. 最後對照前端頁面，檢查字段是否完整映射（名稱、口徑、時間區間）。
4. 對空數據模塊，優先排查：日期區間、基準配置、行情表是否有樣本。
