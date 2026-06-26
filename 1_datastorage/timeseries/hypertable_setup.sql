-- TimescaleDB hypertable 設置（高頻時間序列數據）
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 日內行情（tick / 分鐘 K 線）
CREATE TABLE IF NOT EXISTS ts.intraday_prices (
    time        TIMESTAMPTZ  NOT NULL,
    asset_id    VARCHAR(64)  NOT NULL,
    open        NUMERIC(16,8),
    high        NUMERIC(16,8),
    low         NUMERIC(16,8),
    close       NUMERIC(16,8),
    volume      NUMERIC(24,6),
    source      VARCHAR(32)  DEFAULT 'WIND'
);
SELECT create_hypertable('ts.intraday_prices', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_intraday_asset_time ON ts.intraday_prices(asset_id, time DESC);

-- NAV 實時計算序列
CREATE TABLE IF NOT EXISTS ts.nav_realtime (
    time        TIMESTAMPTZ  NOT NULL,
    fund_id     VARCHAR(32)  NOT NULL,
    class_id    VARCHAR(64),
    nav         NUMERIC(16,8) NOT NULL,
    calc_method VARCHAR(32)  DEFAULT 'MARKED_TO_MARKET'
);
SELECT create_hypertable('ts.nav_realtime', 'time', if_not_exists => TRUE);

-- 風控指標歷史（分鐘級）
CREATE TABLE IF NOT EXISTS ts.risk_metrics_realtime (
    time        TIMESTAMPTZ  NOT NULL,
    fund_id     VARCHAR(32)  NOT NULL,
    metric_name VARCHAR(64)  NOT NULL,
    value       NUMERIC(16,8) NOT NULL
);
SELECT create_hypertable('ts.risk_metrics_realtime', 'time', if_not_exists => TRUE);

-- 設置保留策略（保留 2 年）
SELECT add_retention_policy('ts.intraday_prices', INTERVAL '2 years', if_not_exists => TRUE);
SELECT add_retention_policy('ts.risk_metrics_realtime', INTERVAL '1 year', if_not_exists => TRUE);

-- 壓縮策略（7天後壓縮）
ALTER TABLE ts.intraday_prices SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset_id'
);
SELECT add_compression_policy('ts.intraday_prices', INTERVAL '7 days', if_not_exists => TRUE);
