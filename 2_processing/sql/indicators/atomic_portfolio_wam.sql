-- atomic_portfolio_wam.sql
-- 貨幣基金組合加權平均剩餘期限 (Weighted Average Maturity, WAM)
-- 說明：
-- 1. 優先讀取 fsi.balance_portfolio_mmf 中的官方聚合指標 wam_days 與 wal_days。
-- 2. 同時從底層貨幣市場工具持倉表 (balance_bond, balance_deposit, balance_cd, balance_repo) 計算穿透驗證之 WAM。

WITH mmf_aggregated AS (
    -- 1. 取得 fsi.balance_portfolio_mmf 官方聚合數據
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        income_per_10k,
        return_rate_7d,
        nav_deviation,
        nav_deviation_amount,
        wam_days AS aggregated_wam_days,
        wal_days AS aggregated_wal_days
    FROM fsi.balance_portfolio_mmf
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
nav_summary AS (
    -- 2. 取得指定基準日之基金淨值 (NAV)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS total_nav_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
holdings_wam_calculated AS (
    -- 3. 從底層持倉表 (債券、存款、CD、逆回購) 穿透計算加權 WAM
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        SUM(market_value_hkd) AS total_mmf_assets_mv_hkd,
        SUM(market_value_hkd * days_to_maturity) AS weighted_wam_days_sum
    FROM (
        -- 債券
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, 0.0)) AS market_value_hkd, GREATEST(CAST(maturity_date AS DATE) - CAST(evaluate_date AS DATE), 0) AS days_to_maturity 
        FROM fsi.balance_bond WHERE port_id = :fid AND evaluate_date = :as_of_date AND maturity_date IS NOT NULL
        UNION ALL
        -- 存款
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, amount, 0.0)) AS market_value_hkd, GREATEST(CAST(maturity_date AS DATE) - CAST(evaluate_date AS DATE), 0) AS days_to_maturity 
        FROM fsi.balance_deposit WHERE port_id = :fid AND evaluate_date = :as_of_date AND maturity_date IS NOT NULL
        UNION ALL
        -- 大額存單 (CD)
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, amount, 0.0)) AS market_value_hkd, GREATEST(CAST(maturity_date AS DATE) - CAST(evaluate_date AS DATE), 0) AS days_to_maturity 
        FROM fsi.balance_cd WHERE port_id = :fid AND evaluate_date = :as_of_date AND maturity_date IS NOT NULL
        UNION ALL
        -- 逆回購
        SELECT port_id, evaluate_date, ABS(COALESCE(market_value, amount, 0.0)) AS market_value_hkd, GREATEST(CAST(maturity_date AS DATE) - CAST(evaluate_date AS DATE), 0) AS days_to_maturity 
        FROM fsi.balance_repo WHERE port_id = :fid AND evaluate_date = :as_of_date AND maturity_date IS NOT NULL
    ) sub_holdings
    GROUP BY port_id, evaluate_date
)
SELECT
    n.fund_id,
    n.as_of_date,
    ROUND(n.total_nav_hkd, 2) AS total_nav_hkd,
    
    -- MMF 收益率與偏離度指標
    m.income_per_10k,
    m.return_rate_7d,
    m.nav_deviation,
    m.nav_deviation_amount,
    
    -- 1. 官方表 WAM (天) 與 WAL (天)
    m.aggregated_wam_days AS wam_days,
    m.aggregated_wal_days AS wal_days,
    ROUND(m.aggregated_wam_days / 365.0, 4) AS wam_years,
    
    -- 2. 持倉穿透計算 WAM (天) - 供覆核對驗
    ROUND(
        h.weighted_wam_days_sum / NULLIF(h.total_mmf_assets_mv_hkd, 0.0),
        2
    ) AS computed_wam_days_from_positions,
    
    -- 3. 貨幣工具持倉佔淨值比例 (%)
    ROUND(
        (COALESCE(h.total_mmf_assets_mv_hkd, 0.0) / NULLIF(n.total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS mmf_assets_weight_pct

FROM nav_summary n
LEFT JOIN mmf_aggregated m 
       ON n.fund_id = m.fund_id 
      AND n.as_of_date = m.as_of_date
LEFT JOIN holdings_wam_calculated h 
       ON n.fund_id = h.fund_id 
      AND n.as_of_date = h.as_of_date;