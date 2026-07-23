-- campisi_fixed_income.sql
-- 固收 Campisi 歸因分析 (Campisi Fixed Income Attribution)
-- 分解四大收益來源：票息收益 (Coupon)、利率收益 (Treasury)、信用利差收益 (Spread)、選債收益 (Selection)

WITH fi_positions AS (
    SELECT
        fund_id,
        security_code,
        security_name,
        market_value_hkd,
        pnl_hkd,
        coupon_income_hkd,
        COALESCE(duration, 0.0) AS duration,
        COALESCE(spread_duration, duration, 0.0) AS spread_duration,
        COALESCE(delta_treasury_yield, 0.0) AS delta_treasury_yield, -- 國債收益率變動 (小數表示，如 10bps = 0.0010)
        COALESCE(delta_credit_spread, 0.0) AS delta_credit_spread,   -- 信用利差變動 (小數表示)
        market_value_hkd / NULLIF(SUM(market_value_hkd) OVER (PARTITION BY fund_id), 0) AS weight
    FROM fsi.bond_positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN :start_date AND :end_date
),
campisi_components AS (
    SELECT
        fund_id,
        security_code,
        security_name,
        weight,
        -- 總收益率 (Total Return)
        CASE WHEN market_value_hkd > 0 THEN pnl_hkd / market_value_hkd ELSE 0.0 END AS r_total,
        
        -- 1. 票息收益 (Coupon Effect): 持有期利息收入 / 期初市值
        CASE WHEN market_value_hkd > 0 THEN coupon_income_hkd / market_value_hkd ELSE 0.0 END AS r_coupon,
        
        -- 2. 利率收益 (Treasury Effect): - Duration * ΔTreasury Yield
        -1.0 * duration * delta_treasury_yield AS r_treasury,
        
        -- 3. 信用利差收益 (Spread Effect): - Spread Duration * ΔCredit Spread
        -1.0 * spread_duration * delta_credit_spread AS r_spread
    FROM fi_positions
),
campisi_full AS (
    SELECT
        fund_id,
        security_code,
        security_name,
        weight,
        r_total,
        r_coupon,
        r_treasury,
        r_spread,
        -- 4. 選債收益 (Selection Effect): 總收益 - (票息收益 + 利率收益 + 信用利差收益)
        (r_total - (r_coupon + r_treasury + r_spread)) AS r_selection
    FROM campisi_components
)
SELECT
    fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    security_code,
    security_name,
    ROUND(weight * 100.0, 6) AS weight_pct,
    ROUND(r_total * 100.0, 6) AS total_return_pct,
    
    -- 單券層面各收益成分 (%)
    ROUND(r_coupon * 100.0, 6) AS coupon_effect_pct,
    ROUND(r_treasury * 100.0, 6) AS treasury_effect_pct,
    ROUND(r_spread * 100.0, 6) AS spread_effect_pct,
    ROUND(r_selection * 100.0, 6) AS selection_effect_pct,
    
    -- 組合層面貢獻度 (Weighted Contribution, %)
    ROUND((weight * r_coupon) * 100.0, 6) AS contrib_coupon_pct,
    ROUND((weight * r_treasury) * 100.0, 6) AS contrib_treasury_pct,
    ROUND((weight * r_spread) * 100.0, 6) AS contrib_spread_pct,
    ROUND((weight * r_selection) * 100.0, 6) AS contrib_selection_pct,
    ROUND((weight * r_total) * 100.0, 6) AS contrib_total_pct
FROM campisi_full
ORDER BY contrib_total_pct DESC NULLS LAST;
