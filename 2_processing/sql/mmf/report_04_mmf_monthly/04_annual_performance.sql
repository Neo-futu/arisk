-- report_04_mmf_monthly / 04_annual_performance.sql
-- 年度業績：生成年度回報和本年累計 (YTD) 的數據，用於 Factsheet 的年度表現區。
-- 業務意義：
--   1) 以年末 NAV 計算每年的年度回報
--   2) 使用最近一個可用年末數據，並與前一年年末比較
--   3) YTD 使用本年度首個可用 NAV 與當前評估日 NAV 計算
--   4) 只展示 2021 年以後的年度回報，保持報表簡潔
WITH
year_end_nav AS (
    SELECT DISTINCT ON (n.port_id, n.class_id, EXTRACT(YEAR FROM n.evaluate_date))
           n.port_id, n.class_id,
           EXTRACT(YEAR FROM n.evaluate_date)::INT AS yr,
           n.unit_nav, n.evaluate_date
    FROM fsi.balance_portfolio_nav n
    JOIN fsi.para_portfolio p ON p.port_id = n.port_id
    WHERE p.is_mmf = TRUE
      AND EXTRACT(YEAR FROM n.evaluate_date) >= 2020
    ORDER BY n.port_id, n.class_id,
             EXTRACT(YEAR FROM n.evaluate_date), n.evaluate_date DESC
),
ytd_nav AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav AS nav_ytd
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date = '2026-06-25'::DATE
    ORDER BY n.port_id, n.class_id
),
ytd_start AS (
    SELECT DISTINCT ON (n.port_id, n.class_id)
           n.port_id, n.class_id, n.unit_nav AS nav_start
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date >= DATE_TRUNC('year', '2026-06-25'::DATE)::DATE
      AND n.evaluate_date <= DATE_TRUNC('year', '2026-06-25'::DATE)::DATE + 5
    ORDER BY n.port_id, n.class_id, n.evaluate_date ASC
),
annual AS (
    SELECT curr.port_id, curr.class_id,
           curr.yr::TEXT AS year_label,
           ROUND((curr.unit_nav / NULLIF(prev.unit_nav, 0) - 1) * 100, 2) AS perf_pct,
           prev.unit_nav AS nav_start, curr.unit_nav AS nav_end
    FROM year_end_nav curr
    LEFT JOIN year_end_nav prev
        ON prev.port_id = curr.port_id
        AND prev.class_id IS NOT DISTINCT FROM curr.class_id
        AND prev.yr = curr.yr - 1
    WHERE curr.yr BETWEEN 2021 AND 2025
    UNION ALL
    SELECT ytd.port_id, ytd.class_id,
           'YTD' AS year_label,
           ROUND((ytd.nav_ytd / NULLIF(ys.nav_start, 0) - 1) * 100, 2) AS perf_pct,
           ys.nav_start, ytd.nav_ytd
    FROM ytd_nav ytd
    LEFT JOIN ytd_start ys ON ys.port_id = ytd.port_id
        AND ys.class_id IS NOT DISTINCT FROM ytd.class_id
)
SELECT p.port_name,
       COALESCE(a.class_id::TEXT, 'Base') AS class_id,
       a.year_label, a.perf_pct, a.nav_start, a.nav_end
FROM annual a
JOIN fsi.para_portfolio p ON p.port_id = a.port_id
WHERE p.is_active = TRUE
ORDER BY p.port_name, a.class_id NULLS LAST,
         CASE a.year_label WHEN 'YTD' THEN 9999 ELSE a.year_label::INT END;
