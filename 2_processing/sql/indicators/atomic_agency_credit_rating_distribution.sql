-- atomic_agency_credit_rating_distribution.sql
-- 基金組合按評級機構及信用等級劃分的持倉市值占比 (%)
--  維度： 債券

WITH portfolio_summary AS (
    -- 1. 從債券餘額表取得指定日期的持倉與總市值
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        security_code,
        security_name,
        COALESCE(total_market_value, 0.0) AS market_value_hkd,
        COALESCE(UPPER(TRIM(rating_agency::text)), 'DOMESTIC') AS rating_agency,
        '國內評級機構' AS rating_agency_name,
        COALESCE(TRIM(debt_rating), 'UNRATED') AS credit_rating,
        SUM(COALESCE(total_market_value, 0.0)) OVER (PARTITION BY port_id) AS total_portfolio_nav
    FROM fsi.balance_bond
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
      AND total_market_value > 0
),
agency_grouped AS (
    -- 2. 按評級機構與信用等級聚合持倉市值
    SELECT
        fund_id,
        as_of_date,
        rating_agency,
        rating_agency_name,
        credit_rating,
        SUM(market_value_hkd) AS rating_market_value_hkd,
        MAX(total_portfolio_nav) AS total_portfolio_nav
    FROM portfolio_summary
    GROUP BY fund_id, as_of_date, rating_agency, rating_agency_name, credit_rating
),
totals_calculated AS (
    -- 3. 計算組合債券總市值與各評級機構覆蓋總市值
    SELECT
        g.*,
        SUM(rating_market_value_hkd) OVER (PARTITION BY fund_id, as_of_date) AS total_bond_mv,
        SUM(rating_market_value_hkd) OVER (PARTITION BY fund_id, as_of_date, rating_agency) AS agency_total_bond_mv
    FROM agency_grouped g
)
SELECT
    fund_id,
    as_of_date,
    rating_agency,
    rating_agency_name,
    credit_rating,
    
    -- 持倉市值 (HKD)
    ROUND(rating_market_value_hkd, 2) AS rating_market_value_hkd,
    
    -- 1. 占基金總資產 NAV 比例 (%)
    ROUND(
        (rating_market_value_hkd / NULLIF(total_portfolio_nav, 0.0)) * 100.0,
        4
    ) AS nav_weight_pct,
    
    -- 2. 占債券總市值比例 (%)
    ROUND(
        (rating_market_value_hkd / NULLIF(total_bond_mv, 0.0)) * 100.0,
        4
    ) AS total_bond_weight_pct,
    
    -- 3. 占該評級機構覆蓋債券總市值比例 (%)
    ROUND(
        (rating_market_value_hkd / NULLIF(agency_total_bond_mv, 0.0)) * 100.0,
        4
    ) AS agency_share_pct,
    
    -- 評級機構排序
    CASE rating_agency
        WHEN 'DOMESTIC' THEN 1
        WHEN 'MOODYS'   THEN 2
        WHEN 'SP'       THEN 3
        WHEN 'FITCH'    THEN 4
        ELSE 99
    END AS agency_sort_order,
    
    -- 信用等級排序
    CASE UPPER(credit_rating)
        WHEN 'AAA'  THEN 1  WHEN 'Aaa'  THEN 1
        WHEN 'AA+'  THEN 2  WHEN 'Aa1'  THEN 2
        WHEN 'AA'   THEN 3  WHEN 'Aa2'  THEN 3
        WHEN 'AA-'  THEN 4  WHEN 'Aa3'  THEN 4
        WHEN 'A+'   THEN 5  WHEN 'A1'   THEN 5
        WHEN 'A'    THEN 6  WHEN 'A2'   THEN 6
        WHEN 'A-'   THEN 7  WHEN 'A3'   THEN 7
        WHEN 'BBB+' THEN 8  WHEN 'BAA1' THEN 8
        WHEN 'BBB'  THEN 9  WHEN 'BAA2' THEN 9
        WHEN 'BBB-' THEN 10 WHEN 'BAA3' THEN 10
        WHEN 'BB+'  THEN 11 WHEN 'BA1'  THEN 11
        WHEN 'BB'   THEN 12 WHEN 'BA2'  THEN 12
        WHEN 'BB-'  THEN 13 WHEN 'BA3'  THEN 13
        WHEN 'B+'   THEN 14 WHEN 'B1'   THEN 14
        WHEN 'B'    THEN 15 WHEN 'B2'   THEN 15
        WHEN 'B-'   THEN 16 WHEN 'B3'   THEN 16
        WHEN 'CCC'  THEN 17 WHEN 'CAA'  THEN 17
        WHEN 'CC'   THEN 18 WHEN 'CA'   THEN 18
        WHEN 'C'    THEN 19 
        WHEN 'D'    THEN 20
        WHEN 'UNRATED' THEN 99
        ELSE 98
    END AS rating_sort_order
FROM totals_calculated
ORDER BY agency_sort_order ASC, rating_sort_order ASC, credit_rating ASC;