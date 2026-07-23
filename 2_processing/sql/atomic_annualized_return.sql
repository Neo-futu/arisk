-- atomic_annualized_return.sql
-- 年化收益率 (%)
-- 計算公式：年化收益率 = [(1 + 區間累積收益率) ^ (365 / 區間自然日天數) - 1] * 100%
-- 維度： 基金

WITH daily_returns AS (
    SELECT
        evaluate_date AS as_of_date,
        port_id AS fund_id,
        COALESCE(day_return, 0.0) AS r_p
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
cumulative_calc AS (
    SELECT
        fund_id,
        -- 區間累積收益率 R_cum = \prod (1 + r_t) - 1
        EXP(SUM(LN(1.0 + r_p))) - 1.0 AS cumulative_return,
        COUNT(DISTINCT as_of_date) AS trading_days
    FROM daily_returns
    GROUP BY fund_id
)
SELECT
    fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    
    -- 天數統計
    (:end_date - :start_date + 1) AS natural_days,
    trading_days,
    
    -- 區間累積收益率 (%)
    ROUND(cumulative_return * 100.0, 6) AS cumulative_return_pct,
    
    -- 年化收益率 (依 365 自然日年化, %)
    ROUND(
        (POWER(1.0 + cumulative_return, 365.0 / NULLIF((:end_date - :start_date + 1), 0)) - 1.0) * 100.0,
        6
    ) AS annualized_return_365_pct,

    -- 年化收益率 (依 252 交易日年化, %)
    ROUND(
        (POWER(1.0 + cumulative_return, 252.0 / NULLIF(trading_days, 0)) - 1.0) * 100.0,
        6
    ) AS annualized_return_252_pct
FROM cumulative_calc;