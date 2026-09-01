-- atomic_asset_allocation_weight.sql
-- 原子指標：各類資產佔淨值比 (%)
-- 維度： 基金，大類資產匯總層面

WITH position_summary AS (
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(asset_class::text, 'UNCLASSIFIED') AS asset_type,
        SUM(market_value) AS asset_mv_hkd,
        SUM(SUM(market_value)) OVER (PARTITION BY port_id, evaluate_date) AS total_nav
    FROM fsi.balance_portfolio_asset
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
    GROUP BY port_id, evaluate_date, asset_class
)
SELECT
    fund_id,
    as_of_date,
    asset_type,
    asset_mv_hkd,
    total_nav,
    -- 各類資產佔淨值比 (%) = (某類資產總市值 / 基金淨資產 NAV) * 100
    CASE
        WHEN total_nav IS NULL OR total_nav = 0 THEN NULL
        ELSE ROUND((asset_mv_hkd / total_nav) * 100.0, 6)
    END AS weight_pct
FROM position_summary
ORDER BY weight_pct DESC NULLS LAST;