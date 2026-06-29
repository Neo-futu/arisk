-- ============================================================
-- 報表03 / 11_sub_aaa_single_max.sql
-- 原始：SmartReport/03/11.sql  單一AAA以下機構發行的金融工具最大比率
-- Sheet：日报-sql导入数据，標籤11.sql@D60，表頭D61，數據D62
--
-- 欄位說明（對照模版表頭 D61-E61）：
--   组合                               = port_name（每組合一行）
--   单一AAA以下机构发行的金融工具最大比率 = max_ratio（單一發行人最大佔NAV比，%）
--
-- 邏輯：先按發行人彙總佔NAV比，再取各組合最大值（MAX）
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH issuer_detail AS (
    SELECT b.port_id,
           COALESCE(b.issuer_id, b.security_code) AS issuer_id,
           COALESCE(b.cost, 0) / NULLIF(n.net_asset, 0) * 100 AS cost_to_nav
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id = b.port_id
        AND n.evaluate_date = b.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(b.issuer_rating, 'NR') NOT IN ('AAA', 'AAA+')

    UNION ALL

    SELECT c.port_id,
           COALESCE(c.issuer_id, c.security_code),
           COALESCE(c.cost, 0) / NULLIF(n.net_asset, 0) * 100
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id = c.port_id
        AND n.evaluate_date = c.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(c.issuer_rating, 'NR') NOT IN ('AAA', 'AAA+')

    UNION ALL

    SELECT d.port_id,
           COALESCE(d.bank_id, d.deposit_id),
           COALESCE(d.principal, 0) / NULLIF(n.net_asset, 0) * 100
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id = d.port_id
        AND n.evaluate_date = d.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(d.bank_rating, 'NR') NOT IN ('AAA', 'AAA+')
),

issuer_sum AS (
    SELECT port_id, issuer_id,
           CAST(SUM(cost_to_nav) AS NUMERIC(16,2)) AS issuer_ratio
    FROM issuer_detail
    GROUP BY port_id, issuer_id
)

SELECT
    p.port_name,
    ROUND(MAX(s.issuer_ratio), 2) AS max_ratio   -- 單一AAA以下機構最大佔NAV比（%）
FROM issuer_sum s
JOIN fsi.para_portfolio p ON p.port_id = s.port_id
GROUP BY p.port_name
ORDER BY p.port_name;
