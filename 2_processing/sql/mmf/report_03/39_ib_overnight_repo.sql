-- ============================================================
-- 報表03 / 39_ib_overnight_repo.sql
-- 原始：SmartReport/03/39.sql  銀行間市場隔夜回購
-- 填入 Sheet：其他监控-sql导入数据（39.sql@A14，表頭A15，數據A16）
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

SELECT
    p.port_name,
    r.evaluate_date,
    COALESCE(r.actual_maturity_date, r.maturity_date) AS actual_maturity_date,
    r.counterparty_name,
    SUM(r.principal)                                   AS principal,
    ROUND(SUM(r.principal) /
          NULLIF(n.net_asset, 0) * 100, 6)            AS ratio_to_nav
FROM fsi.balance_repo r
JOIN fsi.para_portfolio p ON p.port_id = r.port_id
JOIN fsi.balance_portfolio_nav n ON n.port_id = r.port_id
    AND n.evaluate_date = r.evaluate_date
    AND n.class_id IS NULL
WHERE p.is_mmf = TRUE
  AND p.is_active = TRUE
  AND r.evaluate_date = '2026-06-25'::DATE
  AND r.repo_type = 'REV_REPO'          -- 逆回購（融出，資產方）
  AND r.market_id LIKE '%IB%'            -- 銀行間市場
GROUP BY p.port_name, r.evaluate_date,
         COALESCE(r.actual_maturity_date, r.maturity_date),
         r.counterparty_name, n.net_asset
ORDER BY p.port_name,
         COALESCE(r.actual_maturity_date, r.maturity_date),
         r.counterparty_name;
