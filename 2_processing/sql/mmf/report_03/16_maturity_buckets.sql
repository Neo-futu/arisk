WITH -- ============================================================
-- 報表03 / 16_maturity_buckets.sql
-- 原始：SmartReport/03/16.sql  T+14/T+30/月末/下月末/3月末/季末/年末到期
-- 功能：中長期流動性分佈（含月末/季末/年末關鍵時間節點）
-- 參數：params.evaluate_date DATE
-- ============================================================

all_assets AS (
    SELECT b.port_id, b.maturity_date, COALESCE(b.market_value, 0) AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id, params
    WHERE p.is_mmf = TRUE AND b.evaluate_date = params.evaluate_date
      AND b.maturity_date >= params.evaluate_date

    UNION ALL
    SELECT c.port_id, c.maturity_date, COALESCE(c.market_value, 0)
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id, params
    WHERE p.is_mmf = TRUE AND c.evaluate_date = params.evaluate_date
      AND c.maturity_date >= params.evaluate_date

    UNION ALL
    SELECT d.port_id, d.maturity_date, COALESCE(d.principal, 0)
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id, params
    WHERE p.is_mmf = TRUE AND d.evaluate_date = params.evaluate_date
      AND d.maturity_date >= params.evaluate_date

    UNION ALL
    SELECT r.port_id,
           COALESCE(r.actual_maturity_date, r.maturity_date),
           COALESCE(r.principal, 0)
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p ON p.port_id = r.port_id, params
    WHERE p.is_mmf = TRUE AND r.evaluate_date = params.evaluate_date
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) >= params.evaluate_date
),

-- 關鍵日期計算
dates AS (
    SELECT
        params.evaluate_date::DATE                                                        AS eval_date,
        params.evaluate_date::DATE + 14                                                   AS d14,
        params.evaluate_date::DATE + 30                                                   AS d30,
        -- 月末
        DATE_TRUNC('month', params.evaluate_date::DATE) + INTERVAL '1 month' - INTERVAL '1 day' AS month_end,
        -- 下月末
        DATE_TRUNC('month', params.evaluate_date::DATE) + INTERVAL '2 month' - INTERVAL '1 day' AS next_month_end,
        -- 3個月末
        DATE_TRUNC('month', params.evaluate_date::DATE) + INTERVAL '4 month' - INTERVAL '1 day' AS m3_end,
        -- 季末
        DATE_TRUNC('quarter', params.evaluate_date::DATE) + INTERVAL '3 month' - INTERVAL '1 day' AS quarter_end,
        -- 年末
        DATE_TRUNC('year', params.evaluate_date::DATE) + INTERVAL '1 year' - INTERVAL '1 day'    AS year_end
)

SELECT
    p.port_name,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.d14)          / 100000000, 4) AS t14_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.d30)          / 100000000, 4) AS t30_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.month_end)    / 100000000, 4) AS month_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.next_month_end)/ 100000000, 4) AS next_month_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.m3_end)       / 100000000, 4) AS m3_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.quarter_end)  / 100000000, 4) AS quarter_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.year_end)     / 100000000, 4) AS year_end_100m
FROM all_assets a
CROSS JOIN dates d
JOIN fsi.para_portfolio p ON p.port_id = a.port_id
WHERE p.is_active = TRUE
GROUP BY p.port_name
ORDER BY p.port_name;
