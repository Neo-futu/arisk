-- ============================================================
-- 002_raw.sql  原始數據層  (prefix: raw_)
-- FSI Financial Services Intelligence Platform
-- Layer 1 of 3: Source Staging
--
-- 職責：接收來自外部系統的原始數據，零轉換入庫
-- 來源：Wind/Bloomberg MCP · 托管行報表 · 交易系統 · 基金管理人
--
-- 設計原則：
--   · 所有業務列允許 NULL（源數據可能殘缺）
--   · 無 FK 約束，無 Trigger，不引用其他表
--   · raw_data JSONB 保留完整原始 payload
--   · load_status 驅動 ETL 流水線：PENDING→PROCESSING→DONE/ERROR
--   · batch_id 關聯同批次所有記錄，便於回滾
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 原始持倉數據（托管行/估值系統匯入）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.raw_position (
    load_id         BIGSERIAL    PRIMARY KEY,
    batch_id        VARCHAR(64)  NOT NULL,           -- 批次ID，關聯同批所有記錄
    source_system   VARCHAR(32)  NOT NULL,           -- CUSTODIAN/VALUATION/MANUAL
    load_ts         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    load_status     VARCHAR(16)  NOT NULL DEFAULT 'PENDING', -- PENDING/PROCESSING/DONE/ERROR
    error_msg       TEXT,

    -- 業務字段（源數據原樣，均可為NULL）
    evaluate_date   DATE,
    port_no         VARCHAR(32),
    port_name       VARCHAR(200),
    security_code   VARCHAR(64),
    security_name   VARCHAR(200),
    asset_type_l1   VARCHAR(32),                    -- 一級資產類別（源系統代碼）
    asset_type_l2   VARCHAR(32),                    -- 二級資產類別
    issuer_code     VARCHAR(32),
    issuer_name     VARCHAR(200),
    currency        VARCHAR(8),
    quantity        NUMERIC(24,6),
    cost            NUMERIC(24,4),
    price           NUMERIC(24,8),
    market_value    NUMERIC(24,4),
    weight_pct      NUMERIC(12,6),
    maturity_date   DATE,
    coupon_rate     NUMERIC(12,8),
    ytm             NUMERIC(14,10),
    duration        NUMERIC(12,8),
    credit_rating   VARCHAR(16),

    raw_data        JSONB        NOT NULL DEFAULT '{}'  -- 完整原始 payload
);
COMMENT ON TABLE  fsi.raw_position IS 'Layer1 原始持倉：托管行/估值系統報表直接入庫，ETL前的暫存';
COMMENT ON COLUMN fsi.raw_position.load_status IS 'PENDING=待處理 / PROCESSING=ETL中 / DONE=已轉換 / ERROR=失敗';
COMMENT ON COLUMN fsi.raw_position.raw_data IS '完整原始 payload（JSON），保留源格式便於追溯';

CREATE INDEX IF NOT EXISTS idx_raw_pos_batch  ON fsi.raw_position(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_pos_status ON fsi.raw_position(load_status) WHERE load_status IN ('PENDING','ERROR');
CREATE INDEX IF NOT EXISTS idx_raw_pos_date   ON fsi.raw_position(evaluate_date, port_no);

-- ────────────────────────────────────────────────────────────
-- 2. 原始交易流水
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.raw_transaction (
    load_id         BIGSERIAL    PRIMARY KEY,
    batch_id        VARCHAR(64)  NOT NULL,
    source_system   VARCHAR(32)  NOT NULL,           -- TRADING_SYS/BROKER/MANUAL
    source_txn_id   VARCHAR(64),                    -- 源系統流水號（去重用）
    load_ts         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    load_status     VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    error_msg       TEXT,

    trade_date      DATE,
    settle_date     DATE,
    port_no         VARCHAR(32),
    security_code   VARCHAR(64),
    security_name   VARCHAR(200),
    asset_type      VARCHAR(32),
    trade_direction VARCHAR(8),                     -- B=買 S=賣
    txn_type        VARCHAR(32),
    currency        VARCHAR(8),
    quantity        NUMERIC(24,6),
    price           NUMERIC(24,8),
    amount          NUMERIC(24,4),
    fee             NUMERIC(16,4),
    net_amount      NUMERIC(24,4),
    counterparty    VARCHAR(200),
    broker          VARCHAR(128),

    raw_data        JSONB        NOT NULL DEFAULT '{}'
);
COMMENT ON TABLE  fsi.raw_transaction IS 'Layer1 原始交易：交易系統/券商流水直接入庫';
COMMENT ON COLUMN fsi.raw_transaction.source_txn_id IS '源系統唯一流水號，ETL去重依據';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_raw_txn_src    ON fsi.raw_transaction(source_system, source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_raw_txn_batch    ON fsi.raw_transaction(batch_id);
CREATE INDEX        IF NOT EXISTS idx_raw_txn_status   ON fsi.raw_transaction(load_status) WHERE load_status IN ('PENDING','ERROR');
CREATE INDEX        IF NOT EXISTS idx_raw_txn_date     ON fsi.raw_transaction(trade_date, port_no);

-- ────────────────────────────────────────────────────────────
-- 3. 原始行情數據（Wind/Bloomberg 推送）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.raw_price (
    load_id         BIGSERIAL    PRIMARY KEY,
    batch_id        VARCHAR(64)  NOT NULL,
    source_system   VARCHAR(32)  NOT NULL,           -- WIND/BLOOMBERG/HKEX
    load_ts         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    load_status     VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    error_msg       TEXT,

    price_date      DATE,
    security_code   VARCHAR(64),
    market_id       VARCHAR(16),
    price_type      VARCHAR(16),                    -- CLOSE/SETTLE/BID/ASK
    open_price      NUMERIC(24,8),
    high_price      NUMERIC(24,8),
    low_price       NUMERIC(24,8),
    close_price     NUMERIC(24,8),
    volume          BIGINT,
    turnover        NUMERIC(24,4),

    raw_data        JSONB        NOT NULL DEFAULT '{}'
);
COMMENT ON TABLE fsi.raw_price IS 'Layer1 原始行情：Wind/Bloomberg每日推送，含股票/債券/指數/期貨';

CREATE INDEX IF NOT EXISTS idx_raw_price_batch  ON fsi.raw_price(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_price_status ON fsi.raw_price(load_status) WHERE load_status IN ('PENDING','ERROR');
CREATE INDEX IF NOT EXISTS idx_raw_price_date   ON fsi.raw_price(price_date, security_code);

-- ────────────────────────────────────────────────────────────
-- 4. 原始匯率
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.raw_fx_rate (
    load_id         BIGSERIAL    PRIMARY KEY,
    batch_id        VARCHAR(64)  NOT NULL,
    source_system   VARCHAR(32)  NOT NULL,
    load_ts         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    load_status     VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    error_msg       TEXT,

    rate_date       DATE,
    base_ccy        VARCHAR(8),
    quote_ccy       VARCHAR(8),
    rate_type       VARCHAR(16),                    -- SPOT/FWD
    mid_rate        NUMERIC(18,8),
    bid_rate        NUMERIC(18,8),
    ask_rate        NUMERIC(18,8),

    raw_data        JSONB        NOT NULL DEFAULT '{}'
);
COMMENT ON TABLE fsi.raw_fx_rate IS 'Layer1 原始匯率：Wind/彭博每日推送的即期和遠期匯率';

CREATE INDEX IF NOT EXISTS idx_raw_fx_batch  ON fsi.raw_fx_rate(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_fx_status ON fsi.raw_fx_rate(load_status) WHERE load_status IN ('PENDING','ERROR');
CREATE INDEX IF NOT EXISTS idx_raw_fx_date   ON fsi.raw_fx_rate(rate_date, base_ccy, quote_ccy);

-- ────────────────────────────────────────────────────────────
-- 5. 原始利率曲線
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.raw_yield_curve (
    load_id         BIGSERIAL    PRIMARY KEY,
    batch_id        VARCHAR(64)  NOT NULL,
    source_system   VARCHAR(32)  NOT NULL,
    load_ts         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    load_status     VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    error_msg       TEXT,

    rate_date       DATE,
    curve_id        VARCHAR(32),                    -- HIBOR/SHIBOR/SOFR 等
    tenor           VARCHAR(8),
    rate            NUMERIC(12,8),

    raw_data        JSONB        NOT NULL DEFAULT '{}'
);
COMMENT ON TABLE fsi.raw_yield_curve IS 'Layer1 原始利率曲線：HIBOR/SHIBOR/SOFR等每日數據';

CREATE INDEX IF NOT EXISTS idx_raw_yc_batch  ON fsi.raw_yield_curve(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_yc_status ON fsi.raw_yield_curve(load_status) WHERE load_status IN ('PENDING','ERROR');
CREATE INDEX IF NOT EXISTS idx_raw_yc_date   ON fsi.raw_yield_curve(rate_date, curve_id);

-- ────────────────────────────────────────────────────────────
-- 6. 原始NAV（基金管理人/托管行確認）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.raw_nav (
    load_id         BIGSERIAL    PRIMARY KEY,
    batch_id        VARCHAR(64)  NOT NULL,
    source_system   VARCHAR(32)  NOT NULL,           -- FUND_ADMIN/CUSTODIAN
    load_ts         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    load_status     VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    error_msg       TEXT,

    nav_date        DATE,
    port_no         VARCHAR(32),
    fund_code       VARCHAR(32),
    class_code      VARCHAR(32),
    currency        VARCHAR(8),
    unit_nav        NUMERIC(16,8),
    acc_unit_nav    NUMERIC(16,8),
    total_nav       NUMERIC(24,4),
    shares          NUMERIC(24,6),

    raw_data        JSONB        NOT NULL DEFAULT '{}'
);
COMMENT ON TABLE fsi.raw_nav IS 'Layer1 原始NAV：基金管理人/托管行每日確認，估值鏈的起點';

CREATE INDEX IF NOT EXISTS idx_raw_nav_batch  ON fsi.raw_nav(batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_nav_status ON fsi.raw_nav(load_status) WHERE load_status IN ('PENDING','ERROR');
CREATE INDEX IF NOT EXISTS idx_raw_nav_date   ON fsi.raw_nav(nav_date, port_no);

-- ────────────────────────────────────────────────────────────
-- 7. ETL 批次記錄（追蹤每次數據載入）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.raw_etl_batch (
    batch_id        VARCHAR(64)  PRIMARY KEY,
    source_system   VARCHAR(32)  NOT NULL,
    data_type       VARCHAR(32)  NOT NULL,           -- POSITION/TRANSACTION/PRICE/FX/NAV
    business_date   DATE,
    file_name       VARCHAR(512),
    record_total    INTEGER,
    record_ok       INTEGER,
    record_error    INTEGER,
    batch_status    VARCHAR(16)  NOT NULL DEFAULT 'RUNNING', -- RUNNING/DONE/PARTIAL/FAILED
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    triggered_by    VARCHAR(128),
    error_summary   TEXT
);
COMMENT ON TABLE  fsi.raw_etl_batch IS 'ETL批次記錄：追蹤每次數據載入的狀態和結果統計';
COMMENT ON COLUMN fsi.raw_etl_batch.batch_status IS 'RUNNING=進行中 / DONE=全量成功 / PARTIAL=部分失敗 / FAILED=全部失敗';

CREATE INDEX IF NOT EXISTS idx_raw_batch_date   ON fsi.raw_etl_batch(business_date DESC);
CREATE INDEX IF NOT EXISTS idx_raw_batch_status ON fsi.raw_etl_batch(batch_status) WHERE batch_status IN ('RUNNING','FAILED','PARTIAL');
