-- atomic_portfolio_dv01.sql
-- 基金組合基點價值 (DV01 / Dollar Value of a Basis Point)
-- 計算公式：
-- 1. 單券 DV01_i = Market_Value_i * Modified_Duration_i * 0.0001
-- 2. 組合總 DV01 = \sum (DV01_i)
-- 代表當收益率曲線平行移動 1 個基點 (0.01%) 時，基金組合總市值的預期變動金額 (HKD)

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
    -- 2. 關聯債券持倉與市場風險數據表，計算單券 DV01
    SELECT
        b.port_id AS fund_id,
        b.evaluate_date AS as_of_date,
        b.security_code,
        b.security_name,
        COALESCE(b.market_value, 0.0) AS market_value_hkd,
        COALESCE(b.duration, r.duration, 0.0) AS modified_duration,
        
        -- 單券 DV01 (HKD)
        CASE 
            WHEN COALESCE(b.duration, r.duration, 0.0) > 0 
            THEN COALESCE(b.market_value, 0.0) * COALESCE(b.duration, r.duration, 0.0) * 0.0001
            ELSE 0.0 
        END AS single_security_dv01,
        
        CASE 
            WHEN COALESCE(b.duration, r.duration, 0.0) > 0 THEN 1 
            ELSE 0 
        END AS is_valid_bond
    FROM fsi.balance_bond b
    LEFT JOIN fsi.mktdata_bond_risk r
           ON b.security_code = r.internal_id 
          AND b.evaluate_date = r.price_date
    WHERE b.port_id = :fid
      AND b.evaluate_date = :as_of_date
      AND b.market_value > 0
),
aggregated_dv01 AS (
    -- 3. 聚合計算基金組合總 DV01
    SELECT
        fund_id,
        as_of_date,
        COUNT(*) AS total_bond_holdings_count,
        
        -- 債券類資產總市值
        SUM(market_value_hkd) AS total_bond_mv,
        
        -- 有效久期債券市值
        SUM(CASE WHEN is_valid_bond = 1 THEN market_value_hkd ELSE 0.0 END) AS valid_duration_bond_mv,
        
        -- 組合總 DV01 (HKD)
        SUM(single_security_dv01) AS portfolio_dv01_hkd
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
    
    -- 1. 組合總 DV01 (HKD / 1 bp)
    ROUND(a.portfolio_dv01_hkd, 2) AS portfolio_dv01_hkd,
    
    -- 2. 每百萬資產淨值 DV01 (DV01 per HKD 1M NAV)
    ROUND(
        (a.portfolio_dv01_hkd / NULLIF(n.total_nav_hkd, 0.0)) * 1000000.0,
        2
    ) AS dv01_per_million_nav_hkd
FROM aggregated_dv01 a
JOIN nav_summary n 
  ON a.fund_id = n.fund_id 
 AND a.as_of_date = n.as_of_date;