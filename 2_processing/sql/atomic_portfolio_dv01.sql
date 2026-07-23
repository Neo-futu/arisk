-- atomic_portfolio_dv01.sql
-- 基金組合基點價值 (DV01 / Dollar Value of a Basis Point)
-- 計算公式：
-- 1. 單券 DV01_i = Market_Value_i * Modified_Duration_i * 0.0001
-- 2. 組合總 DV01 = \sum (DV01_i)
-- 代表當收益率曲線平行移動 1 個基點 (0.01%) 時，基金組合總市值的預期變動金額 (HKD)

WITH portfolio_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之持倉
    SELECT
        fund_id,
        as_of_date,
        security_code,
        security_name,
        COALESCE(market_value_hkd, 0.0) AS market_value_hkd,
        SUM(COALESCE(market_value_hkd, 0.0)) OVER (PARTITION BY fund_id) AS total_portfolio_nav
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
      AND market_value_hkd > 0
),
bond_joined AS (
    -- 2. 關聯債券分析指標數據表，計算單券 DV01
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.security_name,
        p.market_value_hkd,
        p.total_portfolio_nav,
        b.modified_duration,
        -- 單券 DV01 (HKD)
        CASE 
            WHEN b.modified_duration IS NOT NULL AND b.modified_duration >= 0 
            THEN p.market_value_hkd * b.modified_duration * 0.0001
            ELSE 0.0 
        END AS single_security_dv01,
        CASE WHEN b.modified_duration IS NOT NULL AND b.modified_duration >= 0 THEN 1 ELSE 0 END AS is_valid_bond
    FROM portfolio_summary p
    LEFT JOIN fsi.bond_analytics b 
           ON p.security_code = b.security_code 
          AND p.as_of_date = b.as_of_date
),
aggregated_dv01 AS (
    -- 3. 聚合計算基金組合總 DV01
    SELECT
        fund_id,
        as_of_date,
        MAX(total_portfolio_nav) AS total_portfolio_nav,
        
        -- 債券類資產總市值
        SUM(CASE WHEN is_valid_bond = 1 THEN market_value_hkd ELSE 0.0 END) AS total_bond_mv,
        
        -- 組合總 DV01 (HKD)
        SUM(single_security_dv01) AS portfolio_dv01_hkd
    FROM bond_joined
    GROUP BY fund_id, as_of_date
)
SELECT
    fund_id,
    as_of_date,
    
    -- 資產規模與債券覆蓋率
    total_portfolio_nav,
    total_bond_mv,
    ROUND((total_bond_mv / NULLIF(total_portfolio_nav, 0.0)) * 100.0, 4) AS bond_weight_pct,
    
    -- 1. 組合總 DV01 (HKD / 1 bp)
    ROUND(portfolio_dv01_hkd, 2) AS portfolio_dv01_hkd,
    
    -- 2. 每百萬資產淨值 DV01 (DV01 per HKD 1M NAV)
    ROUND(
        (portfolio_dv01_hkd / NULLIF(total_portfolio_nav, 0.0)) * 1,000,000.0,
        2
    ) AS dv01_per_million_nav_hkd
FROM aggregated_dv01;