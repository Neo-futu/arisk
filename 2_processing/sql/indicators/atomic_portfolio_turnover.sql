-- atomic_stock_turnover.sql
-- 基金股票年換手率 (Annualized Stock Turnover Rate, %)
-- 計算公式：
-- 1. 股票買入總額 (Total Stock Purchases) = SUM(Stock Buy Transaction Amounts)
-- 2. 股票賣出總額 (Total Stock Sales) = SUM(Stock Sell Transaction Amounts)
-- 3. 股票換手金額 = MIN(股票買入總額, 股票賣出總額)
-- 4. 期間股票換手率 (%) = (股票換手金額 / 期間平均基金淨值 Avg NAV) * 100%
-- 5. 年化股票換手率 (%) = 期間股票換手率 (%) * (365 / 期間天數)

WITH period_config AS (
    -- 1. 計算統計區間天數
    SELECT
        :fid AS fund_id,
        CAST(:start_date AS DATE) AS start_date,
        CAST(:end_date AS DATE) AS end_date,
        (CAST(:end_date AS DATE) - CAST(:start_date AS DATE) + 1) AS days_in_period
),
stock_trade_summary AS (
    -- 2. 僅從股票交易明細表彙整買入與賣出總金額 (HKD)
    SELECT
        port_id AS fund_id,
        SUM(
            CASE 
                WHEN UPPER(COALESCE(direction, buy_sell, '')) IN ('BUY', 'B', 'P', 'PURCHASE') 
                THEN ABS(COALESCE(transact_amount, settlement_amount, amount, 0.0)) 
                ELSE 0.0 
            END
        ) AS total_stock_purchases_hkd,
        SUM(
            CASE 
                WHEN UPPER(COALESCE(direction, buy_sell, '')) IN ('SELL', 'S', 'REDEMPTION') 
                THEN ABS(COALESCE(transact_amount, settlement_amount, amount, 0.0)) 
                ELSE 0.0 
            END
        ) AS total_stock_sales_hkd
    FROM fsi.transact_stock
    WHERE port_id = :fid 
      AND trade_date BETWEEN :start_date AND :end_date
    GROUP BY port_id
),
nav_summary AS (
    -- 3. 計算統計期間內的每日平均基金淨值 (Avg NAV)
    SELECT
        port_id AS fund_id,
        AVG(COALESCE(net_asset, 0.0)) AS avg_net_asset_value_hkd,
        COUNT(DISTINCT evaluate_date) AS nav_days_count
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
    GROUP BY port_id
),
turnover_calculated AS (
    -- 4. 整合並計算股票換手率核心指標
    SELECT
        cfg.fund_id,
        cfg.start_date,
        cfg.end_date,
        cfg.days_in_period,
        COALESCE(n.avg_net_asset_value_hkd, 0.0) AS avg_net_asset_value_hkd,
        COALESCE(st.total_stock_purchases_hkd, 0.0) AS total_stock_purchases_hkd,
        COALESCE(st.total_stock_sales_hkd, 0.0) AS total_stock_sales_hkd,
        LEAST(
            COALESCE(st.total_stock_purchases_hkd, 0.0), 
            COALESCE(st.total_stock_sales_hkd, 0.0)
        ) AS stock_turnover_base_amount_hkd
    FROM period_config cfg
    LEFT JOIN stock_trade_summary st ON cfg.fund_id = st.fund_id
    LEFT JOIN nav_summary n ON cfg.fund_id = n.fund_id
)
SELECT
    fund_id,
    start_date,
    end_date,
    days_in_period,
    
    ROUND(avg_net_asset_value_hkd, 2) AS avg_net_asset_value_hkd,
    ROUND(total_stock_purchases_hkd, 2) AS total_stock_purchases_hkd,
    ROUND(total_stock_sales_hkd, 2) AS total_stock_sales_hkd,
    ROUND(stock_turnover_base_amount_hkd, 2) AS stock_turnover_base_amount_hkd,
    
    -- 1. 期間股票未年化換手率 (%)
    ROUND(
        (stock_turnover_base_amount_hkd / NULLIF(avg_net_asset_value_hkd, 0.0)) * 100.0,
        4
    ) AS period_stock_turnover_rate_pct,
    
    -- 2. 股票年化換手率 (%) (Annualized Stock Turnover Rate)
    ROUND(
        ((stock_turnover_base_amount_hkd / NULLIF(avg_net_asset_value_hkd, 0.0)) * 100.0) * (365.0 / NULLIF(days_in_period, 0)),
        4
    ) AS annualized_stock_turnover_rate_pct
FROM turnover_calculated;