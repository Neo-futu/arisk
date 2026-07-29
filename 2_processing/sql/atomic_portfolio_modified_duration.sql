-- atomic_portfolio_modified_duration.sql
-- 基金組合修正久期 (Modified Duration)
-- 計算公式：組合修正久期 = \sum (w_i * ModD_i)
-- 提供：1. 債券資產加權修正久期 (以固定收益資產總市值為分母)
--       2. 總組合加權修正久期 (以基金總資產淨值 NAV 為分母)

WITH nav_summary AS (
    -- 1. 取得指定基準日之基金總淨值 (來自 fsi.balance_portfolio_nav)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS total_nav_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
bond_joined AS (
    -- 2. 關聯債券持倉與市場風險數據表
    SELECT
        b.port_id AS fund_id,
        b.evaluate_date AS as_of_date,
        b.security_code,
        b.security_name,
        COALESCE(b.market_value, 0.0) AS market_value_hkd,
        COALESCE(b.modified_duration, r.modified_duration, 0.0) AS modified_duration,
        
        -- 判斷是否為有效久期債券
        CASE 
            WHEN COALESCE(b.modified_duration, r.modified_duration, 0.0) > 0 THEN 1 
            ELSE 0 
        END AS is_valid_bond
    FROM fsi.balance_bond b
    LEFT JOIN fsi.mktdata_bond_risk r
           ON b.security_code = r.security_code 
          AND b.evaluate_date = r.price_date
    WHERE b.port_id = :fid
      AND b.evaluate_date = :as_of_date
      AND b.market_value > 0
),
aggregated_duration AS (
    -- 3. 聚合計算債券市值與久期加權分子
    SELECT
        fund_id,
        as_of_date,
        COUNT(*) AS total_bond_holdings_count,
        
        -- 債券類資產總市值
        SUM(market_value_hkd) AS total_bond_mv,
        
        -- 有效久期債券總市值
        SUM(CASE WHEN is_valid_bond = 1 THEN market_value_hkd ELSE 0.0 END) AS valid_duration_bond_mv,
        
        -- 久期加權分子 \sum (MV_i * ModD_i)
        SUM(CASE WHEN is_valid_bond = 1 THEN market_value_hkd * modified_duration ELSE 0.0 END) AS dur_weighted_mv_sum
    FROM bond_joined
    GROUP BY fund_id, as_of_date
)
SELECT
    a.fund_id,
    a.as_of_date,
    ROUND(n.total_nav_hkd, 2) AS total_nav_hkd,
    a.total_bond_holdings_count,
    ROUND(a.total_bond_mv, 2) AS total_bond_market_value_hkd,
    
    -- 債券佔淨值比例 (%)
    ROUND((a.total_bond_mv / NULLIF(n.total_nav_hkd, 0.0)) * 100.0, 4) AS bond_exposure_pct,
    
    -- 1. 債券資產加權修正久期 (Bond Portfolio Duration, 年)
    ROUND(
        a.dur_weighted_mv_sum / NULLIF(a.valid_duration_bond_mv, 0.0),
        4
    ) AS weighted_modified_duration_bond_only,
    
    -- 2. 基金總組合加權修正久期 (Total Portfolio Duration, 年)
    ROUND(
        a.dur_weighted_mv_sum / NULLIF(n.total_nav_hkd, 0.0),
        4
    ) AS weighted_modified_duration_total_nav
FROM aggregated_duration a
JOIN nav_summary n 
  ON a.fund_id = n.fund_id 
 AND a.as_of_date = n.as_of_date;