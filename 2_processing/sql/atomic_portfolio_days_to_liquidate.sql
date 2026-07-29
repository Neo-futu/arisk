-- atomic_portfolio_days_to_liquidate.sql
-- 股票持倉變現天數 (Days to Liquidate Stock Positions)

WITH nav_summary AS (
    -- 1. 取得指定基準日之基金總淨值
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS total_nav_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
mktdata_adv AS (
    -- 2. 動態計算近 30 個交易日的日均成交量 (30D ADV)
    SELECT
        security_code,
        price_date,
        AVG(volume) OVER (
            PARTITION BY security_code 
            ORDER BY price_date 
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS adv_30d_shares
    FROM fsi.mktdata_quotes
    WHERE price_date <= :as_of_date
),
stock_position_liquidation AS (
    -- 3. 計算各股票持倉變現天數
    SELECT
        s.port_id AS fund_id,
        s.evaluate_date AS as_of_date,
        s.security_code,
        s.security_name,
        COALESCE(s.market_value, 0.0) AS market_value_hkd,
        ABS(COALESCE(s.quantity, 0.0)) AS position_quantity,
        COALESCE(q.adv_30d_shares, 0.0) AS adv_shares,
        
        CASE
            -- 有日均成交量數據 (ADV > 0)
            WHEN COALESCE(q.adv_30d_shares, 0.0) > 0 THEN
                CEIL(
                    ABS(COALESCE(s.quantity, 0.0)) / 
                    (q.adv_30d_shares * CAST(:adv_participation_rate AS NUMERIC))
                )
            -- 無公開交易量/數據缺失：預設天數 1 天
            ELSE 1.0
        END AS position_days_to_liquidate
    FROM fsi.balance_stock s
    LEFT JOIN mktdata_adv q
           ON s.security_code = q.security_code 
          AND s.evaluate_date = q.price_date
    WHERE s.port_id = :fid
      AND s.evaluate_date = :as_of_date
      AND s.market_value > 0
),
portfolio_stock_liquidation_summary AS (
    -- 4. 彙整股票持倉層面之變現指標
    SELECT
        spl.fund_id,
        spl.as_of_date,
        COUNT(*) AS total_stock_holdings_count,
        SUM(spl.market_value_hkd) AS total_stock_market_value_hkd,
        
        MAX(spl.position_days_to_liquidate) AS max_days_to_liquidate,
        SUM(spl.position_days_to_liquidate * spl.market_value_hkd) / NULLIF(SUM(spl.market_value_hkd), 0.0) AS weighted_avg_days_to_liquidate
    FROM stock_position_liquidation spl
    GROUP BY spl.fund_id, spl.as_of_date
)
SELECT
    p.fund_id,
    p.as_of_date,
    ROUND(n.total_nav_hkd, 2) AS total_nav_hkd,
    p.total_stock_holdings_count,
    ROUND(p.total_stock_market_value_hkd, 2) AS total_stock_market_value_hkd,
    ROUND((p.total_stock_market_value_hkd / NULLIF(n.total_nav_hkd, 0.0)) * 100.0, 4) AS stock_exposure_pct,
    CAST(:adv_participation_rate AS NUMERIC) AS adv_participation_rate_parameter,
    p.max_days_to_liquidate,
    ROUND(p.weighted_avg_days_to_liquidate, 2) AS weighted_avg_days_to_liquidate
FROM portfolio_stock_liquidation_summary p
JOIN nav_summary n 
  ON p.fund_id = n.fund_id 
 AND p.as_of_date = n.as_of_date;

 