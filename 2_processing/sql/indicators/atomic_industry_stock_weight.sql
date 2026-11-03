-- atomic_industry_stock_weight.sql
-- 原子指標：某行業佔股票市值比 (%)

WITH raw_stock_holdings AS (
    -- 1. 股票持仓行业：持仓 sector > 行业表(GICS优先) > UNCLASSIFIED
    SELECT
        b.port_id AS fund_id,
        b.evaluate_date AS as_of_date,
        COALESCE(
            NULLIF(TRIM(b.sector::text), ''),
            NULLIF(TRIM(ind.level1_name::text), ''),
            NULLIF(TRIM(ind.industry_name::text), ''),
            'UNCLASSIFIED'
        ) AS industry_name,
        COALESCE(NULLIF(TRIM(ind.industry_code::text), ''), 'UNCLASSIFIED') AS industry_code,
        COALESCE(b.market_value_base, b.market_value, 0.0) AS market_value_hkd
    FROM fsi.balance_stock b
    LEFT JOIN LATERAL (
        SELECT i.industry_code, i.industry_name, i.level1_name
        FROM fsi.v_mktdata_stock_industry_current i
        WHERE i.security_code = b.security_code
        ORDER BY (i.standard = 'GICS') DESC, i.is_primary DESC
        LIMIT 1
    ) ind ON TRUE
    WHERE b.port_id = :fid
      AND b.evaluate_date = :end_date
),
industry_aggregated AS (
    -- 2. 按行業加總市值，計算股票總市值
    SELECT
        fund_id,
        as_of_date,
        industry_name,
        SUM(market_value_hkd) AS industry_stock_mv_hkd,
        SUM(SUM(market_value_hkd)) OVER (PARTITION BY fund_id, as_of_date) AS total_stock_mv
    FROM raw_stock_holdings
    GROUP BY fund_id, as_of_date, industry_name
)
SELECT
    fund_id,
    as_of_date,
    industry_name,
    industry_stock_mv_hkd,
    total_stock_mv,
    -- 某行業佔股票市值比 (%) = (特定行業股票總市值 / 全部股票總市值) * 100
    CASE
        WHEN total_stock_mv IS NULL OR total_stock_mv = 0 THEN NULL
        ELSE ROUND((industry_stock_mv_hkd / total_stock_mv) * 100.0, 6)
    END AS industry_stock_weight_pct
FROM industry_aggregated
ORDER BY industry_stock_weight_pct DESC NULLS LAST;