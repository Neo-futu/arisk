-- atomic_industry_stock_weight.sql
-- 原子指標：某行業佔股票市值比 (%)

WITH stock_positions AS (
    SELECT
        fund_id,
        as_of_date,
        COALESCE(industry, 'UNCLASSIFIED') AS industry_name,
        SUM(market_value_hkd) AS industry_stock_mv_hkd,
        SUM(SUM(market_value_hkd)) OVER (PARTITION BY fund_id, as_of_date) AS total_stock_mv
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
      AND UPPER(asset_type) IN ('EQUITY', 'STOCK')
    GROUP BY fund_id, as_of_date, COALESCE(industry, 'UNCLASSIFIED')
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
FROM stock_positions
ORDER BY industry_stock_weight_pct DESC NULLS LAST;