-- atomic_portfolio_leverage.sql
-- 基金總槓桿率 (Total Portfolio Leverage Ratio, %)
-- 計算公式 (Gross / Commitment Method 標準定義)：
-- 1. 總資產槓桿率 (Gross Leverage - Total Assets Basis, %) = (總資產 Gross Assets / 基金淨值 Total NAV) * 100%
-- 2. 總敞口槓桿率 (Gross Exposure Leverage, %) = (總名義敞口 Gross Exposure / 基金淨值 Total NAV) * 100%
--    其中 Gross Exposure = 實物資產市值 + 衍生品名義本金 (Notional Value) / 標的等值市值

WITH nav_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之基金淨值 NAV 與總資產 (Gross Assets)
    SELECT
        fund_id,
        nav_date AS as_of_date,
        COALESCE(net_asset_value_hkd, 0.0) AS total_nav_hkd,
        COALESCE(total_asset_value_hkd, 0.0) AS total_gross_assets_hkd
    FROM fsi.fund_nav
    WHERE fund_id = :fid
      AND nav_date = :as_of_date
),
exposure_summary AS (
    -- 2. 統計持倉之總名義敞口 (包含實物持倉與衍生品名義敞口)
    SELECT
        fund_id,
        as_of_date,
        -- 實物資產總市值
        SUM(CASE WHEN instrument_type NOT IN ('DERIVATIVE', 'FUTURES', 'FORWARD', 'SWAP', 'OPTION') 
                 THEN ABS(COALESCE(market_value_hkd, 0.0)) 
                 ELSE 0.0 
            END) AS physical_asset_mv_hkd,
        -- 衍生品總名義敞口 (Gross Notional Value)
        SUM(CASE WHEN instrument_type IN ('DERIVATIVE', 'FUTURES', 'FORWARD', 'SWAP', 'OPTION') 
                 THEN ABS(COALESCE(notional_value_hkd, market_value_hkd, 0.0)) 
                 ELSE 0.0 
            END) AS derivative_gross_notional_hkd,
        -- 總名義敞口 (Gross Exposure)
        SUM(
            CASE 
                WHEN instrument_type IN ('DERIVATIVE', 'FUTURES', 'FORWARD', 'SWAP', 'OPTION') 
                THEN ABS(COALESCE(notional_value_hkd, market_value_hkd, 0.0))
                ELSE ABS(COALESCE(market_value_hkd, 0.0))
            END
        ) AS total_gross_exposure_hkd
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
    GROUP BY fund_id, as_of_date
),
leverage_calculated AS (
    -- 3. 整合 NAV 與敞口數據
    SELECT
        n.fund_id,
        n.as_of_date,
        n.total_nav_hkd,
        n.total_gross_assets_hkd,
        COALESCE(e.physical_asset_mv_hkd, 0.0) AS physical_asset_mv_hkd,
        COALESCE(e.derivative_gross_notional_hkd, 0.0) AS derivative_gross_notional_hkd,
        COALESCE(e.total_gross_exposure_hkd, 0.0) AS total_gross_exposure_hkd
    FROM nav_summary n
    LEFT JOIN exposure_summary e 
           ON n.fund_id = e.fund_id 
          AND n.as_of_date = e.as_of_date
)
SELECT
    fund_id,
    as_of_date,
    ROUND(total_nav_hkd, 2) AS total_nav_hkd,
    ROUND(total_gross_assets_hkd, 2) AS total_gross_assets_hkd,
    ROUND(physical_asset_mv_hkd, 2) AS physical_asset_mv_hkd,
    ROUND(derivative_gross_notional_hkd, 2) AS derivative_gross_notional_hkd,
    ROUND(total_gross_exposure_hkd, 2) AS total_gross_exposure_hkd,
    
    -- 1. 總資產槓桿率 (%) (Gross Assets / NAV)
    ROUND(
        (total_gross_assets_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS gross_asset_leverage_pct,
    
    -- 2. 總敞口槓桿率 (%) (Gross Exposure / NAV, 涵蓋衍生品名義本金)
    ROUND(
        (total_gross_exposure_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS gross_exposure_leverage_pct
FROM leverage_calculated;