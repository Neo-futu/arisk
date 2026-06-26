-- ============================================================
-- 報表03 / 15_overnight_repo.sql
-- 原始：SmartReport/03/15.sql  隔夜正向回購查詢
-- 填入 Sheet：回购明细（A1=表頭，數據從 A2 開始）
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

SELECT
    r.port_id                                        AS port_id,
    p.port_name                                      AS port_name,
    r.market_id,
    r.repo_type,
    r.pledged_security_code                          AS security_code,
    ROUND(r.principal, 2)                            AS principal,
    ROUND(r.interest_rate * 100, 6)                 AS interest_rate_pct,
    r.value_date,
    COALESCE(r.actual_maturity_date, r.maturity_date) AS actual_maturity_date,
    ROUND(r.principal /
          NULLIF(n.net_asset, 0) * 100, 6)          AS ratio_to_nav,
    r.counterparty_name
FROM fsi.balance_repo r
JOIN fsi.para_portfolio p ON p.port_id = r.port_id
JOIN fsi.balance_portfolio_nav n ON n.port_id = r.port_id
    AND n.evaluate_date = r.evaluate_date
    AND n.class_id IS NULL
WHERE p.is_mmf = TRUE
  AND p.is_active = TRUE
  AND r.evaluate_date = '2026-06-25'::DATE
ORDER BY r.port_id, r.repo_type, r.counterparty_name;
