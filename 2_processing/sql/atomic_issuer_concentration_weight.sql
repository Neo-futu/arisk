-- atomic_issuer_concentration_weight.sql
-- 原子指標：發行人集中度 (%)

WITH position_summary AS (
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(issuer_id, issuer_name, 'UNKNOWN_ISSUER') AS issuer_id,
        COALESCE(issuer_name, 'UNKNOWN_ISSUER') AS issuer_name,
        SUM(COALESCE(market_value_base, market_value, 0.0)) AS issuer_mv_hkd,
        SUM(SUM(COALESCE(market_value_base, market_value, 0.0))) OVER (PARTITION BY port_id, evaluate_date) AS total_nav
    FROM fsi.balance_bond
    WHERE port_id = :fid
      AND evaluate_date = :end_date
    GROUP BY 
        port_id, 
        evaluate_date, 
        COALESCE(issuer_id, issuer_name, 'UNKNOWN_ISSUER'), 
        COALESCE(issuer_name, 'UNKNOWN_ISSUER')
)
SELECT
    fund_id,
    as_of_date,
    issuer_id,
    issuer_name,
    issuer_mv_hkd,
    total_nav,
    -- 發行人集中度 (%) = (單一發行人總市值 / 總持倉市值 NAV) * 100
    CASE
        WHEN total_nav IS NULL OR total_nav = 0 THEN NULL
        ELSE ROUND((issuer_mv_hkd / total_nav) * 100.0, 6)
    END AS concentration_pct
FROM position_summary
ORDER BY concentration_pct DESC NULLS LAST;
