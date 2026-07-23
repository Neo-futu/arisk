-- atomic_portfolio_days_to_liquidate.sql
-- 組合變現天數 (Days to Liquidate Portfolio)
-- 計算公式與邏輯：
-- 1. 單一持倉變現天數 = 持倉數量 (Quantity) / (市場日均成交量 ADV * 變現參與率限制 Rate_Limit)
--    - 若市場日均成交量 (ADV) 為 NULL 或 0（如未上市債券、場外 OTC 存款），可根據資產類別給予預設變現天數或劃分為 0/1 天。
-- 2. 組合全倉變現天數 (Portfolio Days to Liquidate) = MAX(各持倉變現天數)
-- 3. 組合加權變現天數 (Weighted Days to Liquidate) = SUM(單持倉變現天數 * 持倉權重)

WITH nav_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之基金淨值 Total NAV
    SELECT
        fund_id,
        nav_date AS as_of_date,
        COALESCE(net_asset_value_hkd, 0.0) AS total_nav_hkd
    FROM fsi.fund_nav
    WHERE fund_id = :fid
      AND nav_date = :as_of_date
),
position_liquidation AS (
    -- 2. 計算各持倉在設定的最大市場參與率 (如 20%) 下所需的變現天數
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.security_name,
        COALESCE(p.market_value_hkd, 0.0) AS market_value_hkd,
        ABS(COALESCE(p.quantity, 0.0)) AS position_quantity,
        COALESCE(m.adv_30d_shares, 0.0) AS adv_30d_shares,
        LOWER(COALESCE(p.asset_class, p.instrument_type, '')) AS asset_type,
        
        -- 計算單一持倉所需變現天數
        CASE
            -- 現金及極高流動性資產：0 天
            WHEN LOWER(COALESCE(p.asset_class, p.instrument_type, '')) IN ('cash', 'cash_equivalent', 'reverse_repo') THEN 0.0
            
            -- 具備市場日均成交量 (ADV) 的公開交易證券
            WHEN COALESCE(m.adv_30d_shares, 0.0) > 0 THEN 
                CEIL(
                    ABS(COALESCE(p.quantity, 0.0)) / 
                    (m.adv_30d_shares * :adv_participation_rate)
                )
                
            -- 無公開交易量 (OTC/債券/存款)：若無 ADV，退回保守預設天數 (例如固定 1 天或 5 天)
            ELSE 1.0
        END AS position_days_to_liquidate
    FROM fsi.positions p
    LEFT JOIN fsi.market_liquidity m 
           ON p.security_code = m.security_code 
          AND p.as_of_date = m.as_of_date
    WHERE p.fund_id = :fid
      AND p.as_of_date = :as_of_date
      AND p.market_value_hkd > 0
),
portfolio_liquidation_summary AS (
    -- 3. 彙整組合層面的變現天數指標
    SELECT
        pl.fund_id,
        pl.as_of_date,
        SUM(pl.market_value_hkd) AS total_position_market_value_hkd,
        
        -- 全倉變現天數：所有持倉中最大變現天數 (瓶頸持倉)
        MAX(pl.position_days_to_liquidate) AS max_days_to_liquidate_full_portfolio,
        
        -- 加權平均變現天數：按持倉市值加權
        SUM(pl.position_days_to_liquidate * pl.market_value_hkd) / NULLIF(SUM(pl.market_value_hkd), 0.0) AS weighted_avg_days_to_liquidate
    FROM position_liquidation pl
    GROUP BY pl.fund_id, pl.as_of_date
)
SELECT
    s.fund_id,
    s.as_of_date,
    ROUND(n.total_nav_hkd, 2) AS total_nav_hkd,
    ROUND(s.total_position_market_value_hkd, 2) AS total_position_market_value_hkd,
    :adv_participation_rate AS adv_participation_rate_parameter,
    
    -- 1. 變現全倉所需最大天數 (Max Days to Liquidate)
    s.max_days_to_liquidate_full_portfolio AS max_days_to_liquidate,
    
    -- 2. 組合市值加權平均變現天數 (Weighted Avg Days to Liquidate)
    ROUND(s.weighted_avg_days_to_liquidate, 2) AS weighted_avg_days_to_liquidate
FROM portfolio_liquidation_summary s
JOIN nav_summary n 
  ON s.fund_id = n.fund_id 
 AND s.as_of_date = n.as_of_date;
 