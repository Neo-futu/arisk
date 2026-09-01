-- atomic_industry_stock_weight.sql
-- 原子指標：某行業佔股票市值比 (%)

WITH raw_stock_holdings AS (
    -- 1. 取出指定基金在指定日期的股票持倉，優先讀取持倉表 sector，備用靜態表 sector_level1
    SELECT
        b.port_id AS fund_id,
        b.evaluate_date AS as_of_date,
        COALESCE(
            NULLIF(TRIM(b.sector::text), ''),
            NULLIF(TRIM(s.sector_level1::text), ''),
            NULLIF(TRIM(s.sector_level2::text), ''),
            'UNCLASSIFIED'
        ) AS industry_name,
        COALESCE(b.market_value_base, b.market_value, 0.0) AS market_value_hkd
    FROM fsi.balance_stock b
    LEFT JOIN fsi.mktdata_stock_static s
      ON b.security_code = s.security_code
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