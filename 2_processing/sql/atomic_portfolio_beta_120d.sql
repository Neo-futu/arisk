-- atomic_portfolio_beta_120d.sql
-- 基金組合 Beta (近 120 個交易日)
-- 計算公式：Beta = Cov(R_p, R_m) / Var(R_m)
-- 採用 PostgreSQL 統計內建函數 COVAR_SAMP / VAR_SAMP 以及 REGR_SLOPE 線性迴歸斜率進行交叉驗證
-- 添加benchamrk-component表

WITH fund_bm_info AS (
    -- 1. 從 fsi.para_portfolio_benchmark 自動獲取基金對應的基准代碼
    SELECT 
        port_id AS fund_id, 
        benchmark_id AS benchmark_code
    FROM fsi.para_portfolio_benchmark
    WHERE port_id = :fid
      AND :as_of_date >= begin_date 
      AND :as_of_date <= COALESCE(end_date, '9999-12-31'::date)
    ORDER BY begin_date DESC
    LIMIT 1
),
daily_portfolio_returns AS (
    -- 2. 獲取基金組合每日收益率 R_p (來源：fsi.balance_portfolio_nav)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        day_return AS r_p
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date <= :as_of_date
      AND day_return IS NOT NULL
),
daily_benchmark_returns AS (
    -- 3. 獲取基準指數每日收益率 R_m
    SELECT
        b.benchmark_code,
        b.as_of_date,
        b.return_rate AS r_m
    FROM fsi.benchmark_daily_returns b
    INNER JOIN fund_bm_info m ON b.benchmark_code = m.benchmark_code
    WHERE b.as_of_date <= :as_of_date
      AND b.return_rate IS NOT NULL
),
aligned_120d_returns AS (
    -- 4. 取基準日前最新 120 個交易日之對齊數據
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