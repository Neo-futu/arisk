-- ============================================================
-- 017_indicator_explorer.sql  指標探索引擎底座（DataJungle 式）
-- 涵蓋：通用 long-format 宏觀/市場指標定義 + 時序觀測（可編輯維護）
-- 依賴：001_schema_init.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 指標定義（目錄）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_indicator_def (
    indicator_id      VARCHAR(48)  PRIMARY KEY,
    indicator_name    VARCHAR(160) NOT NULL,
    indicator_name_en VARCHAR(160),
    category          VARCHAR(48)  NOT NULL,       -- 通脹 / 增長 / 利率 / 就業 / 市場
    country           CHAR(2)      NOT NULL,       -- HK / CN / US / EU ...
    unit              VARCHAR(24)  NOT NULL,       -- %, %YoY, index, bp
    frequency         VARCHAR(12)  NOT NULL DEFAULT 'MONTHLY',  -- DAILY/MONTHLY/QUARTERLY/ANNUAL
    data_source       VARCHAR(32)  NOT NULL DEFAULT 'MANUAL',
    description       TEXT,
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.mktdata_indicator_def IS
    '指標探索引擎：通用宏觀/市場指標定義，供 DataJungle 式選擇（指標/國家/週期/數據源）與 API 導出。';

-- ────────────────────────────────────────────────────────────
-- 2. 指標時序觀測（long-format，可編輯維護）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_indicator_series (
    indicator_id  VARCHAR(48)   NOT NULL
        REFERENCES fsi.mktdata_indicator_def(indicator_id) ON DELETE CASCADE,
    obs_date      DATE          NOT NULL,
    value         NUMERIC(24,8) NOT NULL,
    data_source   VARCHAR(32)   NOT NULL DEFAULT 'MANUAL',
    loaded_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (indicator_id, obs_date)
);
COMMENT ON TABLE fsi.mktdata_indicator_series IS
    '指標時序觀測：界面可視化增刪改並直連底層表，支持手工維護與外部源接入。';

CREATE INDEX IF NOT EXISTS idx_mkt_indicator_series
    ON fsi.mktdata_indicator_series(indicator_id, obs_date);

-- ────────────────────────────────────────────────────────────
-- 3. 指標定義種子（HK / CN / US 常用宏觀 + 市場指標）
-- ────────────────────────────────────────────────────────────
INSERT INTO fsi.mktdata_indicator_def
    (indicator_id, indicator_name, indicator_name_en, category, country, unit, frequency, data_source, description)
VALUES
    ('HK_CPI_YOY', '香港 CPI 同比',   'Hong Kong CPI YoY',        '通脹', 'HK', '%YoY', 'MONTHLY', 'SEED', '香港綜合消費物價指數同比'),
    ('HK_GDP_YOY', '香港 GDP 同比',   'Hong Kong GDP YoY',        '增長', 'HK', '%YoY', 'MONTHLY', 'SEED', '香港實質 GDP 同比（示例插值）'),
    ('HK_UNEMP',   '香港失業率',       'Hong Kong Unemployment',   '就業', 'HK', '%',    'MONTHLY', 'SEED', '香港經季節調整失業率'),
    ('HK_HIBOR3M', '香港 3 個月 HIBOR','Hong Kong 3M HIBOR',       '利率', 'HK', '%',    'MONTHLY', 'SEED', '3 個月香港銀行同業拆息月均'),
    ('HSI_INDEX',  '恒生指數',         'Hang Seng Index',          '市場', 'HK', 'index','MONTHLY', 'SEED', '恒生指數月末點位'),
    ('CN_CPI_YOY', '中國 CPI 同比',   'China CPI YoY',            '通脹', 'CN', '%YoY', 'MONTHLY', 'SEED', '中國居民消費價格指數同比'),
    ('CN_GDP_YOY', '中國 GDP 同比',   'China GDP YoY',            '增長', 'CN', '%YoY', 'MONTHLY', 'SEED', '中國實質 GDP 同比（示例插值）'),
    ('CN_LPR1Y',   '中國 1 年期 LPR', 'China 1Y LPR',             '利率', 'CN', '%',    'MONTHLY', 'SEED', '中國 1 年期貸款市場報價利率'),
    ('US_CPI_YOY', '美國 CPI 同比',   'US CPI YoY',               '通脹', 'US', '%YoY', 'MONTHLY', 'SEED', '美國城市消費者物價指數同比'),
    ('US_GDP_YOY', '美國 GDP 同比',   'US GDP YoY',               '增長', 'US', '%YoY', 'MONTHLY', 'SEED', '美國實質 GDP 同比（示例插值）'),
    ('US_FEDRATE', '美國聯邦基金利率', 'US Fed Funds Rate',        '利率', 'US', '%',    'MONTHLY', 'SEED', '美國聯邦基金目標利率上限'),
    ('US_UNEMP',   '美國失業率',       'US Unemployment',          '就業', 'US', '%',    'MONTHLY', 'SEED', '美國 U-3 失業率')
ON CONFLICT (indicator_id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 4. 時序觀測種子（36 個月度點，確定性生成，非隨機）
--    value = round(base + amp*sin(n/3) + trend*n, 4)
-- ────────────────────────────────────────────────────────────
WITH params(indicator_id, base, amp, trend) AS (
    VALUES
        ('HK_CPI_YOY',      2.0,      0.6,    0.010),
        ('HK_GDP_YOY',      3.0,      1.5,   -0.020),
        ('HK_UNEMP',        3.2,      0.5,   -0.010),
        ('HK_HIBOR3M',      4.6,      0.4,   -0.015),
        ('HSI_INDEX',   18500.0,   1800.0,   45.000),
        ('CN_CPI_YOY',      1.0,      0.8,   -0.005),
        ('CN_GDP_YOY',      5.0,      0.9,   -0.010),
        ('CN_LPR1Y',        3.45,     0.15,  -0.008),
        ('US_CPI_YOY',      3.4,      1.1,   -0.030),
        ('US_GDP_YOY',      2.4,      0.7,   -0.005),
        ('US_FEDRATE',      5.375,    0.25,  -0.020),
        ('US_UNEMP',        3.8,      0.4,    0.012)
),
months AS (
    SELECT gs::date AS obs_date,
           ROW_NUMBER() OVER (ORDER BY gs) AS n
    FROM generate_series(DATE '2023-09-01', DATE '2026-08-01', INTERVAL '1 month') AS gs
)
INSERT INTO fsi.mktdata_indicator_series (indicator_id, obs_date, value, data_source)
SELECT p.indicator_id,
       m.obs_date,
       ROUND((p.base + p.amp * SIN(m.n / 3.0) + p.trend * m.n)::numeric, 4),
       'SEED'
FROM params p
CROSS JOIN months m
ON CONFLICT (indicator_id, obs_date) DO NOTHING;
