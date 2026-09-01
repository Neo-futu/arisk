-- atomic_tracking_error.sql
-- 原子指標：基金組合跟蹤誤差 (Tracking Error, TE)
-- 說明：
-- 1. 組合淨值來源：fsi.balance_portfolio_nav (port_id, evaluate_date, net_asset)
-- 2. 基準收益來源：fsi.benchmark_daily_returns (benchmark_code, as_of_date, return_rate)
-- 3. 計算公式：
--    - 日超額收益率 (Excess Return) = R_p,t - R_m,t
--    - 年化跟蹤誤差 (Annualized TE) = STDDEV_SAMP(Excess Return) * SQRT(252) * 100%

WITH raw_portfolio_nav AS (
    -- 1. 取得組合每日淨值（擴展前一日數據以計算 start_date 當日收益率）
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        net_asset,
        LAG(net_asset) OVER (PARTITION BY port_id ORDER BY evaluate_date) AS prev_net_asset
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date >= (CAST(:start_date AS DATE) - INTERVAL '7 day') -- 涵蓋休市日，確保算得出首日收益
      AND evaluate_date <= CAST(:end_date AS DATE)
),
daily_portfolio_returns AS (
    -- 2. 計算組合每日收益率 R_p
    SELECT
        fund_id,
        as_of_date,
        (net_asset - prev_net_asset) / NULLIF(prev_net_asset, 0.0) AS r_p
    FROM raw_portfolio_nav
    WHERE as_of_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
      AND prev_net_asset IS NOT NULL
      AND prev_net_asset > 0
),
daily_benchmark_returns AS (
    -- 3. 取得基準每日收益率 R_m
    SELECT
        benchmark_code,
        as_of_date,
        COALESCE(return_rate, 0.0) AS r_m
    FROM fsi.benchmark_daily_returns
    WHERE benchmark_code = :bm_code
      AND as_of_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
),
excess_returns AS (
    -- 4. 交易日對齊並計算每日超額收益率
    SELECT
        p.fund_id,
        b.benchmark_code,
        p.as_of_date,
        p.r_p,
        b.r_m,
        (p.r_p - b.r_m) AS excess_return
    FROM daily_portfolio_returns p
    INNER JOIN daily_benchmark_returns b ON p.as_of_date = b.as_of_date
)
SELECT
    fund_id,
    benchmark_code,
    CAST(:start_date AS DATE) AS start_date,
    CAST(:end_date AS DATE) AS end_date,
    COUNT(excess_return) AS trading_days_count,
    
    -- 日均超額收益率 (%)
    ROUND(AVG(excess_return) * 100.0, 6) AS avg_daily_excess_return_pct,
    
    -- 日跟蹤誤差 (%)
    CASE 
        WHEN COUNT(excess_return) >= 2 THEN ROUND(STDDEV_SAMP(excess_return) * 100.0, 6)
        ELSE 0.0 
    END AS daily_tracking_error_pct,
    
    -- 年化跟蹤誤差 (依 252 交易日標準年化, %)
    CASE 
        WHEN COUNT(excess_return) >= 2 THEN ROUND(STDDEV_SAMP(excess_return) * SQRT(252.0) * 100.0, 6)
        ELSE 0.0 
    END AS annualized_tracking_error_252_pct,
    
    -- 年化跟蹤誤差 (依 365 自然日年化, %)
    CASE 
        WHEN COUNT(excess_return) >= 2 THEN ROUND(STDDEV_SAMP(excess_return) * SQRT(365.0) * 100.0, 6)
        ELSE 0.0 
    END AS annualized_tracking_error_365_pct

FROM excess_returns
GROUP BY fund_id, benchmark_code;