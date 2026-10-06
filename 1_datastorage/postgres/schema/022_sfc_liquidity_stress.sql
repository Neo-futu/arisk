-- ============================================================
-- 022_sfc_liquidity_stress.sql  SFC 香港貨幣市場基金壓力測試
-- FSI — 對應 lmt-mmf-test-sfc.docx（Indicative Liquidity Profile）
-- 依賴：004_balance.sql（balance_bond/cd/deposit/repo/cash/portfolio_nav）
--       005_mktdata.sql（mktdata_quotes 行情）
--
-- 三張表：
--   1. fsi.mktdata_adtv            — 證券 30 日平均日交易量（Wind/MCP 入庫）
--   2. fsi.sfc_liquidity_bucket_def — 變現係數/市場參與率/ADTV 折扣配置
--   3. fsi.sfc_liquidity_stress    — SFC 流動性壓力測試結果落庫（按持倉 × 場景 × 時間桶）
--
-- SFC 口徑（lmt-mmf-test-sfc.docx）：
--   5 檔時間桶：1D / 2-7D / 8-30D / 31-90D / >90D（非累計，Normal+Stressed 雙場景求和=100%）
--   Normal：合約到期 + 二級市場 10% ADTV
--   Stressed：合約到期（存款零早破）+ 二級市場 10% × ADTV × (1-50% haircut)
--   DLA ≥ 7.5% / WLA ≥ 15%（雙場景均須滿足，UT Code §8.2(n)）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 證券平均日交易量（ADTV）表
--   來源：Wind/MCP 行情入庫；未入庫時由變現係數配置表用品種典型換手率代理
--   口徑：過去 30 個交易日成交量（turnover，元）的算術平均
--   SFC 用法：可變現規模 = MIN(持倉市值, ADTV × 10% × (1 - haircut))
-- ============================================================
CREATE TABLE IF NOT EXISTS fsi.mktdata_adtv (
    adtv_date        DATE         NOT NULL,          -- 計算截止日（通常=估值日）
    security_code    VARCHAR(32)  NOT NULL,          -- 證券代碼（與 balance_bond/cd.security_code 對齊）
    market_id        VARCHAR(16),                    -- 市場（HKEX/IB/CIBM/OTC）
    adtv_30d         NUMERIC(24,2) NOT NULL DEFAULT 0,-- 30 日平均日成交額（元，本幣）
    adtv_30d_volume  NUMERIC(24,4),                  -- 30 日平均日成交量（手/份）— 輔助
    sample_days      INTEGER      NOT NULL DEFAULT 30,-- 樣本天數
    turnover_pct     NUMERIC(8,6),                    -- 樣本期日均換手率（成交額/流通盤）
    data_source      VARCHAR(16)  NOT NULL DEFAULT 'WIND', -- WIND/MCP/PROXY（代理值標記）
    loaded_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (adtv_date, security_code)
);
COMMENT ON TABLE  fsi.mktdata_adtv IS '證券 30 日平均日成交額（ADTV）：SFC 流動性壓力測試二級市場可變現規模計算依據';
COMMENT ON COLUMN fsi.mktdata_adtv.adtv_30d IS '30 日平均日成交額（元）：SFC 文檔要求「過去 30 天 ADTV」';
COMMENT ON COLUMN fsi.mktdata_adtv.data_source IS 'WIND/MCP=行情入庫；PROXY=用品種典型換手率代理（待行情接入後覆蓋）';

CREATE INDEX IF NOT EXISTS idx_mkt_adtv_date     ON fsi.mktdata_adtv(adtv_date DESC);
CREATE INDEX IF NOT EXISTS idx_mkt_adtv_security ON fsi.mktdata_adtv(security_code, adtv_date DESC);

-- ────────────────────────────────────────────────────────────
-- 2. SFC 變現係數 / 市場參與率 / ADTV 折扣 配置表
--   按資產類別 + 場景（Normal/Stressed）配置：
--     market_participation_pct — 二級市場最大參與率（SFC 文檔 §2(a) 10%）
--     adtv_haircut_pct         — ADTV 折扣（SFC 文檔 §1(iv) Stressed 50%）
--     early_break_pct          — 存款提前支取比例（SFC 文檔 §1(iv) Stressed 零早破=0%）
--     bid_ask_cost_bps         — 壓力下買賣價差成本（bp，用於變現成本扣減）
--     proxy_turnover_pct       — 無行情時品種典型日均換手率（代理 ADTV 用）
-- ============================================================
CREATE TABLE IF NOT EXISTS fsi.sfc_liquidity_bucket_def (
    asset_category        VARCHAR(32) NOT NULL,      -- CASH/DEPOSIT/CD/BOND_GOVT/BOND_CORP/BOND_FLOAT/REV_REPO/REPO
    scenario              VARCHAR(16) NOT NULL,      -- NORMAL / STRESSED
    market_participation_pct NUMERIC(8,6) NOT NULL DEFAULT 0.10, -- 二級市場參與率（默認 10%）
    adtv_haircut_pct        NUMERIC(8,6) NOT NULL DEFAULT 0.00,  -- ADTV 折扣（Stressed 50%）
    early_break_pct         NUMERIC(8,6) NOT NULL DEFAULT 0.00,  -- 存款提前支取比例
    bid_ask_cost_bps        NUMERIC(10,4) NOT NULL DEFAULT 0,    -- 買賣價差成本（bp）
    proxy_turnover_pct      NUMERIC(8,6) NOT NULL DEFAULT 0,     -- 代理日均換手率（成交額/流通盤）
    liq_ratio_static        NUMERIC(8,6),                       -- 靜態變現係數（向後兼容 42_stress_result.sql 口徑）
    note                   VARCHAR(200),
    PRIMARY KEY (asset_category, scenario)
);
COMMENT ON TABLE fsi.sfc_liquidity_bucket_def IS 'SFC 流動性壓力測試參數：按資產類別×場景配置參與率/折扣/早破比例';
COMMENT ON COLUMN fsi.sfc_liquidity_bucket_def.market_participation_pct IS '二級市場最大參與率：SFC 文檔 §2(a) 取 ADTV 的 10%';
COMMENT ON COLUMN fsi.sfc_liquidity_bucket_def.adtv_haircut_pct IS 'ADTV 折扣：SFC 文檔 §1(iv) Stressed 場景對 ADTV 50% haircut';
COMMENT ON COLUMN fsi.sfc_liquidity_bucket_def.early_break_pct IS '存款提前支取比例：SFC 文檔 §1(iv) Stressed 零早破=0%（僅合約到期變現）';

-- ────────────────────────────────────────────────────────────
-- 3. SFC 流動性壓力測試結果表（按持倉 × 場景 × 時間桶）
--   時間桶：1D / 2-7D / 8-30D / 31-90D / GT90D（>90 天）
--   一筆持倉在 Normal/Stressed 兩場景各落一行（liquidation_bucket）
--   匯總到 5 檔分層由 SQL 動態 GROUP BY 完成（不必預聚合）
-- ============================================================
CREATE TABLE IF NOT EXISTS fsi.sfc_liquidity_stress (
    evaluate_date         DATE         NOT NULL,
    port_id               VARCHAR(16)  NOT NULL,
    security_code         VARCHAR(48)  NOT NULL,     -- 債券/CD security_code；存款 deposit_id；回購 repo_id；CASH='CASH'
    security_name         VARCHAR(200),
    asset_category        VARCHAR(32)  NOT NULL,     -- CASH/DEPOSIT/CD/BOND_GOVT/BOND_CORP/BOND_FLOAT/REV_REPO/REPO
    scenario              VARCHAR(16)  NOT NULL,     -- NORMAL / STRESSED
    market_value          NUMERIC(24,2) NOT NULL,     -- 持倉市值（元）
    duration              NUMERIC(12,8),             -- 有效久期（年）
    rate_shock_bps        NUMERIC(10,4) NOT NULL DEFAULT 50,  -- 利率衝擊（bp，默認 +50bp）
    stressed_mv           NUMERIC(24,2),             -- 利率衝擊後市值 = market_value × (1 - duration × shock/10000)
    stressed_loss         NUMERIC(24,2),             -- 利率壓力損失 = market_value - stressed_mv
    adtv_30d              NUMERIC(24,2),             -- 30 日 ADTV（元）；無行情時為代理值
    tradable_size          NUMERIC(24,2),            -- 二級市場日可變現規模 = ADTV × 參與率 × (1 - 折扣)
    realizable_amount      NUMERIC(24,2),            -- 1 交易日內可變現金額（DLA 口徑）
    realizable_5d_amount   NUMERIC(24,2),            -- 5 交易日內可變現金額（WLA 口徑）
    liquidation_bucket     VARCHAR(8)  NOT NULL,     -- 1D / 2-7D / 8-30D / 31-90D / GT90D
    liquidation_days       INTEGER,                  -- 完全變現所需天數（決定時間桶）
    realizable_pct_nav     NUMERIC(10,6),            -- 1 日可變現金額佔 NAV 比例（%，DLA 貢獻）
    realizable_5d_pct_nav  NUMERIC(10,6),            -- 5 日可變現金額佔 NAV 比例（%，WLA 貢獻）
    bucket_pct_nav         NUMERIC(10,6),            -- 持倉全額市值佔 NAV 比例（%，分層分佈，求和=100%）
    bid_ask_cost           NUMERIC(24,2),            -- 買賣價差成本（元，按 1 日可變現額計）
    net_realizable         NUMERIC(24,2),            -- 扣減成本後 1 日淨變現金額
    net_asset              NUMERIC(24,2),            -- 組合 NAV（元，方便查詢）
    data_source            VARCHAR(16)  NOT NULL DEFAULT 'CALC',
    loaded_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, security_code, scenario)
);
COMMENT ON TABLE  fsi.sfc_liquidity_stress IS 'SFC 貨幣基金流動性壓力測試：按持倉×場景（Normal/Stressed）落庫，含 1 日/5 日可變現額與完全變現桶';
COMMENT ON COLUMN fsi.sfc_liquidity_stress.scenario IS 'NORMAL=正常場景；STRESSED=壓力場景（50% ADTV haircut + 零早破存款）';
COMMENT ON COLUMN fsi.sfc_liquidity_stress.liquidation_bucket IS '完全變現所需天數對應的 5 檔時間桶（SFC 文檔）：1D/2-7D/8-30D/31-90D/GT90D；按 bucket_pct_nav 分層求和=100%';
COMMENT ON COLUMN fsi.sfc_liquidity_stress.tradable_size IS '二級市場日可變現規模 = ADTV × 10% 參與率 × (1-50% haircut)（SFC §1(iv)/§2(a)）';
COMMENT ON COLUMN fsi.sfc_liquidity_stress.realizable_amount IS '1 交易日內可變現金額（DLA 口徑）：MIN(持倉市值, tradable_size) + 到期/現金/隔夜存款';
COMMENT ON COLUMN fsi.sfc_liquidity_stress.realizable_5d_amount IS '5 交易日內可變現金額（WLA 口徑）：1 日可變現額 + 2-5 日可繼續變現部分';
COMMENT ON COLUMN fsi.sfc_liquidity_stress.bucket_pct_nav IS '該持倉全額市值佔 NAV %，歸入完全變現桶；同場景求和=100%（SFC 文檔 §1(i)）';

CREATE INDEX IF NOT EXISTS idx_sfc_ls_port_date ON fsi.sfc_liquidity_stress(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_sfc_ls_bucket   ON fsi.sfc_liquidity_stress(evaluate_date, port_id, scenario, liquidation_bucket);

-- ────────────────────────────────────────────────────────────
-- 4. SFC 合規流動性指標匯總表（DLA/WLA 雙場景 + 5 檔分層）
--   SFC UT Code §8.2(n)：DLA ≥ 7.5% / WLA ≥ 15%（Normal+Stressed 均須滿足）
--   分層口徑：全組合 100% 按完全變現天數歸桶（SFC 文檔 §1(i)）
--   DLA/WLA 口徑：1 日/5 日內實際可變現金額（受 ADTV 上限約束）
-- ============================================================
CREATE TABLE IF NOT EXISTS fsi.sfc_liquidity_compliance (
    evaluate_date     DATE         NOT NULL,
    port_id           VARCHAR(16)  NOT NULL,
    scenario          VARCHAR(16)  NOT NULL,         -- NORMAL / STRESSED
    dla_amount        NUMERIC(24,2),                 -- 日流動資產（1 交易日內可變現，ADTV 約束）
    wla_amount        NUMERIC(24,2),                 -- 週流動資產（5 交易日內可變現，ADTV 約束）
    nav               NUMERIC(24,2),
    dla_pct           NUMERIC(10,6),                 -- DLA / NAV × 100
    wla_pct           NUMERIC(10,6),                 -- WLA / NAV × 100
    dla_status        VARCHAR(24),                   -- 合規 / 未達標(≥7.5%)
    wla_status        VARCHAR(24),                   -- 合規 / 未達標(≥15%)
    bucket_1d_pct     NUMERIC(10,6),                 -- 1D 桶佔 NAV %（全額歸桶，求和=100%）
    bucket_2_7d_pct   NUMERIC(10,6),                 -- 2-7D 桶佔 NAV %
    bucket_8_30d_pct  NUMERIC(10,6),                 -- 8-30D 桶佔 NAV %
    bucket_31_90d_pct NUMERIC(10,6),                 -- 31-90D 桶佔 NAV %
    bucket_gt90d_pct  NUMERIC(10,6),                 -- >90D 桶佔 NAV %
    total_pct         NUMERIC(10,6),                 -- 五桶合計（資產端分層，應=資產/NAV=100%）
    coverage_pct      NUMERIC(10,6),                 -- 明細持倉市值 / NAV（數據完備時應=100%）
    loaded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, scenario)
);
COMMENT ON TABLE fsi.sfc_liquidity_compliance IS 'SFC 流動性合規匯總：DLA/WLA（ADTV 約束）+ 5 檔分層佔 NAV%（雙場景，資產端分層求和=coverage_pct）';
COMMENT ON COLUMN fsi.sfc_liquidity_compliance.dla_pct IS 'DLA / NAV：SFC UT Code §8.2(n) 要求 ≥ 7.5%（雙場景），含現金/隔夜/到期/ADTV 上限內二級變現';
COMMENT ON COLUMN fsi.sfc_liquidity_compliance.wla_pct IS 'WLA / NAV：SFC UT Code §8.2(n) 要求 ≥ 15%（雙場景），1 日額 + 2-5 日可繼續變現';
COMMENT ON COLUMN fsi.sfc_liquidity_compliance.total_pct IS '五檔桶市值合計 / NAV；資產端分層應=coverage_pct（數據完備時=100%）';
COMMENT ON COLUMN fsi.sfc_liquidity_compliance.coverage_pct IS '明細持倉市值 / NAV：當明細表(bond/cd/deposit/repo/cash)完整覆蓋資產端時=100%';
