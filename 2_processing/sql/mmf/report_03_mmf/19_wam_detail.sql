-- ============================================================
-- 報表03 / 19_wam_detail.sql
-- 原始：SmartReport/03/19.sql  債券及存單加權平均到期期限
-- Sheet：其他监控-sql导入数据，標籤19.sql@D2，表頭D3，數據D4
--
-- 欄位說明（對照模版表頭 D3-E3）：
--   组合名称                    = port_name
--   加权平均剩余期限(天)         = wam_all_days
--
-- 計算方法（市值加權，SFC 監管口徑）：
--   wam_all_days = SUM(持倉市值_i × 剩餘天數_i) / 基金總NAV
--
--   分母用基金總NAV（含現金，現金貢獻 0 天）→ 反映全組合視角
--   浮息債使用下次付息重設日（而非到期日），符合 SFC UT Code §8.2(f) WAM 定義
--   存款、逆回購使用實際到期日
--
-- 與 01_nav_deviation.sql 的 wam_days 對比：
--   · 01 sql: wam_days 来自 balance_portfolio_mmf（系統計算，監管口徑，精確）
--   · 19 sql: 本 SQL 按持倉明細重算，可作交叉驗證
--
-- 注意：結果若接近 SFC 上限（60天）但未超越，屬正常；
--       若超過 60 天，需結合 01 sql 的系統口徑值確認。
--       單一工具剩餘期限上限：SFC UT Code §8.2(f) ≤397天（政府/公共證券≤730天）。
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date = '2026-06-25'::DATE
      AND n.class_id IS NULL
),

holdings AS (
    -- 債券：固息債用到期日；浮息債用下次付息重設日（SFC WAM 定義）
    SELECT b.port_id,
           CASE
               WHEN COALESCE(b.coupon_type, 'FIXED') = 'FLOAT'
               THEN GREATEST(
                       COALESCE(b.next_coupon_date, b.maturity_date)
                       - '2026-06-25'::DATE, 0)
               ELSE GREATEST(
                       COALESCE(b.remaining_days,
                                (b.maturity_date - '2026-06-25'::DATE)::INT),
                       0)
           END                                                   AS days,
           COALESCE(b.market_value, 0)                          AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.quantity > 0

    UNION ALL

    -- 同業存單：用到期日
    SELECT c.port_id,
           GREATEST(
               COALESCE(c.remaining_days,
                        (c.maturity_date - '2026-06-25'::DATE)::INT),
               0)                                               AS days,
           COALESCE(c.market_value, 0)                         AS mv
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE

    UNION ALL

    -- 定期存款：用到期日（隔夜存款貢獻1天）
    SELECT d.port_id,
           GREATEST((d.maturity_date - '2026-06-25'::DATE)::INT, 0) AS days,
           COALESCE(d.principal, 0)                            AS mv
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE

    UNION ALL

    -- 逆回購：用實際到期日（通常隔夜，貢獻1天）
    SELECT r.port_id,
           GREATEST(
               (COALESCE(r.actual_maturity_date, r.maturity_date)
                - '2026-06-25'::DATE)::INT,
               0)                                               AS days,
           COALESCE(r.principal, 0)                            AS mv
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p ON p.port_id = r.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REV_REPO'
),

agg AS (
    SELECT port_id,
           SUM(mv * days)  AS wtd_sum
    FROM holdings
    GROUP BY port_id
)

SELECT
    p.port_name,
    -- WAM = SUM(市值_i × 天數_i) / 基金總NAV（現金貢獻0天）
    ROUND(a.wtd_sum / NULLIF(n.net_asset, 0), 4)   AS wam_all_days
FROM agg a
JOIN fsi.para_portfolio p ON p.port_id = a.port_id
JOIN nav n ON n.port_id = a.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
