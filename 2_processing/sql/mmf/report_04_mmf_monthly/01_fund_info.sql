-- report_04_mmf_monthly / 01_fund_info.sql
-- 基金基本資料：為 Factsheet 提供組合整體規模與主要風險收益指標。
-- 這裡的業務含義是：
--   1) 取 MMF 基金主檔資訊（活躍貨幣基金）
--   2) 取指定評估日的組合淨資產 NAV
--   3) 取同一天的加權平均到期日 WAM、加權平均到期收益率 WAL、7日年化收益
-- 4) NAV 以 1 億港元為單位輸出，便於報表展示。
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
