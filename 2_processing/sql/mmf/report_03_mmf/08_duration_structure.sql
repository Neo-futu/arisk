-- ============================================================
-- 報表03 / 08_duration_structure.sql
-- 原始：SmartReport/03/08.sql  偏離資產組合期限結構（加權平均久期）
-- Sheet：日报-sql导入数据，標籤08.sql@A23，表頭A24，數據A26
--
-- 欄位說明（對照模版表頭 A24-C24）：
--   组合         = port_name（每個組合一行）
--   偏离度资产   = mv（債券+存單市值合計，元）
--   久期         = duration（市值加權平均久期，年）
--
-- 久期計算規則（對應源 SQL）：
--   固息債（coupon_type='FIXED'）：直接用 duration 欄位
--   浮息債（coupon_type='FLOAT'）：用距下次重定價日天數/365（重定價剩餘期限）
--   存款證（CD）：直接用 duration 欄位
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH detail AS (
    -- 債券
    SELECT
        b.port_id,
        b.market_value,
        CASE
            WHEN b.coupon_type = 'FLOAT' AND b.next_coupon_date IS NOT NULL
                THEN (b.next_coupon_date - '2026-06-25'::DATE) / 365.0
            ELSE COALESCE(b.duration, b.remaining_days / 365.0)
        END AS effective_duration
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE
      AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.market_value > 0

    UNION ALL

    -- 存款證（CD）
    SELECT
        c.port_id,
        c.market_value,
        COALESCE(c.duration, c.remaining_days / 365.0) AS effective_duration
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE
      AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND c.market_value > 0
)

SELECT
    p.port_name,
    ROUND(SUM(d.market_value), 2)                              AS mv,       -- 偏离度资产（元）
    ROUND(SUM(d.market_value * d.effective_duration) /
          NULLIF(SUM(d.market_value), 0), 4)                   AS duration  -- 久期（年）
FROM detail d
JOIN fsi.para_portfolio p ON p.port_id = d.port_id
GROUP BY p.port_name
ORDER BY p.port_name;
