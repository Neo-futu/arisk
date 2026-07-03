-- ============================================================
-- 報表 report_04_mmf_monthly / 07_maturity_dist.sql
-- 到期日分佈（佔 NAV 百分比），仿 Factsheet 到期日分佈圖
--
-- 到期區間：
--   1天以內（隔夜）   remaining_days = 0~1
--   2至7天            remaining_days = 2~7
--   8至30天           remaining_days = 8~30
--   31至60天          remaining_days = 31~60
--   61至90天          remaining_days = 61~90
--   91至180天         remaining_days = 91~180
--   181至365天        remaining_days = 181~365
--   超過365天         remaining_days > 365
--
-- 欄位（5列）：
--   A  port_name     組合名稱
--   B  bucket_order  排序序號
--   C  bucket_label  到期區間標籤（繁體）
--   D  mv_100m       市值（億元，存款用本金）
--   E  pct_nav       佔 NAV 比例（%）
-- ============================================================

WITH
eval AS (SELECT '2026-06-25'::DATE AS d),

nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n, eval e
    WHERE n.evaluate_date = e.d AND n.class_id IS NULL
),

holdings AS (
    -- 債券
    SELECT b.port_id,
           COALESCE(b.remaining_days,
                    (b.maturity_date - '2026-06-25'::DATE)) AS rem_days,
           COALESCE(b.market_value, 0)                       AS mv
    FROM fsi.balance_bond b, eval e
    WHERE b.evaluate_date = e.d AND b.quantity > 0

    UNION ALL
    -- 同業存單
    SELECT c.port_id,
           COALESCE(c.remaining_days,
                    (c.maturity_date - '2026-06-25'::DATE)) AS rem_days,
           COALESCE(c.market_value, 0)
    FROM fsi.balance_cd c, eval e
    WHERE c.evaluate_date = e.d

    UNION ALL
    -- 定期存款（本金）
    SELECT d.port_id,
           GREATEST((d.maturity_date - '2026-06-25'::DATE), 0) AS rem_days,
           COALESCE(d.principal, 0)
    FROM fsi.balance_deposit d, eval e
    WHERE d.evaluate_date = e.d

    UNION ALL
    -- 逆回購
    SELECT r.port_id,
           GREATEST((COALESCE(r.actual_maturity_date, r.maturity_date)
                     - '2026-06-25'::DATE), 0)               AS rem_days,
           COALESCE(r.principal, 0)
    FROM fsi.balance_repo r, eval e
    WHERE r.evaluate_date = e.d AND r.repo_type = 'REV_REPO'
),

bucketed AS (
    SELECT port_id, mv,
           CASE
               WHEN rem_days <= 1   THEN 1
               WHEN rem_days <= 7   THEN 2
               WHEN rem_days <= 30  THEN 3
               WHEN rem_days <= 60  THEN 4
               WHEN rem_days <= 90  THEN 5
               WHEN rem_days <= 180 THEN 6
               WHEN rem_days <= 365 THEN 7
               ELSE                      8
           END AS bucket_order,
           CASE
               WHEN rem_days <= 1   THEN '1天以內'
               WHEN rem_days <= 7   THEN '2至7天'
               WHEN rem_days <= 30  THEN '8至30天'
               WHEN rem_days <= 60  THEN '31至60天'
               WHEN rem_days <= 90  THEN '61至90天'
               WHEN rem_days <= 180 THEN '91至180天'
               WHEN rem_days <= 365 THEN '181至365天'
               ELSE                      '超過365天'
           END AS bucket_label
    FROM holdings
),

agg AS (
    SELECT port_id, bucket_order, bucket_label,
           SUM(mv) AS mv_sum
    FROM bucketed
    GROUP BY port_id, bucket_order, bucket_label
)

SELECT
    p.port_name,
    a.bucket_order,
    a.bucket_label,
    ROUND(a.mv_sum / 1e8, 6)                                   AS mv_100m,
    ROUND(a.mv_sum / NULLIF(n.net_asset, 0) * 100, 4)         AS pct_nav
FROM agg a
JOIN fsi.para_portfolio p ON p.port_id = a.port_id
JOIN nav n ON n.port_id = a.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name, a.bucket_order;
