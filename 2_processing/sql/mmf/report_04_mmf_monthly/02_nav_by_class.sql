-- report_04_mmf_monthly / 02_nav_by_class.sql
-- 各股份類別每股資產淨值（unit_nav）
SELECT
    p.port_name,
    COALESCE(n.class_id::TEXT, 'Base')        AS class_id,
    ROUND(COALESCE(n.unit_nav, 0), 4)         AS nav_per_unit,
    ROUND(n.net_asset, 2)                      AS nav_total,
    ROUND(CASE WHEN COALESCE(n.unit_nav, 0) > 0
               THEN n.net_asset / n.unit_nav ELSE 0 END, 0) AS outstanding_units,
    n.evaluate_date
FROM fsi.para_portfolio p
JOIN fsi.balance_portfolio_nav n ON n.port_id = p.port_id
    AND n.evaluate_date = '2026-06-25'::DATE
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name, n.class_id NULLS LAST;
