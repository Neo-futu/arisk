-- atomic_single_position_weight.sql
-- 原子指標：個股/個券市值佔淨值比 (%)
-- 說明：
-- 1. 淨值來源：fsi.balance_portfolio_nav (port_id, evaluate_date, net_asset)
-- 2. 持倉來源：fsi.balance_stock, fsi.balance_bond, fsi.balance_fund, fsi.balance_repo 等
-- 3. 計算公式：(單一標的持倉市值 / 組合 NAV) * 100

WITH current_nav AS (
    -- 1. 取得指定日期的組合淨資產 (NAV)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS nav_t
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
pos_union AS (
    -- 2. 彙整多資產類別持倉
    -- 股票持倉
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, wind_code, ticker, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(market_value, 0.0) AS mv_i
    FROM fsi.balance_stock
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date

    UNION ALL

    -- 債券持倉
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, wind_code, bond_code, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(market_value, 0.0) AS mv_i
    FROM fsi.balance_bond
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date

    UNION ALL

    -- 基金持倉
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, fund_code, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        COALESCE(market_value, 0.0) AS mv_i
    FROM fsi.balance_fund
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date

    UNION ALL

    -- 逆回購 / 貨幣型頭寸
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(security_code, repo_code, 'REVERSE_REPO') AS security_code,
        COALESCE(security_name, 'Reverse Repo') AS security_name,
        COALESCE(market_value, amount, 0.0) AS mv_i
    FROM fsi.balance_repo
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
position_summary AS (
    -- 3. 按標的進行市值彙總
    SELECT
        fund_id,
        as_of_date,
        security_code,
        security_name,
        SUM(mv_i) AS position_mv
    FROM pos_union
    GROUP BY fund_id, as_of_date, security_code, security_name
)
SELECT
    p.fund_id,
    p.as_of_date,
    p.security_code,
    p.security_name,
    p.position_mv,
    n.nav_t AS total_nav,
    
    -- 個股/個券市值佔淨值比 (%) = (單一持倉市值 / 基金淨資產 NAV) * 100
    CASE
        WHEN n.nav_t IS NULL OR n.nav_t <= 0.0 THEN NULL
        ELSE ROUND((p.position_mv / n.nav_t) * 100.0, 6)
    END AS weight_pct

FROM position_summary p
LEFT JOIN current_nav n 
       ON p.fund_id = n.fund_id 
      AND p.as_of_date = n.as_of_date
ORDER BY weight_pct DESC NULLS LAST;