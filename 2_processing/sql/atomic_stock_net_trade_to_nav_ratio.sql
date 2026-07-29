-- atomic_stock_net_trade_to_nav_ratio.sql
-- 原子指標：淨交易佔淨值比例 (%) (Net Trade Amount to Average NAV Ratio, %)
-- 說明：
-- 1. 淨值來源：fsi.balance_portfolio_nav (port_id, evaluate_date, net_asset)
-- 2. 交易來源：fsi.trade_order (port_id, trade_date, security_code, bs_flag, trade_amount)
-- 3. 計算公式：
--    - 股票淨交易金額 (Net Trade Amount) = 區間總買入金額 (Buy Amount) - 區間總賣出金額 (Sell Amount)
--    - 淨交易佔淨值比例 (%) = (區間股票淨交易金額 / 區間日均基金淨資產 Avg NAV) * 100%

WITH nav_summary AS (
    -- 1. 計算統計期間內的日均基金淨資產 (Avg NAV)
    SELECT
        port_id AS fund_id,
        AVG(COALESCE(net_asset, 0.0)) AS avg_nav
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
    GROUP BY port_id
),
base_trades AS (
    -- 2. 預處理交易紀錄，標準化標的代碼與買賣金額
    SELECT
        port_id AS fund_id,
        COALESCE(security_code, wind_code, ticker, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        UPPER(COALESCE(bs_flag, trade_direction, '')) AS norm_bs_flag,
        ABS(COALESCE(trade_amount, deal_amount, business_balance, 0.0)) AS norm_trade_amount
    FROM fsi.trade_order
    WHERE port_id = :fid
      AND trade_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
      AND (:security_code IS NULL OR security_code = :security_code)
),
trade_summary AS (
    -- 3. 彙整交易金額
    SELECT
        fund_id,
        security_code,
        MAX(security_name) AS security_name,
        
        -- 買入總金額
        SUM(
            CASE 
                WHEN norm_bs_flag IN ('B', 'BUY', '1') THEN norm_trade_amount
                ELSE 0.0 
            END
        ) AS total_buy_amount,
        
        -- 賣出總金額
        SUM(
            CASE 
                WHEN norm_bs_flag IN ('S', 'SELL', '2') THEN norm_trade_amount
                ELSE 0.0 
            END
        ) AS total_sell_amount
    FROM base_trades
    GROUP BY fund_id, security_code
),
calculated_ratios AS (
    -- 4. 整合日均 NAV 與交易金額，計算淨交易金額與占比
    SELECT
        t.fund_id,
        t.security_code,
        t.security_name,
        CAST(:start_date AS DATE) AS start_date,
        CAST(:end_date AS DATE) AS end_date,
        COALESCE(n.avg_nav, 0.0) AS avg_nav,
        t.total_buy_amount,
        t.total_sell_amount,
        (t.total_buy_amount - t.total_sell_amount) AS net_trade_amount
    FROM trade_summary t
    LEFT JOIN nav_summary n ON t.fund_id = n.fund_id
)
SELECT
    fund_id,
    security_code,
    security_name,
    start_date,
    end_date,
    ROUND(avg_nav, 2) AS avg_nav,
    ROUND(total_buy_amount, 2) AS total_buy_amount,
    ROUND(total_sell_amount, 2) AS total_sell_amount,
    ROUND(net_trade_amount, 2) AS net_trade_amount,
    
    -- 淨交易佔淨值比例 (%) = (淨交易金額 / 日均 NAV) * 100
    CASE
        WHEN avg_nav IS NULL OR avg_nav <= 0.0 THEN NULL
        ELSE ROUND((net_trade_amount / avg_nav) * 100.0, 6)
    END AS net_trade_to_nav_ratio_pct

FROM calculated_ratios
ORDER BY ABS(net_trade_amount) DESC;