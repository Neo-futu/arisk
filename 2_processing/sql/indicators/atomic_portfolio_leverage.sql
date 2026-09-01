-- atomic_portfolio_leverage.sql
-- 基金總槓桿率 (Total Portfolio Leverage Ratio, %)
-- 計算公式 (Gross Method 標準定義)：
-- 1. 總資產槓桿率 (Gross Asset Leverage, %) = (總資產 Total Assets / 基金淨值 Total NAV) * 100%
-- 2. 總敞口槓桿率 (Gross Exposure Leverage, %) = (總名義敞口 Gross Exposure / 基金淨值 Total NAV) * 100%
--    其中 Gross Exposure = 實物資產市值 + 衍生品名義本金 (Notional Amount)

WITH nav_summary AS (
    -- 1. 取得指定基準日之基金淨值 (NAV) 與總資產 (Total Assets)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS total_nav_hkd,
        COALESCE(total_asset, net_asset, 0.0) AS total_gross_assets_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
physical_assets AS (
    -- 2. 彙整所有實物資產市值 (Stock, Bond, Fund, Deposit, CD, Cash, Repo)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        SUM(market_value_hkd) AS total_physical_mv_hkd
    FROM (
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, 0.0)) AS market_value_hkd FROM fsi.balance_stock WHERE port_id = :fid AND evaluate_date = :as_of_date
        UNION ALL
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, 0.0)) AS market_value_hkd FROM fsi.balance_bond WHERE port_id = :fid AND evaluate_date = :as_of_date
        UNION ALL
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, 0.0)) AS market_value_hkd FROM fsi.balance_fund WHERE port_id = :fid AND evaluate_date = :as_of_date
        UNION ALL
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, amount, 0.0)) AS market_value_hkd FROM fsi.balance_deposit WHERE port_id = :fid AND evaluate_date = :as_of_date
        UNION ALL
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, amount, 0.0)) AS market_value_hkd FROM fsi.balance_cd WHERE port_id = :fid AND evaluate_date = :as_of_date
        UNION ALL
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, amount, 0.0)) AS market_value_hkd FROM fsi.balance_cash WHERE port_id = :fid AND evaluate_date = :as_of_date
        UNION ALL
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, amount, 0.0)) AS market_value_hkd FROM fsi.balance_repo WHERE port_id = :fid AND evaluate_date = :as_of_date
    ) sub_physical
    GROUP BY port_id, evaluate_date
),
derivative_assets AS (
    -- 3. 彙整衍生品名義本金敞口 (Futures, Options)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        SUM(notional_hkd) AS total_derivative_notional_hkd
    FROM (
        SELECT port_id, evaluate_date, ABS(COALESCE(notional_amount, market_value, 0.0)) AS notional_hkd FROM fsi.balance_futures WHERE port_id = :fid AND evaluate_date = :as_of_date
        UNION ALL
        SELECT port_id, evaluate_date, ABS(COALESCE(notional_amount, market_value, 0.0)) AS notional_hkd FROM fsi.balance_options WHERE port_id = :fid AND evaluate_date = :as_of_date
    ) sub_derivatives
    GROUP BY port_id, evaluate_date
),
leverage_calculated AS (
    -- 4. 整合各項敞口數據
    SELECT
        n.fund_id,
        n.as_of_date,
        n.total_nav_hkd,
        n.total_gross_assets_hkd,
        COALESCE(p.total_physical_mv_hkd, 0.0) AS physical_asset_mv_hkd,
        COALESCE(d.total_derivative_notional_hkd, 0.0) AS derivative_gross_notional_hkd,
        (COALESCE(p.total_physical_mv_hkd, 0.0) + COALESCE(d.total_derivative_notional_hkd, 0.0)) AS total_gross_exposure_hkd
    FROM nav_summary n
    LEFT JOIN physical_assets p 
           ON n.fund_id = p.fund_id 
          AND n.as_of_date = p.as_of_date
    LEFT JOIN derivative_assets d 
           ON n.fund_id = d.fund_id 
          AND n.as_of_date = d.as_of_date
)
SELECT
    fund_id,
    as_of_date,
    ROUND(total_nav_hkd, 2) AS total_nav_hkd,
    ROUND(total_gross_assets_hkd, 2) AS total_gross_assets_hkd,
    ROUND(physical_asset_mv_hkd, 2) AS physical_asset_mv_hkd,
    ROUND(derivative_gross_notional_hkd, 2) AS derivative_gross_notional_hkd,
    ROUND(total_gross_exposure_hkd, 2) AS total_gross_exposure_hkd,
    
    -- 1. 總資產槓桿率 (%) (Total Assets / NAV)
    ROUND(
        (total_gross_assets_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS gross_asset_leverage_pct,
    
    -- 2. 總敞口槓桿率 (%) (Gross Exposure / NAV)
    ROUND(
        (total_gross_exposure_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS gross_exposure_leverage_pct
FROM leverage_calculated;