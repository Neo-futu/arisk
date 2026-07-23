-- atomic_sector_allocation_weight.sql
-- 原子指標：板塊/細分資產配置比 (%)

WITH position_summary AS (
    SELECT
        fund_id,
        as_of_date,
        COALESCE(sector, sub_asset_type, 'UNCLASSIFIED') AS sector_name,
        SUM(market_value_hkd) AS sector_mv_hkd,
        SUM(SUM(market_value_hkd)) OVER (PARTITION BY fund_id, as_of_date) AS total_nav
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
    GROUP BY fund_id, as_of_date, COALESCE(sector, sub_asset_type, 'UNCLASSIFIED')
)
SELECT
    fund_id,
    as_of_date,
    sector_name,
    sector_mv_hkd,
    total_nav,
    -- 板塊/細分資產配置比 (%) = (板塊總市值 / 基金淨資產 NAV) * 100
    CASE
        WHEN total_nav IS NULL OR total_nav = 0 THEN NULL
        ELSE ROUND((sector_mv_hkd / total_nav) * 100.0, 6)
    END AS weight_pct
FROM position_summary
ORDER BY weight_pct DESC NULLS LAST;