-- atomic_sector_allocation_weight.sql
-- 原子指標：板塊 / 細分資產配置比 (%)
-- 說明：
-- 1. 淨值來源：fsi.balance_portfolio_nav (port_id, evaluate_date, net_asset)
-- 2. 板塊/資產來源：從股票 (balance_stock)、債券 (balance_bond)、存款 (balance_deposit)、
--    大額存單 (balance_cd) 與回購 (balance_repo) 等各分類持倉表中擷取行業或資產類別。

WITH nav_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之基金淨值 NAV
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS total_nav_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
all_holdings AS (
    -- 2. 彙整各類資產之市值與板塊/行業分類
    -- 股票
    SELECT 
        port_id AS fund_id, 
        evaluate_date AS as_of_date, 
        COALESCE(industry_name, sector, 'Unclassified Stocks') AS sector_name, 
        COALESCE(market_value, 0.0) AS market_value_hkd 
    FROM fsi.balance_stock 
    WHERE port_id = :fid AND evaluate_date = :as_of_date

    UNION ALL

    -- 債券
    SELECT 
        port_id AS fund_id, 
        evaluate_date AS as_of_date, 
        COALESCE(industry_name, bond_type, 'Unclassified Bonds') AS sector_name, 
        COALESCE(market_value, 0.0) AS market_value_hkd 
    FROM fsi.balance_bond 
    WHERE port_id = :fid AND evaluate_date = :as_of_date

    UNION ALL

    -- 存款
    SELECT 
        port_id AS fund_id, 
        evaluate_date AS as_of_date, 
        'Bank Deposits' AS sector_name, 
        COALESCE(market_value, amount, 0.0) AS market_value_hkd 
    FROM fsi.balance_deposit 
    WHERE port_id = :fid AND evaluate_date = :as_of_date

    UNION ALL

    -- 大額存單 (CD)
    SELECT 
        port_id AS fund_id, 
        evaluate_date AS as_of_date, 
        'Certificates of Deposit' AS sector_name, 
        COALESCE(market_value, amount, 0.0) AS market_value_hkd 
    FROM fsi.balance_cd 
    WHERE port_id = :fid AND evaluate_date = :as_of_date

    UNION ALL

    -- 逆回購
    SELECT 
        port_id AS fund_id, 
        evaluate_date AS as_of_date, 
        'Reverse Repos' AS sector_name, 
        COALESCE(market_value, amount, 0.0) AS market_value_hkd 
    FROM fsi.balance_repo 
    WHERE port_id = :fid AND evaluate_date = :as_of_date
),
sector_summary AS (
    -- 3. 按板塊/細分資產進行市值加總
    SELECT
        fund_id,
        as_of_date,
        sector_name,
        SUM(market_value_hkd) AS sector_mv_hkd
    FROM all_holdings
    GROUP BY fund_id, as_of_date, sector_name
)
SELECT
    n.fund_id,
    n.as_of_date,
    s.sector_name,
    ROUND(s.sector_mv_hkd, 2) AS sector_mv_hkd,
    ROUND(n.total_nav_hkd, 2) AS total_nav_hkd,
    
    -- 板塊/細分資產配置比 (%) = (板塊總市值 / 基金淨資產 NAV) * 100
    ROUND(
        (s.sector_mv_hkd / NULLIF(n.total_nav_hkd, 0.0)) * 100.0,
        6
    ) AS weight_pct

FROM nav_summary n
INNER JOIN sector_summary s 
        ON n.fund_id = s.fund_id 
       AND n.as_of_date = s.as_of_date
ORDER BY weight_pct DESC NULLS LAST;