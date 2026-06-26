WITH -- ============================================================
-- 報表03 / 04_top_holders.sql
-- 原始：SmartReport/03/04.sql  前十大持有人（機構/散戶/前1/前10）
-- 參數：params.evaluate_date DATE
-- ============================================================

top1 AS (
    SELECT
        r.port_id,
        ROUND(r.amount / n.net_asset * 100, 4) AS top1_pct,
        r.holder_name                           AS top1_name
    FROM fsi.balance_holder_rank r
    JOIN fsi.balance_portfolio_nav n ON n.port_id = r.port_id
       AND n.evaluate_date = r.confirm_date AND n.class_id IS NULL
    WHERE r.confirm_date = params.evaluate_date
      AND r.rank_no = 1
),

top10 AS (
    -- 前10大（含關聯方）
    SELECT
        r.port_id,
        SUM(r.pct_of_total) AS top10_pct_gross
    FROM fsi.balance_holder_rank r, params
    WHERE r.confirm_date = params.evaluate_date
      AND r.rank_no <= 10
    GROUP BY r.port_id
),

summary AS (
    SELECT
        hs.port_id,
        hs.total_holders,
        hs.retail_holders,
        ROUND(hs.top10_pct, 4)       AS top10_pct_official,  -- 官方公布前十大佔比
        ROUND(hs.top10_amount, 2)    AS top10_amount
    FROM fsi.balance_holder_summary hs, params
    WHERE hs.confirm_date = params.evaluate_date
      AND hs.class_id IS NULL
)

SELECT
    p.port_name,
    ROUND((s.total_holders - COALESCE(s.retail_holders, 0))::NUMERIC /
          NULLIF(s.total_holders, 0) * 100, 2)           AS institutional_pct,  -- 機構比例%
    t1.top1_pct                                           AS top1_holder_pct,
    COALESCE(t10.top10_pct_gross, s.top10_pct_official)  AS top10_pct,          -- 前十大合計%
    s.top10_pct_official                                  AS top10_pct_reported,
    s.total_holders,
    s.retail_holders,
    t1.top1_name
FROM summary s
JOIN fsi.para_portfolio p ON p.port_id = s.port_id
LEFT JOIN top1  t1  ON t1.port_id  = s.port_id
LEFT JOIN top10 t10 ON t10.port_id = s.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
