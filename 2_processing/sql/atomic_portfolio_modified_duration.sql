-- atomic_portfolio_modified_duration.sql
-- 基金組合修正久期 (Modified Duration)
-- 計算公式：組合修正久期 = \sum (w_i * ModD_i)
-- 提供：1. 債券資產加權修正久期 (以固定收益資產總市值為分母)
--       2. 總組合加權修正久期 (以基金總資產淨值 NAV 為分母)

WITH portfolio_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之總資產與各持倉
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
    -- 2. 關聯債券分析指標數據表
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.security_name,
        p.market_value_hkd,
        p.total_portfolio_nav,
        b.modified_duration,
        b.macaulay_duration,
        b.ytm,
        CASE WHEN b.modified_duration IS NOT NULL AND b.modified_duration >= 0 THEN 1 ELSE 0 END AS is_valid_bond
    FROM portfolio_summary p
    LEFT JOIN fsi.bond_analytics b 
           ON p.security_code = b.security_code 
          AND p.as_of_date = b.as_of_date
),
aggregated_duration AS (
    -- 3. 聚合計算債券市值與加權久期分子
    SELECT
        fund_id,
        as_of_date,
        MAX(total_portfolio_nav) AS total_portfolio_nav,
        
        -- 債券類資產總市值
        SUM(CASE WHEN is_valid_bond = 1 THEN market_value_hkd ELSE 0.0 END) AS total_bond_mv,
        
        -- 久期加權分子 \sum (MV_i * ModD_i)
        SUM(CASE WHEN is_valid_bond = 1 THEN market_value_hkd * modified_duration ELSE 0.0 END) AS dur_weighted_mv_sum
    FROM bond_joined
    GROUP BY fund_id, as_of_date
)
SELECT
    fund_id,
    as_of_date,
    
    -- 資產規模與覆蓋率
    total_portfolio_nav,
    total_bond_mv,
    ROUND((total_bond_mv / NULLIF(total_portfolio_nav, 0.0)) * 100.0, 4) AS bond_weight_pct,
    
    -- 1. 債券資產加權修正久期 (Bond Portfolio Duration, 年)
    ROUND(
        dur_weighted_mv_sum / NULLIF(total_bond_mv, 0.0),
        4
    ) AS weighted_modified_duration_bond_only,
    
    -- 2. 基金總組合加權修正久期 (Total Portfolio Duration, 年)
    ROUND(
        dur_weighted_mv_sum / NULLIF(total_portfolio_nav, 0.0),
        4
    ) AS weighted_modified_duration_total_nav
FROM aggregated_duration;