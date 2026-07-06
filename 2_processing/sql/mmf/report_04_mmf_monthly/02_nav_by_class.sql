-- report_04_mmf_monthly / 02_nav_by_class.sql
-- 各股份類別資產淨值：用於報表中按份額類別顯示 NAV 與在外流通單位。
-- 業務邏輯：
--   1) 以指定評估日的 NAV 數據為基準
--   2) 若 class_id 為 NULL，則視為 Base 類別
--   3) 計算每股淨值、總 NAV 及估算在外單位數量
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
