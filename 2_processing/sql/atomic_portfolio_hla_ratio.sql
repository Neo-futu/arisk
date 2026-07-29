-- atomic_portfolio_hla_ratio.sql
-- 貨幣基金高流動性資產佔比 (High Liquidity Assets Ratio, %)
-- 計算公式：
-- 1. 1個工作日高流動資產佔比 (%) = (1個工作日可變現資產 / 基金總淨值 Total NAV) * 100%
-- 2. 5個工作日高流動資產佔比 (%) = (5個工作日可變現資產 / 基金總淨值 Total NAV) * 100%
-- 需要ai補充數據，請根據這個計算變現的腳本 atomic_portfolio_hla_ratio.sql，在數據庫中添加相應表中的所需的組合，所需的nav淨值，所需的資產類別數據，現金，存款，債券等腳本正確計算dv01

WITH nav_summary AS (
    -- 1. 取得基金總淨值 (來自 fsi.balance_portfolio_nav)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS total_nav_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
all_assets_maturity AS (
    -- 2. 按資產分表聚合金額與到期天數

    -- (1) 現金資產：直接認定為 0 天到期
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(market_value, amount, 0.0) AS market_value_hkd,
        0 AS days_to_maturity
    FROM fsi.balance_cash
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date

    UNION ALL

    -- (2) 銀行存款：計算 (maturity_date - evaluate_date)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(market_value, amount, 0.0) AS market_value_hkd,
        COALESCE(maturity_date - evaluate_date, 0) AS days_to_maturity
    FROM fsi.balance_deposit
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date

    UNION ALL

    -- (3) 大額存單 (CD)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(market_value, amount, 0.0) AS market_value_hkd,
        COALESCE(maturity_date - evaluate_date, 9999) AS days_to_maturity
    FROM fsi.balance_cd
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date

    UNION ALL

    -- (4) 逆回購 (Repo)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(market_value, amount, 0.0) AS market_value_hkd,
        COALESCE(expire_date - evaluate_date, maturity_date - evaluate_date, 0) AS days_to_maturity
    FROM fsi.balance_repo
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date

    UNION ALL

    -- (5) 債券資產 (Bond)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(market_value, 0.0) AS market_value_hkd,
        COALESCE(maturity_date - evaluate_date, 9999) AS days_to_maturity
    FROM fsi.balance_bond
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
hla_summary AS (
    -- 3. 彙整 1 個工作日與 5 個工作日高流動性資產金額
    SELECT
        fund_id,
        as_of_date,
        SUM(CASE WHEN days_to_maturity <= 1 THEN market_value_hkd ELSE 0.0 END) AS hla_1day_amount_hkd,
        SUM(CASE WHEN days_to_maturity <= 5 THEN market_value_hkd ELSE 0.0 END) AS hla_5day_amount_hkd
    FROM all_assets_maturity
    GROUP BY fund_id, as_of_date
)
SELECT
    n.fund_id,
    n.as_of_date,
    ROUND(n.total_nav_hkd, 2) AS total_nav_hkd,
    ROUND(COALESCE(h.hla_1day_amount_hkd, 0.0), 2) AS hla_1day_amount_hkd,
    ROUND(COALESCE(h.hla_5day_amount_hkd, 0.0), 2) AS hla_5day_amount_hkd,
    
    -- 1. 1個工作日高流動性資產佔比 (%)
    ROUND(
        (COALESCE(h.hla_1day_amount_hkd, 0.0) / NULLIF(n.total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS hla_1day_ratio_pct,
    
    -- 2. 5個工作日高流動性資產佔比 (%)
    ROUND(
        (COALESCE(h.hla_5day_amount_hkd, 0.0) / NULLIF(n.total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS hla_5day_ratio_pct
FROM nav_summary n
LEFT JOIN hla_summary h 
       ON n.fund_id = h.fund_id 
      AND n.as_of_date = h.as_of_date;