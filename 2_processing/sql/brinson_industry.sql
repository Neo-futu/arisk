-- brinson_industry.sql
-- 行業層面 Brinson 歸因

WITH p_industry AS (
    SELECT
        fund_id,
        COALESCE(industry, sector, 'UNCLASSIFIED') AS industry_name,
        SUM(market_value_hkd) AS mv_p,
        SUM(pnl_hkd) AS pnl_p
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN :start_date AND :end_date
    GROUP BY fund_id, COALESCE(industry, sector, 'UNCLASSIFIED')
),
b_industry AS (
    SELECT
        benchmark_id,
        COALESCE(industry, sector, 'UNCLASSIFIED') AS industry_name,
        SUM(market_value_hkd) AS mv_b,
        SUM(pnl_hkd) AS pnl_b
    FROM fsi.benchmark_positions
    WHERE benchmark_id = :benchmark_id
      AND as_of_date BETWEEN :start_date AND :end_date
    GROUP BY benchmark_id, COALESCE(industry, sector, 'UNCLASSIFIED')
),
totals AS (
    SELECT
        NULLIF(SUM(mv_p), 0) AS total_mv_p,
        NULLIF(SUM(mv_b), 0) AS total_mv_b
    FROM p_industry FULL OUTER JOIN b_industry ON p_industry.industry_name = b_industry.industry_name
),
base_metrics AS (
    SELECT
        COALESCE(p.industry_name, b.industry_name) AS industry_name,
        COALESCE(p.mv_p, 0.0) / t.total_mv_p AS w_p,
        COALESCE(b.mv_b, 0.0) / t.total_mv_b AS w_b,
        CASE WHEN COALESCE(p.mv_p, 0) = 0 THEN 0.0 ELSE p.pnl_p / p.mv_p END AS r_p,
        CASE WHEN COALESCE(b.mv_b, 0) = 0 THEN 0.0 ELSE b.pnl_b / b.mv_b END AS r_b
    FROM p_industry p
    FULL OUTER JOIN b_industry b ON p.industry_name = b.industry_name
    CROSS JOIN totals t
)
SELECT
    :fid AS fund_id,
    :benchmark_id AS benchmark_id,
    :start_date AS start_date,
    :end_date AS end_date,
    industry_name,
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