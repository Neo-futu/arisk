-- ============================================================
-- 報表03 / 19_wam_detail.sql
-- 原始：SmartReport/03/19.sql  利率債/信用債/存單加權平均剩餘期限
-- Sheet：其他监控-sql导入数据，標籤19.sql@D2，表頭D3，數據D4
--
-- 欄位說明（對照模版表頭 D3-E3）：
--   组合名称                          = port_name
--   利率债、信用债、同存加权平均剩余期限(天) = syday
--
-- 計算公式（完全對齊源 SQL）：
--   ROUND( SUM(RatioToNAV% × 剩餘天數) / 100, 4 )
--
--   除以100的含義：RatioToNAV是百分比（如5.2），除以100後得到加權平均天數。
--   效果：非債券資產（現金/存款）隱性貢獻0天，結果反映整體組合視角的期限。
--
--   對比 WAM 計算（svc_risk_snapshot.wam_days）：
--   · WAM：按貨基守則，浮息債用下次重定價日，固息債用到期日
--   · 19.sql：所有債券+存單統一用到期日，純"剩餘天數"概念
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH bond_cd AS (
    -- 債券
    SELECT b.port_id,
           b.security_code,
           b.remaining_days                   AS syday,     -- 到期剩餘天數
           COALESCE(b.weight_pct, 0)          AS ratio_to_nav  -- %，如5.2表示5.2%NAV
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.remaining_days > 0

    UNION ALL

    -- 存款證（同業存單）
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
           SUM(ratio_to_nav * syday) AS ratio_sy   -- ∑(佔比% × 剩餘天數)
    FROM bond_cd
    GROUP BY port_id
)

SELECT
    p.port_name,
    ROUND(s.ratio_sy / 100.0, 4) AS syday   -- 除以100：% → 小數，得加權平均天數
FROM summary s
JOIN fsi.para_portfolio p ON p.port_id = s.port_id
ORDER BY p.port_name;
