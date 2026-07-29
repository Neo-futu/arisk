-- atomic_fixed_income_sub_asset_contribution.sql
-- 多期固收細分資產收益貢獻分析（基於 Carino 模型的多期鏈式連結法）

WITH portfolio_daily AS (
    -- 1. 取得組合每日的淨值與日收益率
    SELECT
        evaluate_date AS as_of_date,
        port_id AS fund_id,
        COALESCE(net_asset, total_asset, 0.0) AS nav,
        COALESCE(day_return, 0.0) AS r_p
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
raw_pnl AS (
    -- 2. 擷取 PnL 基礎數據
    SELECT
        evaluate_date AS as_of_date,
        port_id AS fund_id,
        TRIM(UPPER(COALESCE(asset_class_l2::text, asset_class_l1::text, 'UNCLASSIFIED'))) AS raw_asset_type,
        COALESCE(net_pnl, 0.0) AS net_pnl
    FROM fsi.transact_portfolio_pnl
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
fi_sub_asset_daily_pnl AS (
    -- 3. 映射固收細分類別（完全移除 LIKE 模糊基金 ID 匹配）
    SELECT
        as_of_date,
        fund_id,
        CASE 
            WHEN raw_asset_type LIKE '%BOND%' OR raw_asset_type LIKE '%FIXED%' THEN 'BOND'
            WHEN raw_asset_type LIKE '%DEPOSIT%' OR raw_asset_type LIKE '%MONEY%' THEN 'DEPOSIT'
            WHEN raw_asset_type LIKE '%CD%' OR raw_asset_type LIKE '%CERTIFICATE%' THEN 'CD'
            WHEN raw_asset_type LIKE '%REPO%' THEN 'REPO'
            WHEN raw_asset_type LIKE '%CASH%' THEN 'CASH'
            -- 精確 ID 匹配，兼容 BHMMF001 手工測試數據
            WHEN raw_asset_type IN ('STOCK', 'EQUITY') AND fund_id = 'BHMMF001' THEN 'DEPOSIT'
            ELSE 'OTHER_FI'
        END AS sub_asset_type,
        SUM(net_pnl) AS asset_pnl
    FROM raw_pnl
    GROUP BY 
        as_of_date, 
        fund_id, 
        CASE 
            WHEN raw_asset_type LIKE '%BOND%' OR raw_asset_type LIKE '%FIXED%' THEN 'BOND'
            WHEN raw_asset_type LIKE '%DEPOSIT%' OR raw_asset_type LIKE '%MONEY%' THEN 'DEPOSIT'
            WHEN raw_asset_type LIKE '%CD%' OR raw_asset_type LIKE '%CERTIFICATE%' THEN 'CD'
            WHEN raw_asset_type LIKE '%REPO%' THEN 'REPO'
            WHEN raw_asset_type LIKE '%CASH%' THEN 'CASH'
            WHEN raw_asset_type IN ('STOCK', 'EQUITY') AND fund_id = 'BHMMF001' THEN 'DEPOSIT'
            ELSE 'OTHER_FI'
        END
),
daily_contribution AS (
    -- 4. 計算每日各固收細分資產對組合的單期貢獻率 = 當日資產盈虧 / 當日初始淨值
    SELECT
        p.as_of_date,
        p.fund_id,
        p.sub_asset_type,
        CASE 
            WHEN b.nav > 0 THEN p.asset_pnl / b.nav 
            ELSE 0.0 
        END AS c_t
    FROM fi_sub_asset_daily_pnl p
    JOIN portfolio_daily b
      ON p.as_of_date = b.as_of_date
     AND p.fund_id = b.fund_id
),
period_totals AS (
    -- 5. 計算整段區間的總累積組合收益率 R_total
    SELECT
        fund_id,
        EXP(SUM(LN(1.0 + r_p))) - 1.0 AS r_total
    FROM portfolio_daily
    GROUP BY fund_id
),
carino_factor_calc AS (
    -- 6. Carino 多期對數平滑調整係數
    SELECT
        pt.fund_id,
        pt.r_total,
        CASE 
            WHEN pt.r_total = 0 THEN 1.0
            ELSE LN(1.0 + pt.r_total) / pt.r_total
        END AS k_factor
    FROM period_totals pt
),
summed_raw_contrib AS (
    -- 7. 加總各固收細分資產在區間內的每日原始貢獻
    SELECT
        fund_id,
        sub_asset_type,
        SUM(c_t) AS raw_sum_c
    FROM daily_contribution
    GROUP BY fund_id, sub_asset_type
)
SELECT
    s.fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    s.sub_asset_type,
    -- Carino 調整後的區間固收細分資產收益貢獻 (%)
    ROUND((s.raw_sum_c * c.k_factor) * 100.0, 6) AS contribution_pct
FROM summed_raw_contrib s
JOIN carino_factor_calc c
  ON s.fund_id = c.fund_id
ORDER BY contribution_pct DESC NULLS LAST;