-- ============================================================
-- 報表03 / 12_maturity_t1t5.sql
-- 原始：SmartReport/03/12.sql  T+1至T+5到期金額（億元）
-- 功能：SFC 每日/每週流動資產計算的原始數據
-- 參數：'2026-06-25'::DATE DATE
-- ============================================================

SELECT
    p.port_name,
    -- T+1（每日流動資產核心）
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE::DATE + 1) / 100000000, 4) AS t1_100m,
    -- T+2
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE::DATE + 2) / 100000000, 4) AS t2_100m,
    -- T+3
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE::DATE + 3) / 100000000, 4) AS t3_100m,
    -- T+4
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE::DATE + 4) / 100000000, 4) AS t4_100m,
    -- T+5（每週流動資產重要截止點）
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE::DATE + 5) / 100000000, 4) AS t5_100m
FROM (
    -- 債券（按市值計）
    SELECT b.port_id, b.maturity_date,
           COALESCE(b.market_value, 0) AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p2 ON p2.port_id = b.port_id
    WHERE p2.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.maturity_date >= '2026-06-25'::DATE
      AND b.maturity_date <= '2026-06-25'::DATE::DATE + 5

    UNION ALL

    -- 存款證
    SELECT c.port_id, c.maturity_date,
           COALESCE(c.market_value, c.price * c.quantity, 0)
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p2 ON p2.port_id = c.port_id
    WHERE p2.is_mmf = TRUE AND c.evaluate_date = '2026-06-25'::DATE
      AND c.maturity_date >= '2026-06-25'::DATE
      AND c.maturity_date <= '2026-06-25'::DATE::DATE + 5

    UNION ALL

    -- 定期存款
    SELECT d.port_id, d.maturity_date, COALESCE(d.principal, 0)
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p2 ON p2.port_id = d.port_id
    WHERE p2.is_mmf = TRUE AND d.evaluate_date = '2026-06-25'::DATE
      AND d.maturity_date >= '2026-06-25'::DATE
      AND d.maturity_date <= '2026-06-25'::DATE::DATE + 5

    UNION ALL

    -- 逆回購（融出，到期收回現金）
    SELECT r.port_id,
           COALESCE(r.actual_maturity_date, r.maturity_date) AS maturity_date,
           COALESCE(r.principal, 0)
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p2 ON p2.port_id = r.port_id
    WHERE p2.is_mmf = TRUE AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) >= '2026-06-25'::DATE
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= '2026-06-25'::DATE::DATE + 5

    UNION ALL

    -- 正回購（融入資金，到期還款，負值計入流動性計算）
    SELECT r.port_id,
           COALESCE(r.actual_maturity_date, r.maturity_date),
           -COALESCE(r.principal, 0)          -- 負號：融入資金到期需還款
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p2 ON p2.port_id = r.port_id
    WHERE p2.is_mmf = TRUE AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) >= '2026-06-25'::DATE
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= '2026-06-25'::DATE::DATE + 5
) t
JOIN fsi.para_portfolio p ON p.port_id = t.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
GROUP BY p.port_name
ORDER BY p.port_name;
