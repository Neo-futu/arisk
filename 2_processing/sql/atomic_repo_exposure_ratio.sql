-- atomic_repo_exposure_ratio.sql
-- 正/逆回購敞口佔比 (Repo & Reverse Repo Exposure Ratios, %)
-- 說明：
-- 1. 淨值資料來源：fsi.balance_portfolio_nav (port_id, evaluate_date, net_asset)
-- 2. 回購持倉來源：fsi.balance_repo (port_id, evaluate_date, market_value/amount, repo_type/direction)
-- 3. 計算邏輯：
--    - 正回購 (Repo)：融入資金 (通常 repo_type = 'REPO' 或金額 < 0)
--    - 逆回購 (Reverse Repo)：融出資金 (通常 repo_type = 'REVERSE_REPO' 或金額 > 0)

WITH nav_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之基金淨值 (NAV)
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(net_asset, 0.0) AS total_nav_hkd
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
),
repo_positions AS (
    -- 2. 彙整 fsi.balance_repo 中的正回購與逆回購金額
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        
        -- 正回購 (Repo / 融入資金)
        SUM(
            CASE 
                WHEN UPPER(COALESCE(repo_type, '')) IN ('REPO', 'REP', 'PLEDGED_REPO')
                     OR COALESCE(direction, '') = 'PAYABLE'
                     OR COALESCE(market_value, amount, 0.0) < 0
                THEN ABS(COALESCE(market_value, amount, 0.0))
                ELSE 0.0
            END
        ) AS total_repo_amount_hkd,
        
        -- 逆回購 (Reverse Repo / 融出資金)
        SUM(
            CASE 
                WHEN UPPER(COALESCE(repo_type, '')) IN ('REVERSE_REPO', 'REV_REPO', 'REVERSE')
                     OR COALESCE(direction, '') = 'RECEIVABLE'
                     OR COALESCE(market_value, amount, 0.0) > 0
                THEN ABS(COALESCE(market_value, amount, 0.0))
                ELSE 0.0
            END
        ) AS total_reverse_repo_amount_hkd

    FROM fsi.balance_repo
    WHERE port_id = :fid
      AND evaluate_date = :as_of_date
    GROUP BY port_id, evaluate_date
),
calculated_ratios AS (
    -- 3. 整合淨值與回購金額
    SELECT
        n.fund_id,
        n.as_of_date,
        n.total_nav_hkd,
        COALESCE(r.total_repo_amount_hkd, 0.0) AS total_repo_amount_hkd,
        COALESCE(r.total_reverse_repo_amount_hkd, 0.0) AS total_reverse_repo_amount_hkd
    FROM nav_summary n
    LEFT JOIN repo_positions r 
           ON n.fund_id = r.fund_id 
          AND n.as_of_date = r.as_of_date
)
SELECT
    fund_id,
    as_of_date,
    ROUND(total_nav_hkd, 2) AS total_nav_hkd,
    ROUND(total_repo_amount_hkd, 2) AS total_repo_amount_hkd,
    ROUND(total_reverse_repo_amount_hkd, 2) AS total_reverse_repo_amount_hkd,
    
    -- 1. 正回購佔比 (%) (Repo Ratio = Repo Amount / NAV * 100)
    ROUND(
        (total_repo_amount_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS repo_ratio_pct,
    
    -- 2. 逆回購佔比 (%) (Reverse Repo Ratio = Reverse Repo Amount / NAV * 100)
    ROUND(
        (total_reverse_repo_amount_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS reverse_repo_ratio_pct,

    -- 3. 淨回購敞口佔比 (%) (Net Repo Ratio = (Reverse Repo - Repo) / NAV * 100)
    ROUND(
        ((total_reverse_repo_amount_hkd - total_repo_amount_hkd) / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS net_repo_ratio_pct

FROM calculated_ratios;