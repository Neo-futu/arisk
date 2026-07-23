-- atomic_tracking_error.sql
-- 基金組合跟蹤誤差 (Tracking Error, TE)
-- 計算公式：TE = STDDEV_SAMP(R_p,t - R_m,t) * SQRT(252) * 100%

WITH daily_portfolio AS (
    SELECT
        as_of_date,
        fund_id,
        SUM(COALESCE(market_value_hkd, 0.0)) AS total_mv,
        SUM(COALESCE(pnl_hkd, 0.0)) AS total_pnl
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN :start_date AND :end_date
    GROUP BY as_of_date, fund_id
),
daily_portfolio_returns AS (
    SELECT
        as_of_date,
        fund_id,
        CASE WHEN total_mv > 0 THEN total_pnl / total_mv ELSE 0.0 END AS r_p
    FROM daily_portfolio
),
daily_benchmark_returns AS (
    SELECT
        as_of_date,
        benchmark_code,
        return_rate AS r_m
    FROM fsi.benchmark_daily_returns
    WHERE benchmark_code = :bm_code
      AND as_of_date BETWEEN :start_date AND :end_date
),
excess_returns AS (
    SELECT
        p.fund_id,
        b.benchmark_code,
        p.as_of_date,
        p.r_p,
        b.r_m,
        (p.r_p - b.r_m) AS excess_return
    FROM daily_portfolio_returns p
    JOIN daily_benchmark_returns b ON p.as_of_date = b.as_of_date
)
SELECT
    fund_id,
    benchmark_code,
    :start_date AS start_date,
    :end_date AS end_date,
    COUNT(excess_return) AS trading_days_count,
    
    -- 日均超額收益率 (%)
    ROUND(AVG(excess_return) * 100.0, 6) AS avg_daily_excess_return_pct,
    
    -- 日跟蹤誤差 (%)
    ROUND(COALESCE(STDDEV_SAMP(excess_return), 0.0) * 100.0, 6) AS daily_tracking_error_pct,
    
    -- 年化跟蹤誤差 (依 252 交易日標準年化, %)
    ROUND(COALESCE(STDDEV_SAMP(excess_return), 0.0) * SQRT(252.0) * 100.0, 6) AS annualized_tracking_error_252_pct,
    
    -- 年化跟蹤誤差 (依 365 自然日年化, %)
    ROUND(COALESCE(STDDEV_SAMP(excess_return), 0.0) * SQRT(365.0) * 100.0, 6) AS annualized_tracking_error_365_pct
FROM excess_returns
GROUP BY fund_id, benchmark_code;