-- absolute_return.sql
-- 絕對收益 (億元) 計算
-- 絕對收益 = 持有期內實現收益 + 市值變動(浮動盈虧) + 利息/分紅收益
-- 維度： 基金

WITH pnl_summary AS (
    SELECT
        port_id AS fund_id,
        COALESCE(SUM(realized_return), 0.0) AS total_realized_pnl,
        COALESCE(SUM(mtm_delta), 0.0) AS total_unrealized_pnl,
        COALESCE(SUM(interest_income), 0.0) AS total_dividend_income
    FROM fsi.transact_portfolio_pnl
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
    GROUP BY port_id
)
SELECT
    fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    
    -- 1. 各項盈虧與收益 (金額單位：元)
    total_realized_pnl,
    total_unrealized_pnl,
    total_dividend_income,
    (total_realized_pnl + total_unrealized_pnl + total_dividend_income) AS total_absolute_return,
    
    -- 2. 各項盈虧與收益 (金額單位：億元，保留 6 位小數)
    ROUND((total_realized_pnl / 100000000.0), 6) AS realized_pnl_yi,
    ROUND((total_unrealized_pnl / 100000000.0), 6) AS unrealized_pnl_yi,
    ROUND((total_dividend_income / 100000000.0), 6) AS dividend_income_yi,
    ROUND(((total_realized_pnl + total_unrealized_pnl + total_dividend_income) / 100000000.0), 6) AS absolute_return_yi
FROM pnl_summary;