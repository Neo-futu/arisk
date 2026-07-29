-- atomic_weighted_valuation_ratios.sql
-- 原子指標：基金組合加權估值指標 (Weighted P/E, P/B, P/S)
-- 說明：
-- 1. 持倉來源：fsi.positions (fund_id, as_of_date, security_code, market_value_hkd)
-- 2. 估值來源：fsi.equity_valuation (security_code, as_of_date, pe_ratio, pb_ratio, ps_ratio)
-- 3. 計算算法：
--    - 加權算術平均數 (Weighted Arithmetic Mean): Sum(w_i * Ratio_i) / Sum(w_i)
--    - 加權調和平均數 (Weighted Harmonic Mean， Morningstar/國際標準): Sum(w_i) / Sum(w_i / Ratio_i)

WITH raw_positions AS (
    -- 1. 取得基準日有效多頭持倉，並處理標的代碼備用
    SELECT
        fund_id,
        as_of_date,
        COALESCE(security_code, wind_code, ticker) AS security_code,
        COALESCE(market_value_hkd, 0.0) AS market_value_hkd
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = CAST(:as_of_date AS DATE)
      AND COALESCE(market_value_hkd, 0.0) > 0.0
),
latest_positions AS (
    -- 2. 計算各標的在總股票權重中的佔比 (Portfolio Weight)
    SELECT
        fund_id,
        as_of_date,
        security_code,
        market_value_hkd,
        market_value_hkd / NULLIF(SUM(market_value_hkd) OVER (PARTITION BY fund_id), 0.0) AS weight
    FROM raw_positions
),
valuation_joined AS (
    -- 3. 關聯股票估值數據表
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.weight,
        v.pe_ratio,
        v.pb_ratio,
        v.ps_ratio
    FROM latest_positions p
    LEFT JOIN fsi.equity_valuation v 
           ON p.security_code = v.security_code 
          AND p.as_of_date = v.as_of_date
),
valid_weights AS (
    -- 4. 篩選有效估值數據（排除負值、零值與 NULL），並記錄各指標之有效權重
    SELECT
        fund_id,
        as_of_date,
        security_code,
        weight,
        pe_ratio,
        pb_ratio,
        ps_ratio,
        
        -- P/E 有效性判斷 (虧損企業 P/E <= 0 不納入調和/算術平均計算)
        CASE WHEN pe_ratio IS NOT NULL AND pe_ratio > 0.0 THEN weight ELSE 0.0 END AS w_pe_valid,
        
        -- P/B 有效性判斷 (資不抵債/淨資產為負者 P/B <= 0 排除)
        CASE WHEN pb_ratio IS NOT NULL AND pb_ratio > 0.0 THEN weight ELSE 0.0 END AS w_pb_valid,
        
        -- P/S 有效性判斷
        CASE WHEN ps_ratio IS NOT NULL AND ps_ratio > 0.0 THEN weight ELSE 0.0 END AS w_ps_valid
    FROM valuation_joined
),
aggregated_ratios AS (
    -- 5. 彙整加權算術與調和分子分母
    SELECT
        fund_id,
        as_of_date,
        SUM(weight) AS total_portfolio_weight,
        
        -- 1) 市盈率 (P/E)
        SUM(w_pe_valid) AS weight_pe_coverage,
        SUM(CASE WHEN pe_ratio > 0.0 THEN weight * pe_ratio ELSE 0.0 END) AS pe_arithmetic_sum,
        SUM(CASE WHEN pe_ratio > 0.0 THEN weight / pe_ratio ELSE 0.0 END) AS pe_harmonic_sum,
        
        -- 2) 市淨率 (P/B)
        SUM(w_pb_valid) AS weight_pb_coverage,
        SUM(CASE WHEN pb_ratio > 0.0 THEN weight * pb_ratio ELSE 0.0 END) AS pb_arithmetic_sum,
        SUM(CASE WHEN pb_ratio > 0.0 THEN weight / pb_ratio ELSE 0.0 END) AS pb_harmonic_sum,
        
        -- 3) 市銷率 (P/S)
        SUM(w_ps_valid) AS weight_ps_coverage,
        SUM(CASE WHEN ps_ratio > 0.0 THEN weight * ps_ratio ELSE 0.0 END) AS ps_arithmetic_sum,
        SUM(CASE WHEN ps_ratio > 0.0 THEN weight / ps_ratio ELSE 0.0 END) AS ps_harmonic_sum
    FROM valid_weights
    GROUP BY fund_id, as_of_date
)
SELECT
    fund_id,
    as_of_date,
    
    -- 有效估值覆蓋率 (%)
    ROUND(weight_pe_coverage * 100.0, 4) AS pe_coverage_pct,
    ROUND(weight_pb_coverage * 100.0, 4) AS pb_coverage_pct,
    ROUND(weight_ps_coverage * 100.0, 4) AS ps_coverage_pct,
    
    -- 1. 市盈率 (P/E)
    ROUND(pe_arithmetic_sum / NULLIF(weight_pe_coverage, 0.0), 4) AS weighted_pe_arithmetic,
    ROUND(weight_pe_coverage / NULLIF(pe_harmonic_sum, 0.0), 4) AS weighted_pe_harmonic,
    
    -- 2. 市淨率 (P/B)
    ROUND(pb_arithmetic_sum / NULLIF(weight_pb_coverage, 0.0), 4) AS weighted_pb_arithmetic,
    ROUND(weight_pb_coverage / NULLIF(pb_harmonic_sum, 0.0), 4) AS weighted_pb_harmonic,
    
    -- 3. 市銷率 (P/S)
    ROUND(ps_arithmetic_sum / NULLIF(weight_ps_coverage, 0.0), 4) AS weighted_ps_arithmetic,
    ROUND(weight_ps_coverage / NULLIF(ps_harmonic_sum, 0.0), 4) AS weighted_ps_harmonic

FROM aggregated_ratios;