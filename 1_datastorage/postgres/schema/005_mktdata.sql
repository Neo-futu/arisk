-- ============================================================
-- 004_mktdata.sql  市場數據層  (prefix: mktdata_)
-- FSI Financial Services Intelligence Platform
-- 涵蓋：債券靜態 · 股票靜態 · 指數 · 期貨合約
--        行情報價 · 匯率 · 收益率曲線 · 債券風險指標 · 基金NAV
-- 依賴：001_schema_init.sql · 002_para.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 債券靜態數據
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_bond_static (
    internal_id          VARCHAR(32)        PRIMARY KEY,
    isin                 VARCHAR(12),
    security_code_ib     VARCHAR(16),       -- 銀行間代碼
    security_code_hkex   VARCHAR(16),
    security_code_wind   VARCHAR(32),
    security_code_bbg    VARCHAR(32),       -- Bloomberg
    security_name        VARCHAR(200)       NOT NULL,
    security_name_en     VARCHAR(200),
    currency             CHAR(3)            NOT NULL,
    asset_subtype        fsi.asset_class    NOT NULL,
    issuer_id            VARCHAR(16),
    issuer_name          VARCHAR(200),
    issuer_group         VARCHAR(200),
    country              CHAR(2),
    sector               VARCHAR(64),
    issue_date           DATE,
    value_date           DATE,
    maturity_date        DATE,
    issue_amount         NUMERIC(24,2),
    outstanding_amount   NUMERIC(24,2),
    issue_price          NUMERIC(24,8),
    face_value           NUMERIC(24,8)      DEFAULT 100,
    coupon_type          VARCHAR(16),       -- FIXED/FLOAT/ZERO/STEP/PIK
    coupon_rate          NUMERIC(12,8),
    coupon_frequency     INTEGER,
    day_count_convention VARCHAR(16)        DEFAULT 'ACT/365',
    issuer_rating        VARCHAR(8),
    debt_rating          VARCHAR(8),
    rating_agency        fsi.rating_agency  DEFAULT 'NR',
    rating_date          DATE,
    is_callable          BOOLEAN            DEFAULT FALSE,
    is_puttable          BOOLEAN            DEFAULT FALSE,
    is_convertible       BOOLEAN            DEFAULT FALSE,
    is_green_bond        BOOLEAN            DEFAULT FALSE,
    is_perpetual         BOOLEAN            DEFAULT FALSE,
    data_source          VARCHAR(16)        NOT NULL DEFAULT 'WIND',
    last_updated         DATE,
    created_at           TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ        NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.mktdata_bond_static IS '債券靜態數據：發行信息、票息結構、評級';
COMMENT ON COLUMN fsi.mktdata_bond_static.day_count_convention IS '計息基準：ACT/365(香港常用)/ACT/360/30/360，影響應計利息';
COMMENT ON COLUMN fsi.mktdata_bond_static.is_green_bond IS 'ESG綠色債券標識，用於ESG報告篩選';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mkt_bond_isin ON fsi.mktdata_bond_static(isin) WHERE isin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mkt_bond_issuer   ON fsi.mktdata_bond_static(issuer_id);
CREATE INDEX IF NOT EXISTS idx_mkt_bond_maturity ON fsi.mktdata_bond_static(maturity_date);
CREATE INDEX IF NOT EXISTS idx_mkt_bond_subtype  ON fsi.mktdata_bond_static(asset_subtype);

-- ────────────────────────────────────────────────────────────
-- 2. 股票靜態數據
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_stock_static (
    internal_id        VARCHAR(32)  PRIMARY KEY,
    isin               VARCHAR(12),
    security_code      VARCHAR(32)  NOT NULL,
    security_code_wind VARCHAR(32),
    security_code_bbg  VARCHAR(32),
    security_name      VARCHAR(200) NOT NULL,
    security_name_en   VARCHAR(200),
    market_id          VARCHAR(16)  NOT NULL,   -- HKEX/NYSE/LSE/SSE/SZSE
    currency           CHAR(3)      NOT NULL,
    country            CHAR(2),
    sector_level1      VARCHAR(64),
    sector_level2      VARCHAR(64),
    industry_standard  VARCHAR(16)  DEFAULT 'GICS', -- GICS/CSRC/WIND
    shares_outstanding NUMERIC(24,4),
    free_float_shares  NUMERIC(24,4),
    listing_date       DATE,
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    data_source        VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.mktdata_stock_static IS '股票靜態數據：支持全球主要市場（港股/美股/A股/歐股）';
COMMENT ON COLUMN fsi.mktdata_stock_static.industry_standard IS 'GICS=全球行業分類 / CSRC=中國證監會 / WIND';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mkt_stock_isin ON fsi.mktdata_stock_static(isin) WHERE isin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mkt_stock_market ON fsi.mktdata_stock_static(market_id);
CREATE INDEX IF NOT EXISTS idx_mkt_stock_sector ON fsi.mktdata_stock_static(sector_level1);

-- ────────────────────────────────────────────────────────────
-- 3. 指數主數據
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_index_static (
    index_code         VARCHAR(32)  PRIMARY KEY,
    index_name         VARCHAR(200) NOT NULL,
    index_name_en      VARCHAR(200),
    currency           CHAR(3)      NOT NULL,
    index_type         VARCHAR(16),             -- PRICE/TOTAL_RETURN/NET_RETURN
    asset_class        VARCHAR(16),             -- EQUITY/BOND/COMMODITY/MIXED
    country            CHAR(2),
    base_date          DATE,
    base_value         NUMERIC(16,4),
    provider           VARCHAR(64),             -- MSCI/FTSE/Hang Seng/CSI
    source_ticker_wind VARCHAR(32),
    source_ticker_bbg  VARCHAR(32),
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.mktdata_index_static IS '指數主數據：基準比較、業績歸因用市場指數';

-- ────────────────────────────────────────────────────────────
-- 4. 期貨合約靜態
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_futures_contract (
    contract_code      VARCHAR(32)  PRIMARY KEY,
    contract_name      VARCHAR(120),
    contract_category  VARCHAR(32)  NOT NULL,   -- 股指/利率/外匯/商品
    underlying_code    VARCHAR(32),
    market_id          VARCHAR(16),
    currency           CHAR(3)      NOT NULL,
    contract_multiplier NUMERIC(12,4) NOT NULL,
    margin_rate        NUMERIC(6,4),
    first_trading_date DATE,
    last_trading_date  DATE,
    delivery_date      DATE,
    data_source        VARCHAR(16)  DEFAULT 'WIND',
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.mktdata_futures_contract IS '期貨合約靜態：含合約乘數（計算名義金額必需）';

-- ────────────────────────────────────────────────────────────
-- 5. 債券每日風險指標
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_bond_risk (
    price_date        DATE         NOT NULL,
    internal_id       VARCHAR(32)  NOT NULL,
    clean_price       NUMERIC(24,8),
    dirty_price       NUMERIC(24,8),
    ytm               NUMERIC(14,10),
    duration          NUMERIC(12,8),
    convexity         NUMERIC(12,8),
    dv01              NUMERIC(16,8),              -- DVBP per face 100
    accrued_interest  NUMERIC(24,8),
    surviving_amount  NUMERIC(24,2),
    issuer_rating     VARCHAR(8),
    debt_rating       VARCHAR(8),
    data_source       VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (price_date, internal_id)
);
COMMENT ON TABLE  fsi.mktdata_bond_risk IS '債券每日風險指標：久期/凸性/DV01，持倉風控計算數據來源';
COMMENT ON COLUMN fsi.mktdata_bond_risk.dv01 IS '每基點美元值（面值100計算）';

CREATE INDEX IF NOT EXISTS idx_mkt_bond_risk_date ON fsi.mktdata_bond_risk(price_date DESC, internal_id);

-- ────────────────────────────────────────────────────────────
-- 6. 通用行情報價（股票/ETF/公募基金NAV）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_quotes (
    price_date         DATE         NOT NULL,
    security_code      VARCHAR(32)  NOT NULL,
    market_id          VARCHAR(16)  NOT NULL,
    price_type         VARCHAR(16)  NOT NULL DEFAULT 'CLOSE',  -- CLOSE/BID/ASK/MID/SETTLE
    open_price         NUMERIC(24,8),
    high_price         NUMERIC(24,8),
    low_price          NUMERIC(24,8),
    close_price        NUMERIC(24,8) NOT NULL,
    prev_close         NUMERIC(24,8),
    price_change_pct   NUMERIC(12,8),
    volume             BIGINT,
    turnover           NUMERIC(24,2),
    pe_ratio           NUMERIC(14,4),
    pb_ratio           NUMERIC(14,4),
    market_cap         NUMERIC(28,2),
    data_source        VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (price_date, security_code, price_type)
);
COMMENT ON TABLE  fsi.mktdata_quotes IS '通用行情報價：股票/ETF/基金淨值等每日收盤數據';
COMMENT ON COLUMN fsi.mktdata_quotes.price_change_pct IS '漲跌幅（%）= (close-prev_close)/prev_close*100';

CREATE INDEX IF NOT EXISTS idx_mkt_quotes_date     ON fsi.mktdata_quotes(price_date DESC);
CREATE INDEX IF NOT EXISTS idx_mkt_quotes_security ON fsi.mktdata_quotes(security_code, price_date DESC);

-- ────────────────────────────────────────────────────────────
-- 7. 指數每日行情
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_index_quotes (
    price_date       DATE         NOT NULL,
    index_code       VARCHAR(32)  NOT NULL,
    open_price       NUMERIC(16,4),
    high_price       NUMERIC(16,4),
    low_price        NUMERIC(16,4),
    close_price      NUMERIC(16,4) NOT NULL,
    prev_close       NUMERIC(16,4),
    price_change_pct NUMERIC(12,8),
    volume           BIGINT,
    turnover         NUMERIC(24,2),
    pe_ratio         NUMERIC(14,2),
    pb_ratio         NUMERIC(14,4),
    dividend_yield   NUMERIC(10,6),
    data_source      VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (price_date, index_code)
);
COMMENT ON TABLE fsi.mktdata_index_quotes IS '指數每日行情：業績比較、歸因計算';

CREATE INDEX IF NOT EXISTS idx_mkt_idx_q_date ON fsi.mktdata_index_quotes(price_date DESC);

-- ────────────────────────────────────────────────────────────
-- 8. 期貨行情
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_futures_quotes (
    price_date          DATE         NOT NULL,
    contract_code       VARCHAR(32)  NOT NULL,
    open_price          NUMERIC(16,4),
    high_price          NUMERIC(16,4),
    low_price           NUMERIC(16,4),
    close_price         NUMERIC(16,4),
    settlement_price    NUMERIC(16,4) NOT NULL,
    prev_settlement     NUMERIC(16,4),
    price_change_pct    NUMERIC(12,8),
    volume              BIGINT,
    open_interest       BIGINT,                  -- 持倉量
    turnover            NUMERIC(24,2),
    data_source         VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (price_date, contract_code)
);
COMMENT ON TABLE  fsi.mktdata_futures_quotes IS '期貨行情：結算價用於每日盯市計算';
COMMENT ON COLUMN fsi.mktdata_futures_quotes.open_interest IS '持倉量（Open Interest）：流動性指標';

CREATE INDEX IF NOT EXISTS idx_mkt_fut_q_date ON fsi.mktdata_futures_quotes(price_date DESC);

-- ────────────────────────────────────────────────────────────
-- 9. 匯率（即期 + 遠期）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_fx_rate (
    rate_date    DATE         NOT NULL,
    base_ccy     CHAR(3)      NOT NULL,
    quote_ccy    CHAR(3)      NOT NULL,
    rate_type    VARCHAR(16)  NOT NULL DEFAULT 'SPOT',  -- SPOT/FWD_1W/FWD_1M/FWD_3M
    mid_rate     NUMERIC(18,8) NOT NULL,
    bid_rate     NUMERIC(18,8),
    ask_rate     NUMERIC(18,8),
    data_source  VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rate_date, base_ccy, quote_ccy, rate_type)
);
COMMENT ON TABLE  fsi.mktdata_fx_rate IS '匯率數據：即期和遠期，多幣種組合折算和外匯風險計算';
COMMENT ON COLUMN fsi.mktdata_fx_rate.rate_type IS 'SPOT=即期 / FWD_1W/1M/3M=遠期，用於外匯對沖分析';

CREATE INDEX IF NOT EXISTS idx_mkt_fx_date ON fsi.mktdata_fx_rate(rate_date DESC, base_ccy, quote_ccy);
CREATE INDEX IF NOT EXISTS idx_mkt_fx_pair ON fsi.mktdata_fx_rate(base_ccy, quote_ccy, rate_date DESC);

-- ────────────────────────────────────────────────────────────
-- 10. 收益率曲線定義
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_yield_curve_def (
    curve_id     VARCHAR(16)  PRIMARY KEY,
    curve_name   VARCHAR(120) NOT NULL,
    currency     CHAR(3)      NOT NULL,
    curve_type   VARCHAR(16)  NOT NULL,   -- GOVERNMENT/INTERBANK/SWAP/CREDIT
    country      CHAR(2),
    data_source  VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    source_id    VARCHAR(32),
    description  TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE fsi.mktdata_yield_curve_def IS '收益率曲線定義：HIBOR/SHIBOR/美聯儲利率曲線等';

INSERT INTO fsi.mktdata_yield_curve_def (curve_id, curve_name, currency, curve_type, country) VALUES
    ('HIBOR',    'Hong Kong Interbank Offered Rate', 'HKD', 'INTERBANK', 'HK'),
    ('HKGOV',    '香港政府債券收益率曲線',             'HKD', 'GOVERNMENT','HK'),
    ('SHIBOR',   'Shanghai Interbank Offered Rate',   'CNY', 'INTERBANK', 'CN'),
    ('SOFR',     'Secured Overnight Financing Rate',  'USD', 'INTERBANK', 'US'),
    ('US_TREAS', 'US Treasury Yield Curve',           'USD', 'GOVERNMENT','US'),
    ('EURIBOR',  'Euro Interbank Offered Rate',       'EUR', 'INTERBANK', 'EU')
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 11. 收益率曲線每日報價
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_yield_curve_quotes (
    rate_date   DATE         NOT NULL,
    curve_id    VARCHAR(16)  NOT NULL,
    tenor       VARCHAR(8)   NOT NULL,   -- ON/1W/2W/1M/2M/3M/6M/1Y/2Y/5Y/10Y/30Y
    tenor_days  INTEGER,                 -- 標準化天數，便於插值
    rate        NUMERIC(12,8) NOT NULL,  -- 年化利率（小數，非%）
    data_source VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rate_date, curve_id, tenor)
);
COMMENT ON TABLE  fsi.mktdata_yield_curve_quotes IS '利率曲線每日報價：HIBOR/SHIBOR/美債，貼現和久期計算數據源';
COMMENT ON COLUMN fsi.mktdata_yield_curve_quotes.tenor_days IS '期限標準天數（ON=1,1W=7,1M=30...），收益率曲線插值用';

CREATE INDEX IF NOT EXISTS idx_mkt_ycurve_date ON fsi.mktdata_yield_curve_quotes(rate_date DESC, curve_id);

-- ────────────────────────────────────────────────────────────
-- 12. 外部基金NAV歷史
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_fund_nav (
    nav_date      DATE         NOT NULL,
    fund_code     VARCHAR(32)  NOT NULL,
    unit_nav      NUMERIC(16,8) NOT NULL,
    acc_unit_nav  NUMERIC(16,8),
    day_return    DOUBLE PRECISION,
    total_return  DOUBLE PRECISION,
    data_source   VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (nav_date, fund_code)
);
COMMENT ON TABLE fsi.mktdata_fund_nav IS '外部公募基金NAV歷史：基金持倉估值、業績比較';

CREATE INDEX IF NOT EXISTS idx_mkt_fund_nav_date ON fsi.mktdata_fund_nav(fund_code, nav_date DESC);
