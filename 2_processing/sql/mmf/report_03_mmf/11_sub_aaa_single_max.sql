-- ============================================================
-- 報表03 / 11_sub_aaa_single_max.sql
-- 單一AAA以下機構發行的金融工具最大佔NAV比率（信用集中度指標）
-- Sheet：日报-sql导入数据，標籤11.sql@D60，表頭D61，數據D62
--
-- 業務含義（SFC §8.2(a) 信用質量 + §8.2(g) 集中度間接要求）：
--   在所有「非頂級評級」機構的持倉中，找出佔 NAV 比例最高的單一發行人。
--   用於識別信用集中度風險：若單一非 AAA 發行人佔比過高，需向投資委員會說明。
--
-- 評級過濾（與 09_sub_aaa_total.sql 保持一致）：
--   排除：AAA（S&P）、Aaa（Moody's）
--   包含：AA及以下所有評級、未評級(NR)
--
-- 發行人識別規則（HK 數據庫）：
--   債券：優先用 issuer_id；無則回退到 COALESCE(issuer_name, security_code)
--   存單：優先用 issuer_id；無則回退到 issuer_name
--   存款：優先用 bank_id；無則回退到 bank_name
--   注意：同一發行人可能有多個 security_code，issuer_id 是最可靠的彙總鍵
--
-- 欄位說明（2列）：
--   port_name   組合名稱
--   max_ratio   單一非AAA發行人最大佔NAV比（%）
--
-- 修正說明（vs 原版）：
--   [原] NOT IN ('AAA','AAA+')：'AAA+'非標準；改用標準清單
--   [原] 用 cost/NAV；改為 market_value/NAV（存款仍用 principal）
--   [原] 優先用 issuer_id，無則用 security_code
--   [新] 優先用 issuer_id，無則改用 issuer_name（更準確）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH aaa_ratings AS (
    SELECT unnest(ARRAY['AAA', 'Aaa', 'AAA+', 'AAA-sf']) AS rating
),

nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n
    WHERE n.evaluate_date = '2026-06-25'::DATE AND n.class_id IS NULL
),

-- 各持倉按發行人 + 評級篩選彙總
issuer_detail AS (
    -- 債券
    SELECT b.port_id,
           -- 發行人識別優先級：issuer_id > issuer_name > security_code
           COALESCE(
               NULLIF(TRIM(b.issuer_id::TEXT), ''),
               NULLIF(TRIM(b.issuer_name), ''),
               b.security_code
           ) AS issuer_key,
           COALESCE(b.market_value, 0) AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.quantity > 0
      AND COALESCE(b.issuer_rating, b.debt_rating, 'NR')
          NOT IN (SELECT rating FROM aaa_ratings)

    UNION ALL

    -- 同業存單
    SELECT c.port_id,
           COALESCE(
               NULLIF(TRIM(c.issuer_id::TEXT), ''),
               NULLIF(TRIM(c.issuer_name), ''),
               c.security_code
           ) AS issuer_key,
           COALESCE(c.market_value, 0) AS mv
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(c.issuer_rating, 'NR')
          NOT IN (SELECT rating FROM aaa_ratings)

    UNION ALL

    -- 存款（用本金，存款無市值）
    SELECT d.port_id,
           COALESCE(
               NULLIF(TRIM(d.bank_id::TEXT), ''),
               NULLIF(TRIM(d.bank_name), ''),
               d.deposit_id
           ) AS issuer_key,
           COALESCE(d.principal, 0) AS mv
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND COALESCE(d.bank_rating, 'NR')
          NOT IN (SELECT rating FROM aaa_ratings)
),

-- 按發行人彙總佔NAV比
issuer_sum AS (
    SELECT id.port_id, id.issuer_key,
           SUM(id.mv) / NULLIF(n.net_asset, 0) * 100 AS issuer_ratio_nav
    FROM issuer_detail id
    JOIN nav n ON n.port_id = id.port_id
    GROUP BY id.port_id, id.issuer_key, n.net_asset
)

SELECT
    p.port_name,
    ROUND(MAX(s.issuer_ratio_nav), 4) AS max_ratio
FROM issuer_sum s
JOIN fsi.para_portfolio p ON p.port_id = s.port_id
GROUP BY p.port_name
ORDER BY p.port_name;
