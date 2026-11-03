-- ============================================================
-- 028_attribution_benchmark_market.sql
-- 指数三表：mktdata_index、mktdata_index_quotes、mktdata_index_component。
-- 行情与每日成分由 seed_attribution_market.py 写入。
-- ============================================================

DO $$
BEGIN
    IF to_regclass('fsi.mktdata_index') IS NULL
       AND to_regclass('fsi.mktdata_index_static') IS NOT NULL THEN
        ALTER TABLE fsi.mktdata_index_static RENAME TO mktdata_index;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS fsi.mktdata_index (
    index_code         VARCHAR(32)  PRIMARY KEY,
    index_name         VARCHAR(200) NOT NULL,
    index_name_en      VARCHAR(200),
    currency           CHAR(3)      NOT NULL,
    index_type         VARCHAR(16),
    asset_class        VARCHAR(16),
    country            CHAR(2),
    base_date          DATE,
    base_value         NUMERIC(16,4),
    provider           VARCHAR(64),
    source_ticker_wind VARCHAR(32),
    source_ticker_bbg  VARCHAR(32),
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

DROP VIEW IF EXISTS fsi.mktdata_index_static;
CREATE VIEW fsi.mktdata_index_static AS
SELECT * FROM fsi.mktdata_index;

COMMENT ON TABLE fsi.mktdata_index IS '指数定义：归因与基准比较';
COMMENT ON VIEW fsi.mktdata_index_static IS '兼容旧名，等同 mktdata_index';

INSERT INTO fsi.mktdata_index (
    index_code, index_name, index_name_en, currency, index_type,
    asset_class, country, base_date, base_value, provider,
    source_ticker_wind, source_ticker_bbg, is_active
) VALUES
    ('HSI', '恒生指数', 'Hang Seng Index', 'HKD', 'PRICE',
     'EQUITY', 'HK', DATE '1964-07-31', 100, 'Hang Seng',
     'HSI.HI', 'HSI Index', TRUE),
    ('USD_AGG', '美国投资级综合债', 'US Aggregate Bond', 'USD', 'TOTAL_RETURN',
     'BOND', 'US', DATE '2003-09-22', 100, 'Bloomberg',
     'LUACTRUU', 'LBUSTRUU Index', TRUE)
ON CONFLICT (index_code) DO UPDATE
SET index_name = EXCLUDED.index_name,
    index_name_en = EXCLUDED.index_name_en,
    currency = EXCLUDED.currency,
    index_type = EXCLUDED.index_type,
    asset_class = EXCLUDED.asset_class,
    provider = EXCLUDED.provider,
    source_ticker_bbg = EXCLUDED.source_ticker_bbg,
    is_active = TRUE;

INSERT INTO fsi.para_benchmark_def (
    benchmark_id, benchmark_name, benchmark_name_en, benchmark_type,
    currency, source, source_ticker, plus_bps, description, is_active
) VALUES
    ('HSI', '恒生指数', 'Hang Seng Index', 'INDEX',
     'HKD', 'YFINANCE', '^HSI', 0,
     '权益基准。成分暂按代表个券，权重由行情倒推。', TRUE),
    ('USD_AGG', '美国投资级综合债', 'US Aggregate Bond', 'INDEX',
     'USD', 'YFINANCE', 'AGG', 0,
     '债券基准。成分暂用持仓中的债券 ETF，权重由行情倒推。', TRUE)
ON CONFLICT (benchmark_id) DO UPDATE
SET benchmark_name = EXCLUDED.benchmark_name,
    benchmark_name_en = EXCLUDED.benchmark_name_en,
    benchmark_type = EXCLUDED.benchmark_type,
    source = EXCLUDED.source,
    source_ticker = EXCLUDED.source_ticker,
    description = EXCLUDED.description,
    is_active = TRUE;

-- 债指数成分并入 mktdata_index_component，不再单独落债券成分表
INSERT INTO fsi.mktdata_index_component (
    rebal_date, index_code, security_code, weight_pct, data_source
)
SELECT rebal_date, index_code, security_code, weight_pct, data_source
FROM fsi.mktdata_index_bond_component
WHERE index_code = 'USD_AGG'
ON CONFLICT (rebal_date, index_code, security_code) DO UPDATE
SET weight_pct = EXCLUDED.weight_pct,
    data_source = EXCLUDED.data_source;

DELETE FROM fsi.mktdata_index_bond_component
WHERE index_code = 'USD_AGG';

-- 债券型组合增加债基准，保留已有恒生主基准，归因页可切换
INSERT INTO fsi.para_portfolio_benchmark (
    port_id, benchmark_id, begin_date, end_date, weight_pct, benchmark_role
)
SELECT p.port_id, 'USD_AGG', DATE '2020-01-01', NULL, 100.0000, 'SECONDARY'
FROM fsi.para_portfolio p
WHERE p.port_id IN ('BHMMF001', 'BHMMF002', 'DV01TEST001')
ON CONFLICT (port_id, benchmark_id, begin_date) DO UPDATE
SET end_date = NULL,
    weight_pct = EXCLUDED.weight_pct,
    benchmark_role = EXCLUDED.benchmark_role;
