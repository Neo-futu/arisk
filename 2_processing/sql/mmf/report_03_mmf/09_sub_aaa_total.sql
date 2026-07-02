-- ============================================================
-- 報表03 / 09_sub_aaa_total.sql
-- AAA以下機構發行的存款、存單、債券合計（HK MMF 信用質量監控）
-- Sheet：日报-sql导入数据，標籤09.sql@A60，表頭A61，數據A62
--
-- 業務含義（SFC UT Code §8.2(a) 信用質量要求）：
--   SFC 要求貨幣基金投資「高質量貨幣市場工具」，原則上不投資低評級工具。
--   本 SQL 統計非頂級評級（AAA）機構的持倉市值及佔 NAV 比例，
--   作為信用質量日常監控的補充指標。
--
-- 評級過濾邏輯（HK 主要評級機構）：
--   AAA 等同級別（排除在外，不計入 "AAA以下"）：
--     標準普爾 S&P：AAA
--     穆迪 Moody's：Aaa（本系統存儲為'AAA'或'Aaa'）
--     惠譽 Fitch ：AAA
--   "AAA以下" = 所有非 AAA 評級（含 AA、A、BBB、未評級 NR）
--   注：政府/公共債券（BOND_GOVT）通常視為高質量，本 SQL 亦包含其非 AAA 評級。
--
-- 欄位說明（3列）：
--   port_name  組合名稱
--   mv_100m    AAA以下機構持倉市值合計（億元）
--   ratio_nav  持倉市值佔NAV比例（%）
--
-- 修正說明（vs 原版）：
--   [原] NOT IN ('AAA','AAA+')：'AAA+'不是標準評級代碼，改為更全面的清單
--   [新] 明確包含 Moody's 'Aaa' 等同 AAA，避免遺漏
--   [新] 用 market_value 計算比率（與其他表格口徑統一）
--   [新] 保留 cost/principal 作為輔助計算（存款無市值）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

-- AAA 等同評級清單（S&P / Moody's / Fitch 三家主要機構）
-- 若系統評級存儲格式不一，可在此擴充
WITH aaa_ratings AS (
    SELECT unnest(ARRAY[
        'AAA', 'Aaa',       -- S&P / Moody's
        'AAA+', 'AAA-sf'    -- 結構化金融等特殊標記（保留兼容）
    ]) AS rating
),

nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date = '2026-06-25'::DATE AND n.class_id IS NULL
),

sub_aaa AS (
    -- 債券（發行人評級 ≠ AAA，含未評級 NR）
    SELECT b.port_id,
           b.security_code,
           b.security_name,
           b.asset_subtype,
           COALESCE(b.issuer_rating, b.debt_rating, 'NR') AS rating_used,
           COALESCE(b.market_value, 0)                     AS mv,
           COALESCE(b.cost, 0)                             AS cost_val
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.quantity > 0
      AND COALESCE(b.issuer_rating, b.debt_rating, 'NR')
          NOT IN (SELECT rating FROM aaa_ratings)

    UNION ALL

    -- 同業存單（發行人評級 ≠ AAA）
    SELECT c.port_id,
           c.security_code,
           c.security_name,
           'CD'                                                AS asset_subtype,
           COALESCE(c.issuer_rating, 'NR')                    AS rating_used,
           COALESCE(c.market_value, 0)                        AS mv,
           COALESCE(c.cost, 0)                                AS cost_val
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(c.issuer_rating, 'NR')
          NOT IN (SELECT rating FROM aaa_ratings)

    UNION ALL

    -- 存款（銀行評級 ≠ AAA；用本金代替市值，存款無公允價值）
    SELECT d.port_id,
           d.deposit_id,
           d.deposit_name,
           'DEPOSIT'                                           AS asset_subtype,
           COALESCE(d.bank_rating, 'NR')                      AS rating_used,
           COALESCE(d.principal, 0)                           AS mv,     -- 存款無市值，用本金
           COALESCE(d.principal, 0)                           AS cost_val
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(d.bank_rating, 'NR')
          NOT IN (SELECT rating FROM aaa_ratings)
)

SELECT
    p.port_name,
    ROUND(SUM(s.mv) / 100000000.0, 4)                        AS mv_100m,
    ROUND(SUM(s.mv) / NULLIF(n.net_asset, 0) * 100, 4)       AS ratio_nav
FROM sub_aaa s
JOIN fsi.para_portfolio p ON p.port_id = s.port_id
JOIN nav n ON n.port_id = s.port_id
GROUP BY p.port_name, n.net_asset
ORDER BY p.port_name;
