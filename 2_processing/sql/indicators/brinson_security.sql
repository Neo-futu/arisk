-- brinson_security.sql
-- 單券層面 Brinson 歸因 (BHB / BF 模型日度累加版)
-- 說明：
-- 1. 持倉來源：fsi.positions (fund_id, as_of_date, security_code, instrument_id, security_name, market_value_hkd, pnl_hkd)
-- 2. 基準來源：fsi.benchmark_positions (benchmark_id, as_of_date, security_code, instrument_id, security_name, market_value_hkd, pnl_hkd)
-- 3. 金融邏輯：
--    - 單券層面 r_p = r_b = r_i (同隻股票當日市場收益率相同)。
--    - 單券的主動超額主要由主動權重 (w_p - w_b) 決定。
--    - Allocation (配置效應)  = (w_p - w_b) * (r_i - R_B)   [BF 修正版]
--    - Selection (選擇效應)   = 0 (單券無個股選擇差異)
--    - Interaction (交叉效應) = 0
--    - Total Excess (總超額)  = Allocation

WITH daily_portfolio_sec AS (
    -- 1. 組合：每日單券市值與損益
    SELECT
        fund_id,
        as_of_date,
        COALESCE(security_code, instrument_id, 'UNKNOWN') AS security_code,
        MAX(COALESCE(security_name, 'UNNAMED')) AS security_name,
        SUM(market_value_hkd) AS mv_p,
        SUM(pnl_hkd) AS pnl_p
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
    GROUP BY fund_id, as_of_date, COALESCE(security_code, instrument_id, 'UNKNOWN')
),
daily_portfolio_total AS (
    -- 2. 組合：每日總市值與總損益
    SELECT
        as_of_date,
        SUM(mv_p) AS total_mv_p,
        SUM(pnl_p) AS total_pnl_p
    FROM daily_portfolio_sec
    GROUP BY as_of_date
),
daily_benchmark_sec AS (
    -- 3. 基準：每日單券市值與損益
    SELECT
        benchmark_id,
        as_of_date,
        COALESCE(security_code, instrument_id, 'UNKNOWN') AS security_code,
        MAX(COALESCE(security_name, 'UNNAMED')) AS security_name,
        SUM(market_value_hkd) AS mv_b,
        SUM(pnl_hkd) AS pnl_b
    FROM fsi.benchmark_positions
    WHERE benchmark_id = :benchmark_id
      AND as_of_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
    GROUP BY benchmark_id, as_of_date, COALESCE(security_code, instrument_id, 'UNKNOWN')
),
daily_benchmark_total AS (
    -- 4. 基準：每日總市值與總損益（計算基準每日總收益率 R_B）
    SELECT
        as_of_date,
        SUM(mv_b) AS total_mv_b,
        SUM(pnl_b) AS total_pnl_b,
        CASE 
            WHEN SUM(mv_b) > 0.0 THEN SUM(pnl_b) / SUM(mv_b) 
            ELSE 0.0 
        END AS R_B
    FROM daily_benchmark_sec
    GROUP BY as_of_date
),
daily_base_metrics AS (
    -- 5. 每日單券權重 (w_p, w_b) 與真實標的日收益率 (r_i) 對齊
    SELECT
        COALESCE(p.as_of_date, b.as_of_date) AS as_of_date,
        COALESCE(p.security_code, b.security_code) AS security_code,
        COALESCE(p.security_name, b.security_name, 'UNNAMED') AS security_name,
        
        -- 單券權重 (當天無持倉則為 0.0)
        COALESCE(p.mv_p, 0.0) / NULLIF(pt.total_mv_p, 0.0) AS w_p,
        COALESCE(b.mv_b, 0.0) / NULLIF(bt.total_mv_b, 0.0) AS w_b,
        
        -- 單券日收益率 (優先使用組合損益比，次之使用基準損益比)
        CASE 
            WHEN COALESCE(p.mv_p, 0.0) > 0.0 THEN p.pnl_p / p.mv_p 
            WHEN COALESCE(b.mv_b, 0.0) > 0.0 THEN b.pnl_b / b.mv_b 
            ELSE 0.0 
        END AS r_i,
        
        -- 基準整體總收益率 R_B
        COALESCE(bt.R_B, 0.0) AS R_B
    FROM daily_portfolio_sec p
    FULL OUTER JOIN daily_benchmark_sec b 
                 ON p.as_of_date = b.as_of_date 
                AND p.security_code = b.security_code
    LEFT JOIN daily_portfolio_total pt ON COALESCE(p.as_of_date, b.as_of_date) = pt.as_of_date
    LEFT JOIN daily_benchmark_total bt ON COALESCE(p.as_of_date, b.as_of_date) = bt.as_of_date
),
daily_attribution AS (
    -- 6. 計算每日單券歸因效應
    SELECT
        as_of_date,
        security_code,
        security_name,
        w_p,
        w_b,
        r_i,
        
        -- 主動權重差
        (w_p - w_b) AS active_weight,
        
        -- 1. 配置效應 (Allocation): (w_p - w_b) * (r_i - R_B)
        (w_p - w_b) * (r_i - R_B) AS alloc_effect,
        
        -- 2. 選擇效應 (Selection): 單券層面為 0
        0.0 AS select_effect,
        
        -- 3. 交叉效應 (Interaction): 單券層面為 0
        0.0 AS interact_effect
    FROM daily_base_metrics
)
-- 7. 區間累加與最終結果輸出 (%)
SELECT
    :fid AS fund_id,
    :benchmark_id AS benchmark_id,
    CAST(:start_date AS DATE) AS start_date,
    CAST(:end_date AS DATE) AS end_date,
    security_code,
    MAX(security_name) AS security_name,
    
    -- 平均持倉權重 (%)
    ROUND(AVG(w_p) * 100.0, 4) AS avg_w_p_pct,
    ROUND(AVG(w_b) * 100.0, 4) AS avg_w_b_pct,
    ROUND(AVG(active_weight) * 100.0, 4) AS avg_active_weight_pct,
    
    -- 個股平均日收益率 (%)
    ROUND(AVG(r_i) * 100.0, 4) AS avg_daily_r_pct,
    
    -- 歸因拆解累計值 (%)
    ROUND(SUM(alloc_effect) * 100.0, 6) AS cumulative_allocation_effect_pct,
    ROUND(SUM(select_effect) * 100.0, 6) AS cumulative_selection_effect_pct,
    ROUND(SUM(interact_effect) * 100.0, 6) AS cumulative_interaction_effect_pct,
    
    -- 總超額收益貢獻 (%)
    ROUND(SUM(alloc_effect) * 100.0, 6) AS total_excess_pct

FROM daily_attribution
GROUP BY security_code
ORDER BY total_excess_pct DESC NULLS LAST;