-- atomic_daily_return.sql
-- 原子指標：日收益率 (%)

WITH daily_nav AS (
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, total_asset) AS total_nav
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
      AND COALESCE(net_asset, total_asset) IS NOT NULL
),
nav_with_lag AS (
    SELECT
        fund_id,
        as_of_date,
        total_nav,
        LAG(total_nav) OVER (PARTITION BY fund_id ORDER BY as_of_date ASC) AS prev_nav
    FROM daily_nav
)
SELECT
    fund_id,
    as_of_date,
    total_nav,
    prev_nav,
    -- 日收益率 (%) = (NAV_t - NAV_{t-1}) / NAV_{t-1} * 100
    CASE
        WHEN prev_nav IS NULL OR prev_nav = 0 THEN NULL
        ELSE ROUND(((total_nav - prev_nav) / prev_nav) * 100.0, 6)
    END AS daily_return_pct
FROM nav_with_lag
ORDER BY as_of_date ASC;