-- report_04_mmf_monthly / 01_fund_info.sql
-- 基金基本資料：規模、WAM/WAL、7日年化
SELECT
    p.port_name,
    p.base_currency,
    ROUND(n.net_asset / 100000000.0, 4)       AS nav_total_100m,
    COALESCE(m.wam_days, 0)                   AS wam_days,
    COALESCE(m.wal_days, 0)                   AS wal_days,
    COALESCE(m.return_rate_7d, 0)             AS return_7d_ann,
    '2026-06-25'::DATE                         AS evaluate_date
FROM fsi.para_portfolio p
JOIN fsi.balance_portfolio_nav n ON n.port_id = p.port_id
    AND n.evaluate_date = '2026-06-25'::DATE AND n.class_id IS NULL
LEFT JOIN fsi.balance_portfolio_mmf m ON m.port_id = p.port_id
    AND m.evaluate_date = '2026-06-25'::DATE
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
