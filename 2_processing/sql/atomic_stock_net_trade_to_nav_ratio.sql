-- atomic_stock_net_trade_to_nav_ratio.sql
-- 淨交易佔淨值比例 (%) (Net Trade Amount to Average NAV Ratio, %)
-- 計算公式：
-- 股票淨交易金額 (Net Trade Amount) = 區間股票總買入金額 (Buy Amount) - 區間股票總賣出金額 (Sell Amount)
-- 淨交易佔淨值比例 (%) = (區間單個股票淨買入/賣出金額 / 區間日均基金淨資產 Avg NAV) * 100%

WITH period_config AS (
    -- 1. 設定統計區間與參數
    SELECT
        :fid AS fund_id,
        :security_code AS security_code,
        CAST(:start_date AS DATE) AS start_date,
        CAST(:end_date AS DATE) AS end_date
),
nav_summary AS (
    -- 2. 計算統計期間內的日均基金淨資產 (Avg NAV)
    SELECT
        fund_id,
        AVG(COALESCE(net_asset_value_hkd, 0.0)) AS avg_net_asset_value_hkd
    FROM fsi.fund_nav
    WHERE fund_id = :fid
      AND nav_date BETWEEN :start_date AND :end_date
    GROUP BY fund_id
),
trade_summary AS (
    -- 3. 彙整指定股票在統計期間內的總買入金額、總賣出金額與淨交易金額
    SELECT
        fund_id,
        security_code,
        SUM(CASE WHEN LOWER(transaction_type) IN ('buy', 'p', 'subscription') THEN ABS(COALESCE(amount_hkd, 0.0)) ELSE 0.0 END) AS total_buy_amount_hkd,
        SUM(CASE WHEN LOWER(transaction_type) IN ('sell', 's', 'redemption') THEN ABS(COALESCE(amount_hkd, 0.0)) ELSE 0.0 END) AS total_sell_amount_hkd
    FROM fsi.transactions
    WHERE fund_id = :fid
      AND security_code = :security_code
      AND trade_date BETWEEN :start_date AND :end_date
    GROUP BY fund_id, security_code
),
calculated_ratios AS (
    -- 4. 整合日均 NAV 與交易金額計算淨交易金額與占比
    SELECT
        cfg.fund_id,
        cfg.security_code,
        cfg.start_date,
        cfg.end_date,
        COALESCE(n.avg_net_asset_value_hkd, 0.0) AS avg_net_asset_value_hkd,
        COALESCE(t.total_buy_amount_hkd, 0.0) AS total_buy_amount_hkd,
        COALESCE(t.total_sell_amount_hkd, 0.0) AS total_sell_amount_hkd,
        (COALESCE(t.total_buy_amount_hkd, 0.0) - COALESCE(t.total_sell_amount_hkd, 0.0)) AS net_trade_amount_hkd
    FROM period_config cfg
    LEFT JOIN nav_summary n ON cfg.fund_id = n.fund_id
    LEFT JOIN trade_summary t ON cfg.fund_id = t.fund_id AND cfg.security_code = t.security_code
)
SELECT
    fund_id,
    security_code,
    start_date,
    end_date,
    ROUND(avg_net_asset_value_hkd, 2) AS avg_net_asset_value_hkd,
    ROUND(total_buy_amount_hkd, 2) AS total_buy_amount_hkd,
    ROUND(total_sell_amount_hkd, 2) AS total_sell_amount_hkd,
    ROUND(net_trade_amount_hkd, 2) AS net_trade_amount_hkd,
    
    -- 淨交易佔淨值比例 (%)
    ROUND(
        (net_trade_amount_hkd / NULLIF(avg_net_asset_value_hkd, 0.0)) * 100.0,
        4
    ) AS net_trade_to_nav_ratio_pct
FROM calculated_ratios;