-- ============================================================
-- 報表03 / 40_sub_aaa_detail.sql
-- 原始：SmartReport/03/40.sql  AAA以下機構明細
-- Sheet：日报-sql导入数据 @ F62
-- ============================================================

WITH detail AS (
    SELECT b.port_id,
           COALESCE(b.issuer_name, b.issuer_id) AS issuer_name,
           b.asset_subtype::TEXT                AS security_type,
           COALESCE(b.cost,0) / NULLIF(n.net_asset,0) * 100 AS cost_to_nav,
           COALESCE(b.cost,0) AS cost
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id=b.port_id
        AND n.evaluate_date=b.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf=TRUE AND p.is_active=TRUE
      AND b.evaluate_date='2026-06-25'::DATE
      AND COALESCE(b.issuer_rating,'NR') NOT IN ('AAA','AAA+')

    UNION ALL

    SELECT c.port_id,
           COALESCE(c.issuer_name, c.issuer_id),
           'CD',
           COALESCE(c.cost,0) / NULLIF(n.net_asset,0) * 100,
           COALESCE(c.cost,0)
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id=c.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id=c.port_id
        AND n.evaluate_date=c.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf=TRUE AND p.is_active=TRUE
      AND c.evaluate_date='2026-06-25'::DATE
      AND COALESCE(c.issuer_rating,'NR') NOT IN ('AAA','AAA+')

    UNION ALL

    SELECT d.port_id,
           COALESCE(d.bank_name, d.bank_id),
           '定期存款',
           COALESCE(d.principal,0) / NULLIF(n.net_asset,0) * 100,
           COALESCE(d.principal,0)
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id=d.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id=d.port_id
        AND n.evaluate_date=d.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf=TRUE AND p.is_active=TRUE
      AND d.evaluate_date='2026-06-25'::DATE
      AND COALESCE(d.bank_rating,'NR') NOT IN ('AAA','AAA+')
),

grouped AS (
    SELECT port_id, issuer_name,
           -- 辅助：列出該發行人持有的品種（替代源 SQL 的'none'佔位符）
           STRING_AGG(DISTINCT security_type, '/' ORDER BY security_type) AS aux,
           CAST(SUM(cost_to_nav) AS NUMERIC(16,2)) AS ratio,
           SUM(cost) AS cost
    FROM detail
    GROUP BY port_id, issuer_name
)

SELECT
    p.port_name,
    g.issuer_name,
    g.aux,      -- 辅助：持有品種（如 BOND_CORP/CD）
    g.ratio,    -- 比率（%）
    g.cost      -- 市值（元）
FROM grouped g
JOIN fsi.para_portfolio p ON p.port_id=g.port_id
ORDER BY p.port_name, g.ratio DESC;
