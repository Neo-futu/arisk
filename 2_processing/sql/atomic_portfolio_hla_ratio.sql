-- atomic_portfolio_hla_ratio.sql
-- 貨幣基金高流動性資產佔比 (High Liquidity Assets Ratio, %)
-- 計算公式：
-- 1. 每日清算/1個工作日到期資產佔比 (%) = (1個工作日可變現資產 / 基金總淨值 Total NAV) * 100%
-- 2. 5個工作日到期資產佔比 (%) = (5個工作日可變現資產 / 基金總淨值 Total NAV) * 100%
-- 
-- 資產認定標準：
-- - 1日高流動資產：現金、隔夜逆回購、1個工作日內到期的定期存款與債券
-- - 5日高流動資產：1日高流動資產 + 2至5個工作日內到期的存款、逆回購與高流動性債券

WITH nav_summary AS (
    -- 1. 取得指定基準日 (:as_of_date) 之基金淨值 Total NAV
    SELECT
        fund_id,
        nav_date AS as_of_date,
        COALESCE(net_asset_value_hkd, 0.0) AS total_nav_hkd
    FROM fsi.fund_nav
    WHERE fund_id = :fid
      AND nav_date = :as_of_date
),
position_analytics AS (
    -- 2. 篩選持倉並計算剩餘工作日 / 清算天數
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        COALESCE(p.market_value_hkd, 0.0) AS market_value_hkd,
        LOWER(COALESCE(p.asset_class, p.instrument_type, '')) AS asset_type,
        b.final_maturity_date,
        -- 計算到期剩餘日數 (可根據實際需要替換為工作日計算邏輯)
        CASE 
            WHEN LOWER(COALESCE(p.asset_class, p.instrument_type, '')) IN ('cash', 'bank_deposit_overnight') THEN 0
            WHEN b.final_maturity_date IS NOT NULL THEN (b.final_maturity_date - p.as_of_date)
            ELSE 9999
        END AS days_to_maturity
    FROM fsi.positions p
    LEFT JOIN fsi.bond_analytics b 
           ON p.security_code = b.security_code 
          AND p.as_of_date = b.as_of_date
    WHERE p.fund_id = :fid
      AND p.as_of_date = :as_of_date
      AND p.market_value_hkd > 0
),
hla_summary AS (
    -- 3. 彙整 1 個工作日與 5 個工作日高流動性資產金額
    SELECT
        fund_id,
        as_of_date,
        -- 1個工作日可變現資產 (Cash, Overnight Repo, Deposit/Bond Maturity <= 1 Day)
        SUM(
            CASE 
                WHEN asset_type IN ('cash', 'cash_equivalent', 'reverse_repo') OR days_to_maturity <= 1 
                THEN market_value_hkd 
                ELSE 0.0 
            END
        ) AS hla_1day_amount_hkd,

        -- 5個工作日可變現資產 (1-Day HLA + Deposit/Bond Maturity <= 5 Days)
        SUM(
            CASE 
                WHEN asset_type IN ('cash', 'cash_equivalent', 'reverse_repo') OR days_to_maturity <= 5 
                THEN market_value_hkd 
                ELSE 0.0 
            END
        ) AS hla_5day_amount_hkd
    FROM position_analytics
    GROUP BY fund_id, as_of_date
),
calculated_ratios AS (
    -- 4. 整合 NAV 並計算占比
    SELECT
        n.fund_id,
        n.as_of_date,
        n.total_nav_hkd,
        COALESCE(h.hla_1day_amount_hkd, 0.0) AS hla_1day_amount_hkd,
        COALESCE(h.hla_5day_amount_hkd, 0.0) AS hla_5day_amount_hkd
    FROM nav_summary n
    LEFT JOIN hla_summary h 
           ON n.fund_id = h.fund_id 
          AND n.as_of_date = h.as_of_date
)
SELECT
    fund_id,
    as_of_date,
    ROUND(total_nav_hkd, 2) AS total_nav_hkd,
    ROUND(hla_1day_amount_hkd, 2) AS hla_1day_amount_hkd,
    ROUND(hla_5day_amount_hkd, 2) AS hla_5day_amount_hkd,
    
    -- 1. 1個工作日高流動性資產佔比 (%)
    ROUND(
        (hla_1day_amount_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS hla_1day_ratio_pct,
    
    -- 2. 5個工作日高流動性資產佔比 (%)
    ROUND(
        (hla_5day_amount_hkd / NULLIF(total_nav_hkd, 0.0)) * 100.0,
        4
    ) AS hla_5day_ratio_pct
FROM calculated_ratios;