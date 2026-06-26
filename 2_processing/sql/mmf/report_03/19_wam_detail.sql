-- ============================================================
-- 報表03 / 19_wam_detail.sql
-- 原始：SmartReport/03/19.sql  利率債/信用債/存單加權平均剩餘期限
-- 填入 Sheet：其他监控-sql导入数据（19.sql@D2，表頭D3，數據D4）
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH bond_cd AS (
    SELECT b.port_id,
           b.security_code,
           b.remaining_days                         AS rem_days,
           COALESCE(b.weight_pct, 0)               AS ratio_to_nav
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.remaining_days > 0

    UNION ALL

    SELECT c.port_id,
           c.security_code,
           c.remaining_days,
           COALESCE(c.weight_pct, 0)
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND c.remaining_days > 0
),

summary AS (
    SELECT port_id,
           SUM(ratio_to_nav)               AS total_ratio,
           SUM(ratio_to_nav * rem_days)    AS weighted_days
    FROM bond_cd
    GROUP BY port_id
)

SELECT
    p.port_name,
    ROUND(s.weighted_days / NULLIF(s.total_ratio, 0), 2) AS wam_days
FROM summary s
JOIN fsi.para_portfolio p ON p.port_id = s.port_id
ORDER BY p.port_name;
