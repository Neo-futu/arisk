-- atomic_portfolio_wam.sql
-- 貨幣基金組合加權平均剩餘期限 (Weighted Average Maturity, WAM)
-- 計算公式：
-- WAM (天) = \sum (Market_Value_i * Days_To_Maturity_i) / \sum (Market_Value_i)
-- 其中 Days_To_Maturity_i = Max(Maturity_Date_i - As_Of_Date, 0)

WITH portfolio_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之持倉
    SELECT
        fund_id,
        as_of_date,
        security_code,
        security_name,
        COALESCE(market_value_hkd, 0.0) AS market_value_hkd,
        SUM(COALESCE(market_value_hkd, 0.0)) OVER (PARTITION BY fund_id) AS total_portfolio_nav
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
      AND market_value_hkd > 0
),
maturity_joined AS (
    -- 2. 關聯證券主檔/分析數據表取得到期日，計算剩餘天數
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.security_name,
        p.market_value_hkd,
        p.total_portfolio_nav,
        b.maturity_date,
        CASE 
            WHEN b.maturity_date IS NOT NULL AND b.maturity_date >= p.as_of_date 
            THEN (b.maturity_date - p.as_of_date)
            WHEN b.maturity_date IS NOT NULL AND b.maturity_date < p.as_of_date
            THEN 0
            ELSE NULL
        END AS days_to_maturity,
        CASE WHEN b.maturity_date IS NOT NULL THEN 1 ELSE 0 END AS is_valid_instrument
    FROM portfolio_summary p
    LEFT JOIN fsi.bond_analytics b 
           ON p.security_code = b.security_code 
          AND p.as_of_date = b.as_of_date
),
aggregated_wam AS (
    -- 3. 聚合計算加權剩餘天數
    SELECT
        fund_id,
        as_of_date,
        MAX(total_portfolio_nav) AS total_portfolio_nav,
        SUM(CASE WHEN is_valid_instrument = 1 THEN market_value_hkd ELSE 0.0 END) AS total_mmf_mv,
        SUM(CASE WHEN is_valid_instrument = 1 THEN market_value_hkd * days_to_maturity ELSE 0.0 END) AS weighted_days_sum
    FROM maturity_joined
    GROUP BY fund_id, as_of_date
)
SELECT
    fund_id,
    as_of_date,
    total_portfolio_nav,
    total_mmf_mv,
    ROUND((total_mmf_mv / NULLIF(total_portfolio_nav, 0.0)) * 100.0, 4) AS mmf_weight_pct,
    
    -- 1. 加權平均剩餘期限 (天，以貨幣工具持倉為分母)
    ROUND(
        weighted_days_sum / NULLIF(total_mmf_mv, 0.0),
        2
    ) AS wam_days_mmf_only,
    
    -- 2. 加權平均剩餘期限 (年，按 365 天換算)
    ROUND(
        (weighted_days_sum / NULLIF(total_mmf_mv, 0.0)) / 365.0,
        4
    ) AS wam_years_mmf_only,

    -- 3. 加權平均剩餘期限 (天，以基金總淨值 NAV 為分母)
    ROUND(
        weighted_days_sum / NULLIF(total_portfolio_nav, 0.0),
        2
    ) AS wam_days_total_nav
FROM aggregated_wam;