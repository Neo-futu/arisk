-- atomic_portfolio_wal.sql
-- 貨幣基金組合加權平均剩餘存續期 / 最終剩餘期限 (Weighted Average Life, WAL) 及加權平均修正存續期 (Weighted Duration)
-- 計算說明：
-- 1. 剩餘存續期 (WAL)：採用法定最終到期日 (Final Maturity Date) 計算剩餘天數，不考慮浮動利率工具的利息重置日。
--    WAL (天) = \sum (Market_Value_i * Final_Days_To_Maturity_i) / \sum (Market_Value_i)
-- 2. 加權修正存續期 (Weighted Modified Duration)：
--    Weighted Duration (年) = \sum (Market_Value_i * Modified_Duration_i) / \sum (Market_Value_i)

WITH portfolio_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之持倉與總淨值
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
analytics_joined AS (
    -- 2. 關聯證券分析數據表取得最終到期日與存續期 (Duration)
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.security_name,
        p.market_value_hkd,
        p.total_portfolio_nav,
        b.final_maturity_date,
        COALESCE(b.modified_duration, 0.0) AS modified_duration,
        CASE 
            WHEN b.final_maturity_date IS NOT NULL AND b.final_maturity_date >= p.as_of_date 
            THEN (b.final_maturity_date - p.as_of_date)
            WHEN b.final_maturity_date IS NOT NULL AND b.final_maturity_date < p.as_of_date
            THEN 0
            ELSE NULL
        END AS final_days_to_maturity,
        CASE WHEN b.final_maturity_date IS NOT NULL THEN 1 ELSE 0 END AS is_valid_instrument
    FROM portfolio_summary p
    LEFT JOIN fsi.bond_analytics b 
           ON p.security_code = b.security_code 
          AND p.as_of_date = b.as_of_date
),
aggregated_wal AS (
    -- 3. 聚合計算加權 WAL 與加權 Duration
    SELECT
        fund_id,
        as_of_date,
        MAX(total_portfolio_nav) AS total_portfolio_nav,
        SUM(CASE WHEN is_valid_instrument = 1 THEN market_value_hkd ELSE 0.0 END) AS total_mmf_mv,
        SUM(CASE WHEN is_valid_instrument = 1 THEN market_value_hkd * final_days_to_maturity ELSE 0.0 END) AS weighted_wal_days_sum,
        SUM(CASE WHEN is_valid_instrument = 1 THEN market_value_hkd * modified_duration ELSE 0.0 END) AS weighted_duration_sum
    FROM analytics_joined
    GROUP BY fund_id, as_of_date
)
SELECT
    fund_id,
    as_of_date,
    total_portfolio_nav,
    total_mmf_mv,
    ROUND((total_mmf_mv / NULLIF(total_portfolio_nav, 0.0)) * 100.0, 4) AS mmf_weight_pct,
    
    -- 1. 加權平均剩餘存續期 (WAL，天)
    ROUND(
        weighted_wal_days_sum / NULLIF(total_mmf_mv, 0.0),
        2
    ) AS wal_days_mmf_only,
    
    -- 2. 加權平均剩餘存續期 (WAL，年，按 365 天換算)
    ROUND(
        (weighted_wal_days_sum / NULLIF(total_mmf_mv, 0.0)) / 365.0,
        4
    ) AS wal_years_mmf_only,

    -- 3. 加權平均修正存續期 (Weighted Modified Duration，年)
    ROUND(
        weighted_duration_sum / NULLIF(total_mmf_mv, 0.0),
        4
    ) AS weighted_duration_years,

    -- 4. 加權平均剩餘存續期 (WAL，天，以基金總淨值 NAV 為分母)
    ROUND(
        weighted_wal_days_sum / NULLIF(total_portfolio_nav, 0.0),
        2
    ) AS wal_days_total_nav
FROM aggregated_wal;