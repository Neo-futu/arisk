-- report_04_mmf_monthly / 03_performance.sql
-- 累積業績：1M/3M/6M/1Y/自成立/年化/7日年化（使用 unit_nav）
WITH
nav_t AS (
    SELECT n.port_id, n.class_id, n.unit_nav, n.evaluate_date
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date = '2026-06-25'::DATE
),
nav_1m AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date BETWEEN '2026-06-25'::DATE - 40 AND '2026-06-25'::DATE - 25
    ORDER BY n.port_id, n.class_id, n.evaluate_date DESC
),
nav_3m AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date BETWEEN '2026-06-25'::DATE - 100 AND '2026-06-25'::DATE - 85
    ORDER BY n.port_id, n.class_id, n.evaluate_date DESC
),
nav_6m AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date BETWEEN '2026-06-25'::DATE - 195 AND '2026-06-25'::DATE - 175
    ORDER BY n.port_id, n.class_id, n.evaluate_date DESC
),
nav_1y AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date BETWEEN '2026-06-25'::DATE - 380 AND '2026-06-25'::DATE - 355
    ORDER BY n.port_id, n.class_id, n.evaluate_date DESC
),
nav_ytd AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date >= DATE_TRUNC('year', '2026-06-25'::DATE)::DATE
      AND n.evaluate_date <= DATE_TRUNC('year', '2026-06-25'::DATE)::DATE + 5
    ORDER BY n.port_id, n.class_id, n.evaluate_date ASC
),
nav_incept AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav, n.evaluate_date AS incept_date
    FROM fsi.balance_portfolio_nav n
    JOIN fsi.para_portfolio p ON p.port_id = n.port_id
    WHERE p.is_mmf = TRUE
    ORDER BY n.port_id, n.class_id, n.evaluate_date ASC
),
mmf_yield AS (
    SELECT m.port_id, m.return_rate_7d
    FROM fsi.balance_portfolio_mmf m
    WHERE m.evaluate_date = '2026-06-25'::DATE
)
SELECT
    p.port_name,
    COALESCE(t.class_id::TEXT, 'Base')          AS class_id,
    ROUND((t.unit_nav / NULLIF(m1.unit_nav, 0) - 1) * 100, 4)  AS perf_1m,
    ROUND((t.unit_nav / NULLIF(m3.unit_nav, 0) - 1) * 100, 4)  AS perf_3m,
    ROUND((t.unit_nav / NULLIF(m6.unit_nav, 0) - 1) * 100, 4)  AS perf_6m,
    ROUND((t.unit_nav / NULLIF(y1.unit_nav, 0) - 1) * 100, 4)  AS perf_1y,
    ROUND((t.unit_nav / NULLIF(inc.unit_nav, 0) - 1) * 100, 4) AS perf_since_incept,
    CASE
        WHEN inc.unit_nav > 0 AND (t.evaluate_date - inc.incept_date) > 0
        THEN ROUND((POWER(t.unit_nav::NUMERIC / NULLIF(inc.unit_nav, 0),
                    365.0 / NULLIF((t.evaluate_date - inc.incept_date), 0)) - 1) * 100, 4)
        ELSE NULL
    END AS perf_ann_since_incept,
    COALESCE(my.return_rate_7d, 0)              AS return_7d_ann,
    inc.incept_date,
    ROUND((t.unit_nav / NULLIF(ytd.unit_nav, 0) - 1) * 100, 4) AS perf_ytd,
    t.evaluate_date,
    ROUND((t.evaluate_date - inc.incept_date)::NUMERIC / 365, 2) AS years_since_incept
FROM fsi.para_portfolio p
JOIN nav_t   t   ON t.port_id = p.port_id
LEFT JOIN nav_1m  m1  ON m1.port_id = p.port_id  AND m1.class_id  IS NOT DISTINCT FROM t.class_id
LEFT JOIN nav_3m  m3  ON m3.port_id = p.port_id  AND m3.class_id  IS NOT DISTINCT FROM t.class_id
LEFT JOIN nav_6m  m6  ON m6.port_id = p.port_id  AND m6.class_id  IS NOT DISTINCT FROM t.class_id
LEFT JOIN nav_1y  y1  ON y1.port_id = p.port_id  AND y1.class_id  IS NOT DISTINCT FROM t.class_id
LEFT JOIN nav_ytd ytd ON ytd.port_id = p.port_id AND ytd.class_id IS NOT DISTINCT FROM t.class_id
LEFT JOIN nav_incept inc ON inc.port_id = p.port_id AND inc.class_id IS NOT DISTINCT FROM t.class_id
LEFT JOIN mmf_yield my ON my.port_id = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name, t.class_id NULLS LAST;
