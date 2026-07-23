-- atomic_weighted_valuation_ratios.sql
-- 基金組合加權估值指標：加權市盈率 (P/E)、加權市淨率 (P/B)、加權市銷率 (P/S)
-- 提供加權調和平均數 (Weighted Harmonic Mean，國際標準/ Morningstar 採用的去異常值算子) 
-- 與加權算術平均數 (Weighted Arithmetic Mean) 兩套指標

WITH latest_positions AS (
    -- 取得指定基準日 (:as_of_date) 之持倉與權重
    SELECT
        fund_id,
        as_of_date,
        security_code,
        security_name,
        COALESCE(market_value_hkd, 0.0) AS market_value_hkd,
        market_value_hkd / NULLIF(SUM(market_value_hkd) OVER (PARTITION BY fund_id), 0) AS weight
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
      AND market_value_hkd > 0
),
valuation_joined AS (
    -- 關聯股票估值數據表
    SELECT
        p.fund_id,
        p.as_of_date,
        p.security_code,
        p.security_name,
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
    -- 分別計算有效估值數據的累計權重（用於重新歸一化）
    SELECT
        fund_id,
        as_of_date,
        security_code,
        security_name,
        weight,
        pe_ratio,
        pb_ratio,
        ps_ratio,
        -- P/E 有效性條件 (排除虧損/異常負值)
        CASE WHEN pe_ratio > 0 THEN weight ELSE 0.0 END AS w_pe_valid,
        -- P/B 有效性條件
        CASE WHEN pb_ratio > 0 THEN weight ELSE 0.0 END AS w_pb_valid,
        -- P/S 有效性條件
        CASE WHEN ps_ratio > 0 THEN weight ELSE 0.0 END AS w_ps_valid
    FROM valuation_joined
),
aggregated_ratios AS (
    SELECT
        fund_id,
        as_of_date,
        SUM(weight) AS total_portfolio_weight,
        
        -- 1. 市盈率 (P/E)
        SUM(w_pe_valid) AS weight_pe_coverage,
        SUM(CASE WHEN pe_ratio > 0 THEN weight * pe_ratio ELSE 0.0 END) AS pe_arithmetic_sum,
        SUM(CASE WHEN pe_ratio > 0 THEN weight / pe_ratio ELSE 0.0 END) AS pe_harmonic_sum,
        
        -- 2. 市淨率 (P/B)
        SUM(w_pb_valid) AS weight_pb_coverage,
        SUM(CASE WHEN pb_ratio > 0 THEN weight * pb_ratio ELSE 0.0 END) AS pb_arithmetic_sum,
        SUM(CASE WHEN pb_ratio > 0 THEN weight / pb_ratio ELSE 0.0 END) AS pb_harmonic_sum,
        
        -- 3. 市銷率 (P/S)
        SUM(w_ps_valid) AS weight_ps_coverage,
        SUM(CASE WHEN ps_ratio > 0 THEN weight * ps_ratio ELSE 0.0 END) AS ps_arithmetic_sum,
        SUM(CASE WHEN ps_ratio > 0 THEN weight / ps_ratio ELSE 0.0 END) AS ps_harmonic_sum
    FROM valid_weights
    GROUP BY fund_id, as_of_date
)
SELECT
    fund_id,
    as_of_date,
    
    -- 覆蓋率 (%)
    ROUND(weight_pe_coverage * 100.0, 4) AS pe_coverage_pct,
    ROUND(weight_pb_coverage * 100.0, 4) AS pb_coverage_pct,
    ROUND(weight_ps_coverage * 100.0, 4) AS ps_coverage_pct,
    
    -- 1. 市盈率 (P/E)
    ROUND(pe_arithmetic_sum / NULLIF(weight_pe_coverage, 0), 4) AS weighted_pe_arithmetic,
    ROUND(weight_pe_coverage / NULLIF(pe_harmonic_sum, 0), 4) AS weighted_pe_harmonic,
    
    -- 2. 市淨率 (P/B)
    ROUND(pb_arithmetic_sum / NULLIF(weight_pb_coverage, 0), 4) AS weighted_pb_arithmetic,
    ROUND(weight_pb_coverage / NULLIF(pb_harmonic_sum, 0), 4) AS weighted_pb_harmonic,
    
    -- 3. 市銷率 (P/S)
    ROUND(ps_arithmetic_sum / NULLIF(weight_ps_coverage, 0), 4) AS weighted_ps_arithmetic,
    ROUND(weight_ps_coverage / NULLIF(ps_harmonic_sum, 0), 4) AS weighted_ps_harmonic
FROM aggregated_ratios;