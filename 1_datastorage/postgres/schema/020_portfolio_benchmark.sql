-- ============================================================
-- 020_portfolio_benchmark.sql
-- 组合基准：para_benchmark_def + para_portfolio_benchmark
-- 以及指数主数据、与净值日对齐的指数行情、跟踪误差控制线
-- ============================================================

INSERT INTO fsi.para_benchmark_def (
    benchmark_id, benchmark_name, benchmark_name_en, benchmark_type,
    currency, source, source_ticker, plus_bps, description, is_active
) VALUES (
    'HSI', '恒生指数', 'Hang Seng Index', 'INDEX',
    'HKD', 'INTERNAL', 'HSI.HI', 0,
    '组合主基准：用于超额收益、信息比率、跟踪误差与权益 Beta',
    TRUE
)
ON CONFLICT (benchmark_id) DO UPDATE
    SET benchmark_name = EXCLUDED.benchmark_name,
        benchmark_type = EXCLUDED.benchmark_type,
        source_ticker = EXCLUDED.source_ticker,
        description = EXCLUDED.description,
        is_active = TRUE;

INSERT INTO fsi.mktdata_index_static (
    index_code, index_name, index_name_en, currency, index_type,
    asset_class, country, base_date, base_value, provider, source_ticker_wind, is_active
) VALUES (
    'HSI', '恒生指数', 'Hang Seng Index', 'HKD', 'PRICE',
    'EQUITY', 'HK', DATE '2020-01-02', 18000, 'Hang Seng', 'HSI.HI', TRUE
)
ON CONFLICT (index_code) DO UPDATE
    SET index_name = EXCLUDED.index_name,
        currency = EXCLUDED.currency,
        is_active = TRUE;

INSERT INTO fsi.para_portfolio_benchmark (
    port_id, benchmark_id, begin_date, end_date, weight_pct, benchmark_role
)
SELECT p.port_id, 'HSI', DATE '2020-01-01', NULL, 100.0000, 'PRIMARY'
FROM fsi.para_portfolio p
ON CONFLICT (port_id, benchmark_id, begin_date) DO UPDATE
    SET end_date = NULL,
        weight_pct = EXCLUDED.weight_pct,
        benchmark_role = EXCLUDED.benchmark_role;

-- 持仓个股收盘价为常数时 Beta 无法估计。按交易日生成有波动的收盘价，再让基准跟踪该收益。
WITH ordered AS (
    SELECT price_date,
           ROW_NUMBER() OVER (ORDER BY price_date) AS n
    FROM fsi.mktdata_quotes
    WHERE security_code = '0700.HK'
      AND price_type = 'CLOSE'
),
priced AS (
    SELECT price_date,
           ROUND(
               (380.0 * EXP(SUM(LN(1.0 + (0.0012 + 0.008 * SIN(n * 0.55)))) OVER (ORDER BY n)))::numeric,
               4
           ) AS close_price
    FROM ordered
),
with_prev AS (
    SELECT price_date,
           close_price,
           LAG(close_price) OVER (ORDER BY price_date) AS prev_close
    FROM priced
)
UPDATE fsi.mktdata_quotes AS q
SET close_price = w.close_price,
    open_price = w.close_price,
    high_price = w.close_price,
    low_price = w.close_price,
    prev_close = w.prev_close,
    price_change_pct = CASE
        WHEN w.prev_close IS NULL OR w.prev_close = 0 THEN NULL
        ELSE ROUND(((w.close_price / w.prev_close - 1.0) * 100.0)::numeric, 6)
    END
FROM with_prev AS w
WHERE q.security_code = '0700.HK'
  AND q.price_type = 'CLOSE'
  AND q.price_date = w.price_date;

-- 指数点位与净值日、个券行情日对齐，保证跟踪误差 / Beta 有共同交易日
WITH days AS (
    SELECT DISTINCT price_date
    FROM (
        SELECT evaluate_date AS price_date FROM fsi.balance_portfolio_nav
        UNION
        SELECT price_date FROM fsi.mktdata_quotes
    ) src
    WHERE price_date IS NOT NULL
),
stock_ret AS (
    SELECT price_date,
           close_price / LAG(close_price) OVER (ORDER BY price_date) - 1.0 AS stock_ret
    FROM fsi.mktdata_quotes
    WHERE security_code = '0700.HK'
      AND price_type = 'CLOSE'
      AND close_price IS NOT NULL
),
stepped AS (
    SELECT d.price_date,
           COALESCE(
               0.85 * s.stock_ret,
               0.00015 + 0.0035 * SIN(ROW_NUMBER() OVER (ORDER BY d.price_date) * 0.37)
           ) AS daily_ret
    FROM days d
    LEFT JOIN stock_ret s ON s.price_date = d.price_date
),
priced AS (
    SELECT price_date,
           daily_ret,
           ROUND(
               (18000.0 * EXP(SUM(LN(1.0 + daily_ret)) OVER (ORDER BY price_date)))::numeric,
               4
           ) AS close_price
    FROM stepped
)
INSERT INTO fsi.mktdata_index_quotes (
    price_date, index_code, open_price, high_price, low_price,
    close_price, prev_close, price_change_pct, data_source
)
SELECT price_date,
       'HSI',
       close_price,
       close_price,
       close_price,
       close_price,
       LAG(close_price) OVER (ORDER BY price_date),
       ROUND((daily_ret * 100.0)::numeric, 6),
       'INTERNAL'
FROM priced
ON CONFLICT (price_date, index_code) DO UPDATE
    SET close_price = EXCLUDED.close_price,
        open_price = EXCLUDED.open_price,
        high_price = EXCLUDED.high_price,
        low_price = EXCLUDED.low_price,
        prev_close = EXCLUDED.prev_close,
        price_change_pct = EXCLUDED.price_change_pct,
        data_source = EXCLUDED.data_source;

INSERT INTO fsi.para_risk_limit_regulatory (
    port_id, regulation_src, rule_code, rule_name, rule_name_en,
    dimension, limit_value, limit_unit, limit_direction,
    clause_ref, effective_date, is_active
)
SELECT p.port_id, 'MANDATE', 'MAX_TRACKING_ERROR', '跟踪误差控制线', 'Tracking error limit',
       'TRACKING_ERROR', 8.0000, 'PCT', 'MAX',
       '组合基准委托：年化跟踪误差上限', DATE '2020-01-01', TRUE
FROM fsi.para_portfolio p
WHERE NOT EXISTS (
    SELECT 1
    FROM fsi.para_risk_limit_regulatory r
    WHERE r.port_id = p.port_id
      AND r.rule_code = 'MAX_TRACKING_ERROR'
      AND r.is_active = TRUE
);
