-- ============================================================
-- 報表03 / 16_maturity_buckets.sql
-- 原始：SmartReport/03/16.sql  未来净流入现金流（長期）
-- Sheet：日报-sql导入数据，標籤16.sql@K94，表頭K95，數據K96
--
-- 欄位說明（對照模版表頭 K95-R95）：
--   未来流入现金流            = port_name
--   T+14流入金额（亿元）      = t14
--   T+30流入金额（亿元）      = t30
--   T日至本月末流入金额（亿元）= month_end
--   T日至下月末流入金额（亿元）= next_month_end
--   T日至第3月月末流入金额    = m3_end（首月+2個月末）
--   T日至本季末流入金额       = quarter_end
--   T日至本年末流入金额       = year_end
--
-- 與 12.sql（T+1~T+5）的差異：
--   · 無上限截止（所有到期日均計入）
--   · 不含正回購（16.sql 只計逆回購融出，無還款流出）
--   · 時間節點為日曆日/月末/季末，不是交易日
--
-- 所有列均為累計（MaturityDate <= 各節點）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH all_assets AS (
    -- 債券（市值）
    SELECT b.port_id, b.maturity_date, COALESCE(b.market_value, 0) AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.maturity_date >= '2026-06-25'::DATE

    UNION ALL

    -- 存款證（市值）
    SELECT c.port_id, c.maturity_date, COALESCE(c.market_value, 0)
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND c.evaluate_date = '2026-06-25'::DATE
      AND c.maturity_date >= '2026-06-25'::DATE

    UNION ALL

    -- 存款（本金）
    SELECT d.port_id, d.maturity_date, COALESCE(d.principal, 0)
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND d.evaluate_date = '2026-06-25'::DATE
      AND d.maturity_date >= '2026-06-25'::DATE

    UNION ALL

    -- 逆回購融出（到期收回，正值；注：16.sql 不含正回購負值）
    SELECT r.port_id,
           COALESCE(r.actual_maturity_date, r.maturity_date),
           COALESCE(r.principal, 0)
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p ON p.port_id = r.port_id
    WHERE p.is_mmf = TRUE AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) >= '2026-06-25'::DATE
),

-- 關鍵日期計算（對應源 SQL 的 DateAdd/EndDayOfMonth/EndDayOfQuarter）
dates AS (
    SELECT
        '2026-06-25'::DATE + 14                                                           AS d14,
        '2026-06-25'::DATE + 30                                                           AS d30,
        -- 本月末
        DATE_TRUNC('month','2026-06-25'::DATE) + INTERVAL '1 month' - INTERVAL '1 day'   AS month_end,
        -- 下月末（首月+1個月的月末）
        DATE_TRUNC('month','2026-06-25'::DATE) + INTERVAL '2 month' - INTERVAL '1 day'   AS next_month_end,
        -- 第3月末（首月+3個月的月末，對應源 Dateadd(Month,4,FirstDayOfMonth)-1）
        DATE_TRUNC('month','2026-06-25'::DATE) + INTERVAL '4 month' - INTERVAL '1 day'   AS m3_end,
        -- 季末
        DATE_TRUNC('quarter','2026-06-25'::DATE) + INTERVAL '3 month' - INTERVAL '1 day' AS quarter_end,
        -- 年末
        DATE_TRUNC('year','2026-06-25'::DATE) + INTERVAL '1 year' - INTERVAL '1 day'     AS year_end
)

SELECT
    p.port_name,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.d14)           / 100000000, 4) AS t14_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.d30)           / 100000000, 4) AS t30_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.month_end)     / 100000000, 4) AS month_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.next_month_end)/ 100000000, 4) AS next_month_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.m3_end)        / 100000000, 4) AS m3_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.quarter_end)   / 100000000, 4) AS quarter_end_100m,
    ROUND(SUM(a.mv) FILTER (WHERE a.maturity_date <= d.year_end)      / 100000000, 4) AS year_end_100m
FROM all_assets a
CROSS JOIN dates d
JOIN fsi.para_portfolio p ON p.port_id = a.port_id
WHERE p.is_active = TRUE
GROUP BY p.port_name
ORDER BY p.port_name;
