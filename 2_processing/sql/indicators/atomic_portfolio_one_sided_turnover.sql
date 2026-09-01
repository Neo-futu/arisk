-- atomic_portfolio_one_sided_turnover.sql
-- 基金組合單邊年換手率 (Annualized One-Sided Portfolio Turnover Rate, %)
-- 計算公式：
-- 單邊換手金額 = (買入總額 Total Purchases + 賣出總額 Total Sales) / 2
-- 期間單邊換手率 (%) = (單邊換手金額 / 期間平均基金淨值 Avg NAV) * 100%
-- 單邊年換手率 (%) = 期間單邊換手率 (%) * (365 / 期間天數)

WITH period_config AS (
    -- 1. 計算統計區間天數
    SELECT
        :fid AS fund_id,
        CAST(:start_date AS DATE) AS start_date,
        CAST(:end_date AS DATE) AS end_date,
        (CAST(:end_date AS DATE) - CAST(:start_date AS DATE) + 1) AS days_in_period
),
trade_summary AS (
    -- 2. 從股票與債券交易明細表彙整買入與賣出總金額 (HKD)
    SELECT
        port_id AS fund_id,
        SUM(
            CASE 
                WHEN UPPER(COALESCE(direction, buy_sell, '')) IN ('BUY', 'B', 'P', 'PURCHASE') 
                THEN ABS(COALESCE(transact_amount, settlement_amount, amount, 0.0)) 
                ELSE 0.0 
            END
        ) AS total_purchases_hkd,
        SUM(
            CASE 
                WHEN UPPER(COALESCE(direction, buy_sell, '')) IN ('SELL', 'S', 'REDEMPTION') 
                THEN ABS(COALESCE(transact_amount, settlement_amount, amount, 0.0)) 
                ELSE 0.0 
            END
        ) AS total_sales_hkd
    FROM (
        -- 讀取股票交易表
        SELECT port_id, trade_date, direction, buy_sell, transact_amount, settlement_amount, amount 
        FROM fsi.transact_stock 
        WHERE port_id = :fid AND trade_date BETWEEN :start_date AND :end_date
        
        UNION ALL
        
        -- 讀取債券交易表
        SELECT port_id, trade_date, direction, buy_sell, transact_amount, settlement_amount, amount 
        FROM fsi.transact_bond 
        WHERE port_id = :fid AND trade_date BETWEEN :start_date AND :end_date
    ) sub_trades
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
    -- 4. 整合並計算單邊換手金額
    SELECT
        cfg.fund_id,
        cfg.start_date,
        cfg.end_date,
        cfg.days_in_period,
        COALESCE(n.avg_net_asset_value_hkd, 0.0) AS avg_net_asset_value_hkd,
        COALESCE(t.total_purchases_hkd, 0.0) AS total_purchases_hkd,
        COALESCE(t.total_sales_hkd, 0.0) AS total_sales_hkd,
        (COALESCE(t.total_purchases_hkd, 0.0) + COALESCE(t.total_sales_hkd, 0.0)) / 2.0 AS one_sided_turnover_amount_hkd
    FROM period_config cfg
    LEFT JOIN trade_summary t ON cfg.fund_id = t.fund_id
    LEFT JOIN nav_summary n ON cfg.fund_id = n.fund_id
)
SELECT
    fund_id,
    start_date,
    end_date,
    days_in_period,
    
    ROUND(avg_net_asset_value_hkd, 2) AS avg_net_asset_value_hkd,
    ROUND(total_purchases_hkd, 2) AS total_purchases_hkd,
    ROUND(total_sales_hkd, 2) AS total_sales_hkd,
    ROUND(one_sided_turnover_amount_hkd, 2) AS one_sided_turnover_amount_hkd,
    
    -- 1. 期間單邊換手率 (%)
    ROUND(
        (one_sided_turnover_amount_hkd / NULLIF(avg_net_asset_value_hkd, 0.0)) * 100.0,
        4
    ) AS period_one_sided_turnover_rate_pct,
    
    -- 2. 單邊年換手率 (%) (Annualized One-Sided Portfolio Turnover Rate)
    ROUND(
        ((one_sided_turnover_amount_hkd / NULLIF(avg_net_asset_value_hkd, 0.0)) * 100.0) * (365.0 / NULLIF(days_in_period, 0)),
        4
    ) AS annualized_one_sided_turnover_rate_pct
FROM turnover_calculated;