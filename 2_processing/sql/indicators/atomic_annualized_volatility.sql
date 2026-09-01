-- atomic_annualized_volatility.sql
-- 年化波動率 (%)
-- 計算公式：年化波動率 = 日收益率樣本標準差 (Sample Std Dev) * \sqrt{252} * 100%
-- 維度： 基金

WITH daily_returns AS (
    SELECT
        evaluate_date AS as_of_date,
        port_id AS fund_id,
        COALESCE(day_return, 0.0) AS r_p
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
)
SELECT
    fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    COUNT(r_p) AS trading_days,
    
    -- 日收益率標準差 (%)
    ROUND(COALESCE(STDDEV_SAMP(r_p), 0.0) * 100.0, 6) AS daily_volatility_pct,
    
    -- 年化波動率 (依 252 交易日標準年化, %)
    ROUND(COALESCE(STDDEV_SAMP(r_p), 0.0) * SQRT(252.0) * 100.0, 6) AS annualized_volatility_252_pct,
    
    -- 年化波動率 (依 365 自然日年化, %)
    ROUND(COALESCE(STDDEV_SAMP(r_p), 0.0) * SQRT(365.0) * 100.0, 6) AS annualized_volatility_365_pct
FROM daily_returns
GROUP BY fund_id;