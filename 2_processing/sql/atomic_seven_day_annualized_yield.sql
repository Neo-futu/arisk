-- atomic_seven_day_annualized_yield.sql
-- 原子指標：七日年化收益率（貨幣 %）
-- 說明：
-- 1. 淨值來源：fsi.balance_portfolio_nav (port_id, evaluate_date, net_asset, daily_pnl)
-- 2. 計算公式：取基準日及前 6 個有效估值日（共 7 日）之平均單日收益率，乘以 365 進行年化。

WITH raw_nav AS (
    -- 1. 取出基準日及之前的歷史估值紀錄，並計算當日收益率
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS net_asset,
        -- 若表內有 daily_pnl 則優先使用，否則使用 LAG 淨值計算
        COALESCE(daily_pnl, net_asset - LAG(net_asset) OVER (PARTITION BY port_id ORDER BY evaluate_date ASC)) AS daily_pnl_val,
        LAG(net_asset) OVER (PARTITION BY port_id ORDER BY evaluate_date ASC) AS prev_net_asset
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date <= :as_of_date
),
daily_returns AS (
    -- 2. 計算單日收益率 (daily_return)，並按日期倒序排定序號
    SELECT
        fund_id,
        as_of_date,
        net_asset,
        CASE 
            WHEN prev_net_asset > 0.0 THEN daily_pnl_val / prev_net_asset
            ELSE 0.0
        END AS daily_return,
        ROW_NUMBER() OVER (PARTITION BY fund_id ORDER BY as_of_date DESC) AS rn
    FROM raw_nav
    WHERE prev_net_asset IS NOT NULL AND prev_net_asset > 0.0
),
seven_day_window AS (
    -- 3. 精確鎖定最近 7 個估值日 (rn <= 7)
    SELECT
        fund_id,
        as_of_date,
        daily_return
    FROM daily_returns
    WHERE rn <= 7
)
SELECT
    :fid AS fund_id,
    MAX(as_of_date) AS as_of_date,
    COUNT(*) AS sample_days,
    
    -- 七日年化收益率 (%) = (7 日日均收益率) * 365 * 100
    CASE
        WHEN COUNT(*) < 7 THEN NULL
        ELSE ROUND(AVG(daily_return) * 365.0 * 100.0, 6)
    END AS seven_day_annualized_yield_pct

FROM seven_day_window
GROUP BY fund_id;

