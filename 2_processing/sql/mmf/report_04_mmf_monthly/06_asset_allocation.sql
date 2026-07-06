-- report_04_mmf_monthly / 06_asset_allocation.sql
-- 資產類別分佈：計算不同資產類別在基金 NAV 中的權重，用於資產配置圖表。
-- 業務含義：
--   1) 以評估日的資產持倉市值為基礎
--   2) 按資產類別匯總市值
--   3) 轉換為英文標籤，以避免報表層中文編碼兼容性問題
--   4) 計算各類資產佔 NAV 比例，顯示基金的風險資產配置
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
