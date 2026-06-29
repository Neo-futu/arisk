-- ============================================================
-- 報表03 / 09_sub_aaa_total.sql
-- 原始：SmartReport/03/09.sql  AAA以下機構發行的存款存單債券合計
-- Sheet：日报-sql导入数据，標籤09.sql@A60，表頭A61，數據A62
--
-- 欄位說明（對照模版表頭 A61-C61）：
--   组合                               = port_name（每組合一行）
--   AAA以下机构发行的存款、存单、债券  = mv（市值合計，億元）
--   比率                               = ratio（Cost/NAV×100，%）
--
-- 篩選：發行人評級 NOT IN ('AAA','AAA+')（近12個月最新評級）
-- 用途：監控非高評級機構的持倉集中度
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH sub_aaa AS (
    -- 債券（評級 < AAA）
    SELECT b.port_id, b.security_code, b.security_name,
           COALESCE(b.cost, 0)                           AS cost,
           COALESCE(b.market_value, 0)                   AS mv,
           COALESCE(b.cost, 0) / NULLIF(n.net_asset, 0) * 100 AS cost_to_nav
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id = b.port_id
        AND n.evaluate_date = b.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(b.issuer_rating, 'NR') NOT IN ('AAA', 'AAA+')

    UNION ALL

    -- 存款證（評級 < AAA）
    SELECT c.port_id, c.security_code, c.security_name,
           COALESCE(c.cost, 0),
           COALESCE(c.market_value, 0),
           COALESCE(c.cost, 0) / NULLIF(n.net_asset, 0) * 100
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id = c.port_id
        AND n.evaluate_date = c.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(c.issuer_rating, 'NR') NOT IN ('AAA', 'AAA+')

    UNION ALL

    -- 存款（銀行評級 < AAA）
    SELECT d.port_id, d.deposit_id, d.deposit_name,
           COALESCE(d.principal, 0),
           COALESCE(d.principal, 0),
           COALESCE(d.principal, 0) / NULLIF(n.net_asset, 0) * 100
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    JOIN fsi.balance_portfolio_nav n ON n.port_id = d.port_id
        AND n.evaluate_date = d.evaluate_date AND n.class_id IS NULL
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(d.bank_rating, 'NR') NOT IN ('AAA', 'AAA+')
)

SELECT
    p.port_name,
    ROUND(SUM(s.mv) / 100000000, 4)                    AS mv,     -- AAA以下市值（億）
    ROUND(CAST(SUM(s.cost_to_nav) AS NUMERIC), 2)      AS ratio   -- 佔NAV比（%）
FROM sub_aaa s
JOIN fsi.para_portfolio p ON p.port_id = s.port_id
GROUP BY p.port_name
ORDER BY p.port_name;
