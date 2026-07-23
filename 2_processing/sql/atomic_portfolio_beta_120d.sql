-- atomic_portfolio_beta_120d.sql
-- 基金組合 Beta (近 120 個交易日)
-- 計算公式：Beta = Cov(R_p, R_m) / Var(R_m)
-- 採用 PostgreSQL 統計內建函數 COVAR_SAMP / VAR_SAMP 以及 REGR_SLOPE 線性迴歸斜率進行交叉驗證

WITH raw_portfolio_daily AS (
    -- 1. 計算基金組合每日收益率 R_p
    SELECT
        as_of_date,
        fund_id,
        SUM(COALESCE(market_value_hkd, 0.0)) AS total_mv,
        SUM(COALESCE(pnl_hkd, 0.0)) AS total_pnl
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date <= :as_of_date
    GROUP BY as_of_date, fund_id
),
daily_portfolio_returns AS (
    SELECT
        as_of_date,
        fund_id,
        CASE WHEN total_mv > 0 THEN total_pnl / total_mv ELSE 0.0 END AS r_p
    FROM raw_portfolio_daily
),
daily_benchmark_returns AS (
    -- 2. 獲取基準指數每日收益率 R_m
    SELECT
        as_of_date,
        benchmark_code,
        return_rate AS r_m
    FROM fsi.benchmark_daily_returns
    WHERE benchmark_code = :bm_code
      AND as_of_date <= :as_of_date
),
aligned_120d_returns AS (
    -- 3. 取基準日 (:as_of_date) 前最新 120 個交易日之對齊數據
    SELECT
        p.fund_id,
        b.benchmark_code,
        p.as_of_date,
        p.r_p,
        b.r_m
    FROM daily_portfolio_returns p
    JOIN daily_benchmark_returns b ON p.as_of_date = b.as_of_date
    ORDER BY p.as_of_date DESC
    LIMIT 120
)
SELECT
    fund_id,
    benchmark_code,
    MIN(as_of_date) AS window_start_date,
    MAX(as_of_date) AS window_end_date,
    COUNT(*) AS trading_days_count,
    
    -- 統計基礎量
    ROUND(AVG(r_p) * 100.0, 6) AS avg_portfolio_return_pct,
    ROUND(AVG(r_m) * 100.0, 6) AS avg_benchmark_return_pct,
    ROUND(VAR_SAMP(r_m), 8) AS var_benchmark,
    ROUND(COVAR_SAMP(r_p, r_m), 8) AS cov_portfolio_benchmark,
    
    -- 1. 依據公式 Cov(R_p, R_m) / Var(R_m) 計算之 Beta
    ROUND(
        COVAR_SAMP(r_p, r_m) / NULLIF(VAR_SAMP(r_m), 0.0),
        6
    ) AS beta_120d,
    
    -- 2. 依據最小二乘法迴歸斜率 REGR_SLOPE(y, x) 計算之 Beta (驗證用)
    ROUND(
        REGR_SLOPE(r_p, r_m),
        6
    ) AS beta_regr_slope_120d,
    
    -- 判定係數 R^2 (R-Squared)
    ROUND(
        REGR_R2(r_p, r_m),
        6
    ) AS r_squared_120d
FROM aligned_120d_returns
GROUP BY fund_id, benchmark_code;