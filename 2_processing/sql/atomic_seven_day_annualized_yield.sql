-- atomic_seven_day_annualized_yield.sql
-- 原子指標：七日年化收益率（貨幣 %）

WITH nav_series AS (
    -- 獲取基準日及之前的歷史 NAV 序列
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, total_asset) AS total_nav
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date <= :as_of_date
      AND COALESCE(net_asset, total_asset) IS NOT NULL
    ORDER BY evaluate_date DESC
    LIMIT 15
),
ordered_nav AS (
    SELECT
        fund_id,
        as_of_date,
        total_nav,
        LAG(total_nav) OVER (PARTITION BY fund_id ORDER BY as_of_date ASC) AS prev_nav
    FROM nav_series
),
recent_daily_returns AS (
    -- 篩選最新 7 個交易日的單日收益率
    SELECT
        fund_id,
        as_of_date,
        (total_nav - prev_nav) / prev_nav AS daily_return
    FROM ordered_nav
    WHERE prev_nav IS NOT NULL AND prev_nav > 0
    ORDER BY as_of_date DESC
    LIMIT 7
)
SELECT
    :fid AS fund_id,
    MAX(as_of_date) AS as_of_date,
    COUNT(*) AS sample_days,
    -- 七日年化收益率 (%) = (7 日日均收益率) * 365 * 100
    CASE
        WHEN COUNT(*) < 7 THEN NULL
        ELSE ROUND(AVG(daily_return) * 365.0 * 100.0, 6)
    END AS seven_day_annualized_yield_pct
FROM recent_daily_returns;