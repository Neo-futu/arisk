-- ============================================================
-- 報表 report_03_mmf / 45_concentration.sql
-- 發行人集中度分析（SFC UT Code §8.2(g) 間接要求）
-- Sheet：日报-sql导入数据，數據從 A148 開始
--
-- 業務含義：
--   SFC 要求投資「高質量」及「分散化」貨幣市場工具，雖未明文規定
--   10% NAV 的單一發行人上限，但業界通行做法及 SFC 審查時的參考標準
--   是單一非政府/公共發行人不超過 10% NAV，政府/公共機構可更高。
--   本 SQL 提供最大單一發行人佔比，供合規監控及 SFC 問詢時備查。
--
-- 欄位說明（6列）：
--   A  port_name              組合名稱
--   B  max_issuer_name        最大單一發行人名稱
--   C  max_issuer_pct         最大單一發行人佔NAV比例（%）
--   D  top5_issuers_pct       前5大發行人合計佔NAV比例（%）
--   E  gov_public_pct         政府/公共機構工具佔NAV比例（%）
--   F  credit_non_gov_pct     信用/非政府工具佔NAV比例（%）
--
-- 資產合並規則：
--   · 債券：按 issuer_name（或 security_name 兜底）彙總
--   · 同業存單：按 issuer_name 彙總
--   · 定期存款：按 bank_name 彙總（以本金計）
--   · 逆回購：按 counterparty_name 彙底（以本金計）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH
eval AS (SELECT '2026-06-25'::DATE AS d),

nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n, eval e
    WHERE n.evaluate_date = e.d AND n.class_id IS NULL
),

-- ── 各持倉按發行人彙總 ───────────────────────────────────
all_holdings AS (
    -- 債券（政府債 + 信用債）
    SELECT b.port_id,
           COALESCE(NULLIF(TRIM(b.issuer_name), ''), b.security_name, '未知') AS issuer,
           CASE WHEN b.asset_subtype = 'BOND_GOVT' THEN 'GOV' ELSE 'CREDIT' END AS issuer_type,
           COALESCE(b.market_value, 0) AS mv
    FROM fsi.balance_bond b, eval e
    WHERE b.evaluate_date = e.d AND b.quantity > 0

    UNION ALL

    -- 同業存單（CD）
    SELECT c.port_id,
           COALESCE(NULLIF(TRIM(c.issuer_name), ''), c.security_name, '未知') AS issuer,
           'CD'                                                                AS issuer_type,
           COALESCE(c.market_value, 0) AS mv
    FROM fsi.balance_cd c, eval e
    WHERE c.evaluate_date = e.d

    UNION ALL

    -- 定期存款（按銀行名稱）
    SELECT d.port_id,
           COALESCE(NULLIF(TRIM(d.bank_name), ''), d.deposit_name, '未知')    AS issuer,
           'DEPOSIT'                                                           AS issuer_type,
           COALESCE(d.principal, 0) AS mv
    FROM fsi.balance_deposit d, eval e
    WHERE d.evaluate_date = e.d

    UNION ALL

    -- 逆回購（按交易對手）
    SELECT r.port_id,
           COALESCE(NULLIF(TRIM(r.counterparty_name), ''), '未知')            AS issuer,
           'REV_REPO'                                                          AS issuer_type,
           COALESCE(r.principal, 0) AS mv
    FROM fsi.balance_repo r, eval e
    WHERE r.evaluate_date = e.d AND r.repo_type = 'REV_REPO'
),

-- ── 按發行人彙總 ──────────────────────────────────────────
by_issuer AS (
    SELECT port_id, issuer, issuer_type,
           SUM(mv) AS total_mv
    FROM all_holdings
    GROUP BY port_id, issuer, issuer_type
),

-- ── 最大單一發行人 ────────────────────────────────────────
max_issuer AS (
    SELECT DISTINCT ON (port_id)
           port_id, issuer AS max_issuer_name, total_mv AS max_mv
    FROM by_issuer
    ORDER BY port_id, total_mv DESC
),

-- ── 前 5 大發行人合計 ─────────────────────────────────────
top5 AS (
    SELECT port_id, SUM(total_mv) AS top5_mv
    FROM (
        SELECT port_id, total_mv,
               ROW_NUMBER() OVER (PARTITION BY port_id ORDER BY total_mv DESC) AS rn
        FROM by_issuer
    ) ranked
    WHERE rn <= 5
    GROUP BY port_id
),

-- ── 政府/公共機構工具合計 ─────────────────────────────────
gov_total AS (
    SELECT port_id, SUM(total_mv) AS gov_mv
    FROM by_issuer
    WHERE issuer_type = 'GOV'
    GROUP BY port_id
),

-- ── 信用/非政府工具合計（含CD、存款、信用債）────────────
credit_total AS (
    SELECT port_id, SUM(total_mv) AS credit_mv
    FROM by_issuer
    WHERE issuer_type IN ('CREDIT', 'CD', 'DEPOSIT')
    GROUP BY port_id
)

SELECT
    p.port_name,
    COALESCE(mi.max_issuer_name, '—')                         AS max_issuer_name,
    ROUND(COALESCE(mi.max_mv, 0) / NULLIF(n.net_asset, 0) * 100, 4)  AS max_issuer_pct,
    ROUND(COALESCE(t5.top5_mv, 0) / NULLIF(n.net_asset, 0) * 100, 4) AS top5_issuers_pct,
    ROUND(COALESCE(gv.gov_mv, 0) / NULLIF(n.net_asset, 0) * 100, 4)  AS gov_public_pct,
    ROUND(COALESCE(cr.credit_mv, 0) / NULLIF(n.net_asset, 0) * 100, 4) AS credit_non_gov_pct
FROM fsi.para_portfolio p
JOIN nav n            ON n.port_id  = p.port_id
LEFT JOIN max_issuer mi ON mi.port_id = p.port_id
LEFT JOIN top5       t5 ON t5.port_id = p.port_id
LEFT JOIN gov_total  gv ON gv.port_id = p.port_id
LEFT JOIN credit_total cr ON cr.port_id = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
