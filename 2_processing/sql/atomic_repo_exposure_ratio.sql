-- atomic_repo_exposure_ratio.sql
-- 正/逆回購佔比 (Repo & Reverse Repo Exposure Ratios, %)
-- 計算說明：
-- 1. 正回購 (Repurchase Agreements / Repo, 融入資金/履約負債)：
--    通常表現為負債或負市值，佔比 = (正回購總金額 / 基金總淨值 NAV) * 100%
-- 2. 逆回購 (Reverse Repurchase Agreements / Reverse Repo, 融出資金/短期資產)：
--    通常表現為資產或正市值，佔比 = (逆回購總金額 / 基金總淨值 NAV) * 100%

WITH nav_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之基金淨值 NAV
    SELECT
        fund_id,
        nav_date AS as_of_date,
        COALESCE(net_asset_value_hkd, 0.0) AS total_nav_hkd
    FROM fsi.fund_nav
    WHERE fund_id = :fid
      AND nav_date = :as_of_date
),
repo_positions AS (
    -- 2. 篩選並彙整正回購與逆回購持倉金額 (HKD)
    SELECT
        fund_id,
        as_of_date,
        -- 正回購 (Repo / Sold under agreements to repurchase)
        SUM(
            CASE 
                WHEN LOWER(instrument_type) IN ('repo', 'repurchase_agreement', 'repo_payable')
                     OR LOWER(asset_class) = 'repo'
                THEN ABS(COALESCE(market_value_hkd, 0.0))
                ELSE 0.0
            END
        ) AS total_repo_amount_hkd,
        
        -- 逆回購 (Reverse Repo / Purchased under agreements to resell)
        SUM(
            CASE 
                WHEN LOWER(instrument_type) IN ('reverse_repo', 'reverse_repurchase_agreement', 'repo_receivable')
                     OR LOWER(asset_class) = 'reverse_repo'
                THEN ABS(COALESCE(market_value_hkd, 0.0))
                ELSE 0.0
            END
        ) AS total_reverse_repo_amount_hkd
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
    GROUP BY fund_id, as_of_date
),
calculated_ratios AS (
    -- 3. 整合 NAV 與回購金額計算佔比
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