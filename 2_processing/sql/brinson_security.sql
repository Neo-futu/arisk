-- brinson_security.sql
-- 單券層面 Brinson 歸因

WITH p_sec AS (
    SELECT
        fund_id,
        COALESCE(security_code, instrument_id, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        SUM(market_value_hkd) AS mv_p,
        SUM(pnl_hkd) AS pnl_p
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN :start_date AND :end_date
    GROUP BY fund_id, COALESCE(security_code, instrument_id, 'UNKNOWN'), COALESCE(security_name, 'UNNAMED')
),
b_sec AS (
    SELECT
        benchmark_id,
        COALESCE(security_code, instrument_id, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        SUM(market_value_hkd) AS mv_b,
        SUM(pnl_hkd) AS pnl_b
    FROM fsi.benchmark_positions
    WHERE benchmark_id = :benchmark_id
      AND as_of_date BETWEEN :start_date AND :end_date
    GROUP BY benchmark_id, COALESCE(security_code, instrument_id, 'UNKNOWN'), COALESCE(security_name, 'UNNAMED')
),
totals AS (
    SELECT
        NULLIF(SUM(mv_p), 0) AS total_mv_p,
        NULLIF(SUM(mv_b), 0) AS total_mv_b
    FROM p_sec FULL OUTER JOIN b_sec ON p_sec.security_code = b_sec.security_code
),
base_metrics AS (
    SELECT
        COALESCE(p.security_code, b.security_code) AS security_code,
        COALESCE(p.security_name, b.security_name) AS security_name,
        COALESCE(p.mv_p, 0.0) / t.total_mv_p AS w_p,
        COALESCE(b.mv_b, 0.0) / t.total_mv_b AS w_b,
        CASE WHEN COALESCE(p.mv_p, 0) = 0 THEN 0.0 ELSE p.pnl_p / p.mv_p END AS r_p,
        CASE WHEN COALESCE(b.mv_b, 0) = 0 THEN 0.0 ELSE b.pnl_b / b.mv_b END AS r_b
    FROM p_sec p
    FULL OUTER JOIN b_sec b ON p.security_code = b.security_code
    CROSS JOIN totals t
)
SELECT
    :fid AS fund_id,
    :benchmark_id AS benchmark_id,
    :start_date AS start_date,
    :end_date AS end_date,
    security_code,
    security_name,
    ROUND(w_p, 6) AS w_p,
    ROUND(w_b, 6) AS w_b,
    ROUND(r_p, 6) AS r_p,
    ROUND(r_b, 6) AS r_b,
    -- 1. 配置收益 (%) = (w_p - w_b) * r_b * 100
    ROUND(((w_p - w_b) * r_b) * 100.0, 6) AS allocation_effect_pct,
    -- 2. 選擇收益 (%) = w_b * (r_p - r_b) * 100
    ROUND((w_b * (r_p - r_b)) * 100.0, 6) AS selection_effect_pct,
    -- 3. 交叉收益 (%) = (w_p - w_b) * (r_p - r_b) * 100
    ROUND(((w_p - w_b) * (r_p - r_b)) * 100.0, 6) AS interaction_effect_pct,
    -- 4. 超額收益 (%)
    ROUND((((w_p - w_b) * r_b) + (w_b * (r_p - r_b)) + ((w_p - w_b) * (r_p - r_b))) * 100.0, 6) AS total_excess_pct
FROM base_metrics
ORDER BY total_excess_pct DESC NULLS LAST;