-- report_04_mmf_monthly / 06_asset_allocation.sql
-- 資產類別分佈（使用英文標籤，避免編碼問題）
WITH
nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date = '2026-06-25'::DATE AND n.class_id IS NULL
),
raw AS (
    SELECT a.port_id,
           a.asset_class::TEXT AS asset_class,
           a.asset_class::TEXT AS asset_class_label,
           SUM(a.market_value) AS mv_sum
    FROM fsi.balance_portfolio_asset a
    WHERE a.evaluate_date = '2026-06-25'::DATE
    GROUP BY a.port_id, a.asset_class
)
SELECT
    p.port_name,
    r.asset_class,
    -- 中文標籤在模版/PDF 層處理，SQL 只出英文代碼保證兼容性
    CASE r.asset_class
        WHEN 'CASH'      THEN 'Cash'
        WHEN 'DEPOSIT'   THEN 'Time Deposit'
        WHEN 'CD'        THEN 'Certificate of Deposit'
        WHEN 'BOND_GOVT' THEN 'Govt/Public Bond'
        WHEN 'BOND_CORP' THEN 'Credit Bond'
        WHEN 'REPO'      THEN 'Reverse Repo'
        ELSE r.asset_class
    END AS asset_class_en,
    ROUND(r.mv_sum / 1e8, 6)                              AS mv_100m,
    ROUND(r.mv_sum / NULLIF(n.net_asset, 0) * 100, 4)    AS pct_nav
FROM raw r
JOIN fsi.para_portfolio p ON p.port_id = r.port_id
JOIN nav n ON n.port_id = r.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name, pct_nav DESC;
