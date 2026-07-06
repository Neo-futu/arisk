-- report_04_mmf_monthly / 05_portfolio_chars.sql
-- 組合特點：提供基金風險和收益組成的關鍵指標，例如加權平均到期日、加權平均到期收益率等。
-- 業務邏輯：
--   1) 取指定評估日的組合 NAV
--   2) 取 MMF 专用指标中的 WAM/WAL
--   3) 計算各類持倉的到期收益率加權平均值，得到整體 YTM
--   4) 計算資產規模和持倉筆數，供報表顯示與風險提示使用
WITH
nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date = '2026-06-25'::DATE AND n.class_id IS NULL
),
holdings_ytm AS (
    SELECT b.port_id, COALESCE(b.market_value,0) AS mv, COALESCE(b.ytm,0) AS ytm
    FROM fsi.balance_bond b WHERE b.evaluate_date = '2026-06-25'::DATE AND b.quantity > 0
    UNION ALL
    SELECT c.port_id, COALESCE(c.market_value,0), COALESCE(c.ytm,0)
    FROM fsi.balance_cd c WHERE c.evaluate_date = '2026-06-25'::DATE
    UNION ALL
    SELECT d.port_id, COALESCE(d.principal,0),
           COALESCE(d.interest_rate,0) * 100
    FROM fsi.balance_deposit d WHERE d.evaluate_date = '2026-06-25'::DATE
    UNION ALL
    SELECT r.port_id, COALESCE(r.principal,0),
           COALESCE(r.interest_rate,0) * 100
    FROM fsi.balance_repo r WHERE r.evaluate_date = '2026-06-25'::DATE
        AND r.repo_type = 'REV_REPO'
),
agg AS (
    SELECT port_id,
           SUM(mv * ytm) / NULLIF(SUM(mv), 0) AS wtd_ytm,
           COUNT(*) AS total_count
    FROM holdings_ytm GROUP BY port_id
)
SELECT
    p.port_name,
    COALESCE(m.wam_days, 0)              AS wam_days,
    COALESCE(m.wal_days, 0)              AS wal_days,
    ROUND(COALESCE(a.wtd_ytm, 0), 4)    AS ytm_pct,
    ROUND(nav.net_asset / 1e8, 4)        AS nav_100m,
    COALESCE(a.total_count, 0)           AS total_count
FROM fsi.para_portfolio p
JOIN nav ON nav.port_id = p.port_id
LEFT JOIN fsi.balance_portfolio_mmf m ON m.port_id = p.port_id
    AND m.evaluate_date = '2026-06-25'::DATE
LEFT JOIN agg a ON a.port_id = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
