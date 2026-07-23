-- atomic_portfolio_turnover.sql
-- 基金組合年換手率 (Annualized Portfolio Turnover Rate, %)
-- 計算公式 (SEC / UCITS 標準定義)：
-- 1. 買入總額 (Total Purchases) = SUM(Buy Transaction Amounts)
-- 2. 賣出總額 (Total Sales) = SUM(Sell Transaction Amounts)
-- 3. 換手金額 = MIN(買入總額, 賣出總額)
-- 4. 期間換手率 (%) = (換手金額 / 期間平均基金淨值 Avg NAV) * 100%
-- 5. 年化換手率 (%) = 期間換手率 (%) * (365 / 期間天數)

WITH period_config AS (
    -- 1. 計算統計區間天數
    SELECT
        :fid AS fund_id,
        CAST(:start_date AS DATE) AS start_date,
        CAST(:end_date AS DATE) AS end_date,
        (CAST(:end_date AS DATE) - CAST(:start_date AS DATE) + 1) AS days_in_period
),
trade_summary AS (
    -- 2. 彙整統計期間內的買入與賣出交易總金額 (HKD)
    SELECT
        fund_id,
        SUM(CASE WHEN LOWER(transaction_type) IN ('buy', 'subscription', 'p') THEN ABS(COALESCE(amount_hkd, 0.0)) ELSE 0.0 END) AS total_purchases_hkd,
        SUM(CASE WHEN LOWER(transaction_type) IN ('sell', 'redemption', 's') THEN ABS(COALESCE(amount_hkd, 0.0)) ELSE 0.0 END) AS total_sales_hkd
    FROM fsi.transactions
    WHERE fund_id = :fid
      AND trade_date BETWEEN :start_date AND :end_date
    GROUP BY fund_id
),
nav_summary AS (
    -- 3. 計算統計期間內的每日平均基金淨值 (Avg NAV)
    SELECT
        fund_id,
        AVG(COALESCE(net_asset_value_hkd, 0.0)) AS avg_net_asset_value_hkd,
        COUNT(DISTINCT nav_date) AS nav_days_count
    FROM fsi.fund_nav
    WHERE fund_id = :fid
      AND nav_date BETWEEN :start_date AND :end_date
    GROUP BY fund_id
),
turnover_calculated AS (
    -- 4. 整合並計算換手率核心指標
    SELECT
        cfg.fund_id,
        cfg.start_date,
        cfg.end_date,
        cfg.days_in_period,
        COALESCE(n.avg_net_asset_value_hkd, 0.0) AS avg_net_asset_value_hkd,
        COALESCE(t.total_purchases_hkd, 0.0) AS total_purchases_hkd,
        COALESCE(t.total_sales_hkd, 0.0) AS total_sales_hkd,
        LEAST(COALESCE(t.total_purchases_hkd, 0.0), COALESCE(t.total_sales_hkd, 0.0)) AS turnover_base_amount_hkd
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
    ROUND(turnover_base_amount_hkd, 2) AS turnover_base_amount_hkd,
    
    -- 1. 期間未年化換手率 (%)
    ROUND(
        (turnover_base_amount_hkd / NULLIF(avg_net_asset_value_hkd, 0.0)) * 100.0,
        4
    ) AS period_turnover_rate_pct,
    
    -- 2. 年化換手率 (%) (Annualized Portfolio Turnover Rate)
    ROUND(
        ((turnover_base_amount_hkd / NULLIF(avg_net_asset_value_hkd, 0.0)) * 100.0) * (365.0 / NULLIF(days_in_period, 0)),
        4
    ) AS annualized_turnover_rate_pct
FROM turnover_calculated;