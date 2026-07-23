-- atomic_cumulative_return.sql
-- 原子指標：區間累積複利收益率 (%)

WITH ranked_nav AS (
    SELECT
        port_id AS fund_id,
        evaluate_date AS nav_date,
        COALESCE(net_asset, total_asset) AS total_nav,
        ROW_NUMBER() OVER (PARTITION BY port_id ORDER BY evaluate_date ASC) AS rn_asc,
        ROW_NUMBER() OVER (PARTITION BY port_id ORDER BY evaluate_date DESC) AS rn_desc
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
      AND COALESCE(net_asset, total_asset) IS NOT NULL
),
start_end_nav AS (
    SELECT
        fund_id,
        MAX(CASE WHEN rn_asc = 1 THEN nav_date END) AS start_date,
        MAX(CASE WHEN rn_desc = 1 THEN nav_date END) AS end_date,
        MAX(CASE WHEN rn_asc = 1 THEN total_nav END) AS start_nav,
        MAX(CASE WHEN rn_desc = 1 THEN total_nav END) AS end_nav,
        COUNT(*) AS sample_size
    FROM ranked_nav
    GROUP BY fund_id
)
SELECT
    fund_id,
    start_date,
    end_date,
    start_nav,
    end_nav,
    sample_size,
    -- 區間累積複利收益率 (%) = ((NAV_end - NAV_start) / NAV_start) * 100
    CASE
        WHEN start_nav IS NULL OR start_nav <= 0 THEN NULL
        ELSE ROUND(((end_nav - start_nav) / start_nav) * 100.0, 6)
    END AS cumulative_return_pct
FROM start_end_nav;