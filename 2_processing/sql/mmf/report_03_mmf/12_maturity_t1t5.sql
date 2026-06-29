-- ============================================================
-- 報表03 / 12_maturity_t1t5.sql
-- 原始：SmartReport/03/12.sql  未来净流入现金流（短期，T+1~T+5）
-- Sheet：日报-sql导入数据，標籤12.sql@E94，表頭E95，數據E96
--
-- 欄位說明（對照模版表頭 E95-J95）：
--   未来净流入现金流 = port_name（組合名）
--   T+1 ~ T+5 净流入金额（亿元） = 各期累計淨流入
--
-- 計算邏輯：
--   CUMULATIVE（累計）：T+2列包含T+1的資產（MaturityDate <= T+N）
--   正值：債券/CD/存款到期回款 + 逆回購融出到期收回（正）
--   負值：正回購融入到期還款（負）
--   債券/CD：使用市值（Price×Quantity）
--   存款：使用本金（Principal）
--   逆回購：使用 Principal
--   交易所逆回購：到期日額外+1個交易日（簡化為+1日曆日）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

SELECT
    p.port_name,
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE + 1) / 100000000, 4) AS t1_100m,
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE + 2) / 100000000, 4) AS t2_100m,
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE + 3) / 100000000, 4) AS t3_100m,
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE + 4) / 100000000, 4) AS t4_100m,
    ROUND(SUM(mv) FILTER (WHERE maturity_date <= '2026-06-25'::DATE + 5) / 100000000, 4) AS t5_100m
FROM (
    -- 債券（市值 = Price × Quantity）
    SELECT b.port_id, b.maturity_date,
           COALESCE(b.market_value, 0) AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p2 ON p2.port_id = b.port_id
    WHERE p2.is_mmf = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.maturity_date >= '2026-06-25'::DATE
      AND b.maturity_date <= '2026-06-25'::DATE + 5

    UNION ALL

    -- 存款證（市值）
    SELECT c.port_id, c.maturity_date,
           COALESCE(c.market_value, 0)
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p2 ON p2.port_id = c.port_id
    WHERE p2.is_mmf = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND c.maturity_date >= '2026-06-25'::DATE
      AND c.maturity_date <= '2026-06-25'::DATE + 5

    UNION ALL

    -- 定期存款（本金）
    SELECT d.port_id, d.maturity_date,
           COALESCE(d.principal, 0)
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p2 ON p2.port_id = d.port_id
    WHERE p2.is_mmf = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND d.maturity_date >= '2026-06-25'::DATE
      AND d.maturity_date <= '2026-06-25'::DATE + 5

    UNION ALL

    -- 逆回購（融出到期收回，正值）
    -- 交易所逆回購到期日+1日（源SQL：MarketId in '005002','005003'加1交易日）
    SELECT r.port_id,
           CASE WHEN r.market_id IN ('EXCH_SZ','EXCH_SH')
                THEN COALESCE(r.actual_maturity_date, r.maturity_date) + 1
                ELSE COALESCE(r.actual_maturity_date, r.maturity_date)
           END AS maturity_date,
           COALESCE(r.principal, 0)
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p2 ON p2.port_id = r.port_id
    WHERE p2.is_mmf = TRUE
      AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) >= '2026-06-25'::DATE
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= '2026-06-25'::DATE + 5

    UNION ALL

    -- 正回購（融入到期還款，負值）
    SELECT r.port_id,
           COALESCE(r.actual_maturity_date, r.maturity_date),
           -COALESCE(r.principal, 0)
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p2 ON p2.port_id = r.port_id
    WHERE p2.is_mmf = TRUE
      AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) >= '2026-06-25'::DATE
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= '2026-06-25'::DATE + 5
) t
JOIN fsi.para_portfolio p ON p.port_id = t.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
GROUP BY p.port_name
ORDER BY p.port_name;
