-- atomic_avg_nav_ratio.sql
-- 日均佔資產淨值 (%)
-- 計算區間內（全區間 / 持有區間）該證券每日市值佔基金資產淨值比率的算術平均值

WITH all_assets_union AS (
    -- 1. 債券類 (Bond)
    SELECT
        evaluate_date,
        port_id,
        'BOND' AS asset_class,
        CAST(security_code AS VARCHAR) AS security_code,
        CAST(security_name AS VARCHAR) AS security_name,
        COALESCE(market_value, 0.0) AS market_value
    FROM fsi.balance_bond

    UNION ALL

    -- 2. 股票類 (Stock)
    SELECT
        evaluate_date,
        port_id,
        'STOCK' AS asset_class,
        CAST(security_code AS VARCHAR) AS security_code,
        CAST(security_name AS VARCHAR) AS security_name,
        COALESCE(market_value, 0.0) AS market_value
    FROM fsi.balance_stock

    UNION ALL

    -- 3. 現金類 (Cash)
    SELECT
        evaluate_date,
        port_id,
        'CASH' AS asset_class,
        CAST(cash_account_id AS VARCHAR) AS security_code,
        CAST(account_name AS VARCHAR) AS security_name,
        COALESCE(amount, 0.0) AS market_value
    FROM fsi.balance_cash

    UNION ALL

    -- 4. 存款類 (Deposit)
    SELECT
        evaluate_date,
        port_id,
        'DEPOSIT' AS asset_class,
        CAST(deposit_id AS VARCHAR) AS security_code,
        CAST(deposit_name AS VARCHAR) AS security_name,
        COALESCE(total_value, principal, 0.0) AS market_value
    FROM fsi.balance_deposit

    UNION ALL

    -- 5. 存單類 (CD)
    SELECT
        evaluate_date,
        port_id,
        'CD' AS asset_class,
        CAST(security_code AS VARCHAR) AS security_code,
        CAST(security_name AS VARCHAR) AS security_name,
        COALESCE(market_value, 0.0) AS market_value
    FROM fsi.balance_cd

    UNION ALL

    -- 6. 基金類 (Fund)
    SELECT
        evaluate_date,
        port_id,
        'FUND' AS asset_class,
        CAST(security_code AS VARCHAR) AS security_code,
        CAST(security_name AS VARCHAR) AS security_name,
        COALESCE(market_value, 0.0) AS market_value
    FROM fsi.balance_fund

    UNION ALL

    -- 7. 期貨類 (Futures)
    SELECT
        evaluate_date,
        port_id,
        'FUTURES' AS asset_class,
        CAST(contract_code AS VARCHAR) AS security_code,
        CAST(contract_name AS VARCHAR) AS security_name,
        COALESCE(market_value, 0.0) AS market_value
    FROM fsi.balance_futures

    UNION ALL

    -- 8. 期權類 (Options)
    SELECT
        evaluate_date,
        port_id,
        'OPTIONS' AS asset_class,
        CAST(contract_code AS VARCHAR) AS security_code,
        CAST(contract_name AS VARCHAR) AS security_name,
        COALESCE(market_value, 0.0) AS market_value
    FROM fsi.balance_options

    UNION ALL

    -- 9. 回購類 (Repo)
    SELECT
        evaluate_date,
        port_id,
        'REPO' AS asset_class,
        CAST(repo_id AS VARCHAR) AS security_code,
        CAST(COALESCE(pledged_security_name, repo_type, repo_id) AS VARCHAR) AS security_name,
        COALESCE(total_value, principal, 0.0) AS market_value
    FROM fsi.balance_repo

    UNION ALL

    -- 10. 退休金類 (Pension)
    SELECT
        evaluate_date,
        port_id,
        'PENSION' AS asset_class,
        CAST(security_code AS VARCHAR) AS security_code,
        CAST(security_name AS VARCHAR) AS security_name,
        COALESCE(market_value, 0.0) AS market_value
    FROM fsi.balance_pension
),
calendar_days AS (
    SELECT DISTINCT evaluate_date AS as_of_date, port_id AS fund_id
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
portfolio_nav AS (
    SELECT 
        evaluate_date AS as_of_date,
        port_id AS fund_id,
        COALESCE(net_asset, total_asset, 0.0) AS total_nav_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
filtered_assets AS (
    SELECT 
        evaluate_date,
        port_id,
        asset_class,
        security_code,
        security_name,
        market_value
    FROM all_assets_union
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
distinct_securities AS (
    SELECT DISTINCT 
        port_id AS fund_id,
        asset_class,
        security_code,
        security_name
    FROM filtered_assets
    WHERE security_code IS NOT NULL
),
cartesian_universe AS (
    SELECT 
        c.as_of_date,
        c.fund_id,
        s.asset_class,
        s.security_code,
        s.security_name
    FROM calendar_days c
    CROSS JOIN distinct_securities s
),
daily_security_ratio AS (
    SELECT
        u.as_of_date,
        u.fund_id,
        u.asset_class,
        u.security_code,
        u.security_name,
        COALESCE(p.market_value, 0.0) AS security_mv,
        COALESCE(n.total_nav_hkd, 0.0) AS total_nav_hkd,
        CASE 
            WHEN COALESCE(n.total_nav_hkd, 0.0) > 0 THEN COALESCE(p.market_value, 0.0) / n.total_nav_hkd
            ELSE 0.0 
        END AS daily_nav_ratio
    FROM cartesian_universe u
    JOIN portfolio_nav n ON u.as_of_date = n.as_of_date AND u.fund_id = n.fund_id
    LEFT JOIN filtered_assets p 
      ON u.as_of_date = p.evaluate_date 
     AND u.fund_id = p.port_id 
     AND u.asset_class = p.asset_class 
     AND u.security_code = p.security_code
),
total_days AS (
    SELECT COUNT(DISTINCT as_of_date) AS total_trading_days
    FROM calendar_days
)
SELECT
    d.fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    d.asset_class,
    d.security_code,
    d.security_name,
    COUNT(CASE WHEN d.security_mv > 0 THEN 1 END) AS holding_days,
    t.total_trading_days,
    ROUND(
        AVG(CASE WHEN d.security_mv > 0 THEN d.daily_nav_ratio END) * 100.0, 
        6
    ) AS avg_nav_ratio_holding_period_pct,
    ROUND(
        (SUM(d.daily_nav_ratio) / NULLIF(t.total_trading_days, 0)) * 100.0, 
        6
    ) AS avg_nav_ratio_full_period_pct
FROM daily_security_ratio d
CROSS JOIN total_days t
WHERE d.security_code IS NOT NULL
GROUP BY d.fund_id, d.asset_class, d.security_code, d.security_name, t.total_trading_days
ORDER BY avg_nav_ratio_full_period_pct DESC NULLS LAST;