-- campisi_fixed_income.sql
-- 固收 Campisi 歸因分析 (Campisi Fixed Income Attribution - 日度累加版)
-- 說明：
-- 1. 持倉來源：fsi.bond_positions
-- 2. 收益拆解模型 (Campisi Framework):
--    - Total Return (總收益) = Income Return (收入收益) + Price Return (資本利得/價格收益)
--    - Income Return (票息收益) = coupon_income_hkd / market_value_hkd
--    - Price Return (價格收益)  = pnl_hkd / market_value_hkd - Income Return
--    - Treasury Effect (利率效應)  = -1.0 * duration * delta_treasury_yield
--    - Spread Effect (利差效應)    = -1.0 * spread_duration * delta_credit_spread
--    - Selection Effect (選債/殘差) = Price Return - (Treasury Effect + Spread Effect)

WITH daily_bond_positions AS (
    -- 1. 每日持倉與基礎指標
    SELECT
        fund_id,
        as_of_date,
        COALESCE(security_code, instrument_id, 'UNKNOWN') AS security_code,
        MAX(COALESCE(security_name, 'UNNAMED')) AS security_name,
        SUM(market_value_hkd) AS mv_i,
        SUM(pnl_hkd) AS pnl_i,
        SUM(COALESCE(coupon_income_hkd, 0.0)) AS coupon_i,
        AVG(COALESCE(duration, 0.0)) AS duration_i,
        AVG(COALESCE(spread_duration, duration, 0.0)) AS spread_duration_i,
        AVG(COALESCE(delta_treasury_yield, 0.0)) AS delta_y_treasury, -- 小數表示, 如 10bps = 0.0010
        AVG(COALESCE(delta_credit_spread, 0.0)) AS delta_y_spread      -- 小數表示
    FROM fsi.bond_positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
    GROUP BY fund_id, as_of_date, COALESCE(security_code, instrument_id, 'UNKNOWN')
),
daily_portfolio_total AS (
    -- 2. 每日組合總市值
    SELECT
        as_of_date,
        SUM(mv_i) AS total_mv
    FROM daily_bond_positions
    GROUP BY as_of_date
),
daily_campisi_components AS (
    -- 3. 計算每日單券 Campisi 收益成分與加權貢獻
    SELECT
        p.as_of_date,
        p.security_code,
        p.security_name,
        
        -- 日度權重
        p.mv_i / NULLIF(pt.total_mv, 0.0) AS w_i,
        
        -- 總收益率 (Total Return)
        CASE WHEN p.mv_i > 0.0 THEN p.pnl_i / p.mv_i ELSE 0.0 END AS r_total,
        
        -- 1. 票息收益率 (Income / Coupon Return)
        CASE WHEN p.mv_i > 0.0 THEN p.coupon_i / p.mv_i ELSE 0.0 END AS r_coupon,
        
        -- 2. 利率效應收益率 (Treasury Effect): -Duration * ΔY_treasury
        -1.0 * p.duration_i * p.delta_y_treasury AS r_treasury,
        
        -- 3. 信用利差效應收益率 (Spread Effect): -Spread_Duration * ΔY_spread
        -1.0 * p.spread_duration_i * p.delta_y_spread AS r_spread
    FROM daily_bond_positions p
    JOIN daily_portfolio_total pt ON p.as_of_date = pt.as_of_date
),
daily_campisi_full AS (
    -- 4. 補全選債/殘差效應 (Selection Effect) 及每日加權貢獻
    SELECT
        as_of_date,
        security_code,
        security_name,
        w_i,
        r_total,
        r_coupon,
        r_treasury,
        r_spread,
        
        -- 4. 選債/殘差收益率 (Selection / Residual Effect):
        -- 價格收益 (r_total - r_coupon) 扣除 (利率效應 + 利差效應)
        (r_total - r_coupon) - (r_treasury + r_spread) AS r_selection,
        
        -- 每日組合同比貢獻 (Weighted Contributions)
        w_i * r_coupon AS contrib_coupon,
        w_i * r_treasury AS contrib_treasury,
        w_i * r_spread AS contrib_spread,
        w_i * ((r_total - r_coupon) - (r_treasury + r_spread)) AS contrib_selection,
        w_i * r_total AS contrib_total
    FROM daily_campisi_components
)
-- 5. 跨區間累加與結果輸出 (%)
SELECT
    :fid AS fund_id,
    CAST(:start_date AS DATE) AS start_date,
    CAST(:end_date AS DATE) AS end_date,
    security_code,
    MAX(security_name) AS security_name,
    
    -- 平均日度持倉權重 (%)
    ROUND(AVG(w_i) * 100.0, 4) AS avg_weight_pct,
    
    -- 單券平均日收益率拆解 (%)
    ROUND(AVG(r_total) * 100.0, 4) AS avg_daily_total_return_pct,
    ROUND(AVG(r_coupon) * 100.0, 4) AS avg_daily_coupon_effect_pct,
    ROUND(AVG(r_treasury) * 100.0, 4) AS avg_daily_treasury_effect_pct,
    ROUND(AVG(r_spread) * 100.0, 4) AS avg_daily_spread_effect_pct,
    ROUND(AVG(r_selection) * 100.0, 4) AS avg_daily_selection_effect_pct,
    
    -- 組合層面區間累計貢獻度 (Cumulative Weighted Contribution, %)
    ROUND(SUM(contrib_coupon) * 100.0, 6) AS cumulative_contrib_coupon_pct,
    ROUND(SUM(contrib_treasury) * 100.0, 6) AS cumulative_contrib_treasury_pct,
    ROUND(SUM(contrib_spread) * 100.0, 6) AS cumulative_contrib_spread_pct,
    ROUND(SUM(contrib_selection) * 100.0, 6) AS cumulative_contrib_selection_pct,
    ROUND(SUM(contrib_total) * 100.0, 6) AS cumulative_contrib_total_pct

FROM daily_campisi_full
GROUP BY security_code
ORDER BY cumulative_contrib_total_pct DESC NULLS LAST;