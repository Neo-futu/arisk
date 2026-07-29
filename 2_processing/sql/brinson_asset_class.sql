-- brinson_asset_class.sql
-- 大類資產層面 Brinson 歸因 (BHB / BF 模型日度累加版)
-- 說明：
-- 1. 持倉來源：fsi.positions (fund_id, as_of_date, asset_class, market_value_hkd, pnl_hkd)
-- 2. 基準來源：fsi.benchmark_positions (benchmark_id, as_of_date, asset_class, market_value_hkd, pnl_hkd)
-- 3. 歸因公式 (日度分析):
--    - Allocation (配置效應)  = (w_p - w_b) * (r_b - R_B)   [BF 修正版，排除大盤基底收益影響]
--    - Selection (選擇效應)   = w_b * (r_p - r_b)
--    - Interaction (交叉效應) = (w_p - w_b) * (r_p - r_b)
--    - Total Excess (總超額)  = Allocation + Selection + Interaction

WITH daily_portfolio_asset AS (
    -- 1. 組合：每日各資產類別市值與損益
    SELECT
        fund_id,
        as_of_date,
        COALESCE(asset_class, 'UNCLASSIFIED') AS asset_class,
        SUM(market_value_hkd) AS mv_p,
        SUM(pnl_hkd) AS pnl_p
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
    GROUP BY fund_id, as_of_date, COALESCE(asset_class, 'UNCLASSIFIED')
),
daily_portfolio_total AS (
    -- 2. 組合：每日總市值與總損益
    SELECT
        as_of_date,
        SUM(mv_p) AS total_mv_p,
        SUM(pnl_p) AS total_pnl_p
    FROM daily_portfolio_asset
    GROUP BY as_of_date
),
daily_benchmark_asset AS (
    -- 3. 基準：每日各資產類別市值與損益
    SELECT
        benchmark_id,
        as_of_date,
        COALESCE(asset_class, 'UNCLASSIFIED') AS asset_class,
        SUM(market_value_hkd) AS mv_b,
        SUM(pnl_hkd) AS pnl_b
    FROM fsi.benchmark_positions
    WHERE benchmark_id = :benchmark_id
      AND as_of_date BETWEEN CAST(:start_date AS DATE) AND CAST(:end_date AS DATE)
    GROUP BY benchmark_id, as_of_date, COALESCE(asset_class, 'UNCLASSIFIED')
),
daily_benchmark_total AS (
    -- 4. 基準：每日總市值與總損益（用於計算基準每日總收益率 R_B）
    SELECT
        as_of_date,
        SUM(mv_b) AS total_mv_b,
        SUM(pnl_b) AS total_pnl_b,
        CASE 
            WHEN SUM(mv_b) > 0 THEN SUM(pnl_b) / SUM(mv_b) 
            ELSE 0.0 
        END AS R_B
    FROM daily_benchmark_asset
    GROUP BY as_of_date
),
daily_base_metrics AS (
    -- 5. 每日權重 (w_p, w_b) 與日收益率 (r_p, r_b) 對齊計算
    SELECT
        COALESCE(p.as_of_date, b.as_of_date) AS as_of_date,
        COALESCE(p.asset_class, b.asset_class) AS asset_class,
        
        -- 權重 (當天無持倉則為 0)
        COALESCE(p.mv_p, 0.0) / NULLIF(pt.total_mv_p, 0.0) AS w_p,
        COALESCE(b.mv_b, 0.0) / NULLIF(bt.total_mv_b, 0.0) AS w_b,
        
        -- 各資產類別收益率 (PNL / MV)
        CASE WHEN COALESCE(p.mv_p, 0.0) > 0 THEN p.pnl_p / p.mv_p ELSE 0.0 END AS r_p,
        CASE WHEN COALESCE(b.mv_b, 0.0) > 0 THEN b.pnl_b / b.mv_b ELSE 0.0 END AS r_b,
        
        -- 基準整體總收益率
        COALESCE(bt.R_B, 0.0) AS R_B
    FROM daily_portfolio_asset p
    FULL OUTER JOIN daily_benchmark_asset b 
                 ON p.as_of_date = b.as_of_date 
                AND p.asset_class = b.asset_class
    LEFT JOIN daily_portfolio_total pt ON COALESCE(p.as_of_date, b.as_of_date) = pt.as_of_date
    LEFT JOIN daily_benchmark_total bt ON COALESCE(p.as_of_date, b.as_of_date) = bt.as_of_date
),
daily_attribution AS (
    -- 6. 計算每日三因子歸因效應
    SELECT
        as_of_date,
        asset_class,
        w_p,
        w_b,
        r_p,
        r_b,
        
        -- 1. 配置效應 (Allocation): (w_p - w_b) * (r_b - R_B)
        (w_p - w_b) * (r_b - R_B) AS alloc_effect,
        
        -- 2. 選擇效應 (Selection): w_b * (r_p - r_b)
        w_b * (r_p - r_b) AS select_effect,
        
        -- 3. 交叉效應 (Interaction): (w_p - w_b) * (r_p - r_b)
        (w_p - w_b) * (r_p - r_b) AS interact_effect
    FROM daily_base_metrics
)
-- 7. 區間累加與最終結果輸出 (%)
SELECT
    :fid AS fund_id,
    :benchmark_id AS benchmark_id,
    CAST(:start_date AS DATE) AS start_date,
    CAST(:end_date AS DATE) AS end_date,
    asset_class,
    
    -- 平均持倉權重 (%)
    ROUND(AVG(w_p) * 100.0, 4) AS avg_w_p_pct,
    ROUND(AVG(w_b) * 100.0, 4) AS avg_w_b_pct,
    
    -- 年化/區間累計收益率估算 (%)
    ROUND(AVG(r_p) * 100.0, 4) AS avg_daily_r_p_pct,
    ROUND(AVG(r_b) * 100.0, 4) AS avg_daily_r_b_pct,
    
    -- 歸因拆解累計值 (%)
    ROUND(SUM(alloc_effect) * 100.0, 6) AS cumulative_allocation_effect_pct,
    ROUND(SUM(select_effect) * 100.0, 6) AS cumulative_selection_effect_pct,
    ROUND(SUM(interact_effect) * 100.0, 6) AS cumulative_interaction_effect_pct,
    
    -- 總超額收益 (%)
    ROUND(SUM(alloc_effect + select_effect + interact_effect) * 100.0, 6) AS total_excess_pct

FROM daily_attribution
GROUP BY asset_class
ORDER BY total_excess_pct DESC NULLS LAST;