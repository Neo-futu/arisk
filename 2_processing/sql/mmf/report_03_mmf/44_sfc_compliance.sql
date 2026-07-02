-- ============================================================
-- 報表 report_03_mmf / 44_sfc_compliance.sql
-- SFC UT Code §8.2 合規流動性指標
-- Sheet：日报-sql导入数据，A129=表頭，數據從 A130 開始
--
-- SFC 量化要求（高置信度確認，來源：UT Code §8.2(f)/(n)）：
--   WAM ≤ 60 天                       (§8.2(f))
--   WAL ≤ 120 天                      (§8.2(f))
--   DLA（日流動資產） ≥ 7.5% NAV     (§8.2(n))
--   WLA（週流動資產） ≥ 15%  NAV     (§8.2(n))
--   單一工具最大剩餘期限 ≤ 397 天     (§8.2(f))
--   政府/公共證券例外上限 ≤ 730 天
--
-- DLA 定義（UT Code §8.2(f)(i) + IOSCO FR07/12 建議 §7）：
--   現金
--   + 1 個交易日內到期的政府/公共證券
--   + 1 個交易日內到期的存款（隔夜存款）
--   + 1 個交易日內到期的同業存單（CD）
--   + 所有逆回購（REV_REPO，通常為隔夜，保守計入 DLA）
--
-- WLA 定義（UT Code §8.2(f)(ii)）：
--   現金
--   + 5 個交易日內到期的政府/公共證券
--   + 5 個交易日內到期的其他貨幣市場工具（CD、信用債）
--   + 5 個交易日內到期的存款（含隔夜）
--   + 5 個交易日內到期的逆回購
--
-- 欄位說明（7列）：
--   A  port_name            組合名稱
--   B  dla_pct              DLA 佔 NAV 比例（%）
--   C  wla_pct              WLA 佔 NAV 比例（%）
--   D  max_instrument_days  最大單一工具剩餘期限（天）
--   E  dla_status           DLA 合規狀態（合規 / 未達標≥7.5%）
--   F  wla_status           WLA 合規狀態（合規 / 未達標≥15%）
--   G  mat_status           最大工具期限合規狀態（合規 / 超限≤397天）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH eval AS (
    SELECT '2026-06-25'::DATE AS d
),

nav AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n, eval e
    WHERE n.evaluate_date = e.d AND n.class_id IS NULL
),

-- ── 現金（CASH 資產類別，最高流動性）──────────────────────
cash_amt AS (
    SELECT a.port_id,
           COALESCE(SUM(a.market_value), 0) AS cash
    FROM fsi.balance_portfolio_asset a, eval e
    WHERE a.evaluate_date = e.d
      AND a.asset_class = 'CASH'
    GROUP BY a.port_id
),

-- ── DLA：1 交易日內到期資產 ──────────────────────────────
-- 政府/公共證券 T+1 到期（BOND_GOVT）
dla_govbond AS (
    SELECT b.port_id,
           COALESCE(SUM(b.market_value), 0) AS amt
    FROM fsi.balance_bond b, eval e
    WHERE b.evaluate_date = e.d
      AND b.quantity > 0
      AND b.asset_subtype = 'BOND_GOVT'
      AND b.maturity_date <= e.d + 1
    GROUP BY b.port_id
),
-- CD T+1 到期
dla_cd AS (
    SELECT c.port_id,
           COALESCE(SUM(c.market_value), 0) AS amt
    FROM fsi.balance_cd c, eval e
    WHERE c.evaluate_date = e.d
      AND c.maturity_date <= e.d + 1
    GROUP BY c.port_id
),
-- 隔夜存款（is_overnight=TRUE 或到期日=T+1）
dla_deposit AS (
    SELECT d.port_id,
           COALESCE(SUM(d.principal), 0) AS amt
    FROM fsi.balance_deposit d, eval e
    WHERE d.evaluate_date = e.d
      AND (d.is_overnight = TRUE OR d.maturity_date <= e.d + 1)
    GROUP BY d.port_id
),
-- 逆回購（REV_REPO，保守全部計入 DLA，通常為隔夜）
dla_revrepo AS (
    SELECT r.port_id,
           COALESCE(SUM(r.principal), 0) AS amt
    FROM fsi.balance_repo r, eval e
    WHERE r.evaluate_date = e.d
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= e.d + 1
    GROUP BY r.port_id
),

-- ── WLA：5 交易日內到期資產 ──────────────────────────────
-- 政府/公共證券 T+1~T+5 到期
wla_govbond AS (
    SELECT b.port_id,
           COALESCE(SUM(b.market_value), 0) AS amt
    FROM fsi.balance_bond b, eval e
    WHERE b.evaluate_date = e.d
      AND b.quantity > 0
      AND b.asset_subtype = 'BOND_GOVT'
      AND b.maturity_date <= e.d + 5
    GROUP BY b.port_id
),
-- CD T+1~T+5 到期
wla_cd AS (
    SELECT c.port_id,
           COALESCE(SUM(c.market_value), 0) AS amt
    FROM fsi.balance_cd c, eval e
    WHERE c.evaluate_date = e.d
      AND c.maturity_date <= e.d + 5
    GROUP BY c.port_id
),
-- 存款 T+1~T+5 到期（含隔夜）
wla_deposit AS (
    SELECT d.port_id,
           COALESCE(SUM(d.principal), 0) AS amt
    FROM fsi.balance_deposit d, eval e
    WHERE d.evaluate_date = e.d
      AND (d.maturity_date <= e.d + 5 OR d.is_overnight = TRUE)
    GROUP BY d.port_id
),
-- 逆回購 T+1~T+5 到期
wla_revrepo AS (
    SELECT r.port_id,
           COALESCE(SUM(r.principal), 0) AS amt
    FROM fsi.balance_repo r, eval e
    WHERE r.evaluate_date = e.d
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= e.d + 5
    GROUP BY r.port_id
),
-- 信用債（非政府債）T+1~T+5 到期（SFC WLA 含部分信用評級較高工具）
wla_corpbond AS (
    SELECT b.port_id,
           COALESCE(SUM(b.market_value), 0) AS amt
    FROM fsi.balance_bond b, eval e
    WHERE b.evaluate_date = e.d
      AND b.quantity > 0
      AND b.asset_subtype != 'BOND_GOVT'
      AND b.maturity_date <= e.d + 5
    GROUP BY b.port_id
),

-- ── 最大單一工具剩餘期限 ─────────────────────────────────
max_maturity AS (
    SELECT t.port_id,
           MAX(t.remaining_days) AS max_days
    FROM (
        -- 債券
        SELECT b.port_id,
               COALESCE(b.remaining_days,
                        (b.maturity_date - '2026-06-25'::DATE)::INT) AS remaining_days
        FROM fsi.balance_bond b
        WHERE b.evaluate_date = '2026-06-25'::DATE
          AND b.quantity > 0
          AND b.maturity_date > '2026-06-25'::DATE

        UNION ALL
        -- 同業存單
        SELECT c.port_id,
               COALESCE(c.remaining_days,
                        (c.maturity_date - '2026-06-25'::DATE)::INT) AS remaining_days
        FROM fsi.balance_cd c
        WHERE c.evaluate_date = '2026-06-25'::DATE
          AND c.maturity_date > '2026-06-25'::DATE

        UNION ALL
        -- 定期存款
        SELECT d.port_id,
               (d.maturity_date - '2026-06-25'::DATE)::INT AS remaining_days
        FROM fsi.balance_deposit d
        WHERE d.evaluate_date = '2026-06-25'::DATE
          AND d.maturity_date IS NOT NULL
          AND d.maturity_date > '2026-06-25'::DATE
    ) t
    JOIN fsi.para_portfolio p ON p.port_id = t.port_id
    WHERE p.is_mmf = TRUE
    GROUP BY t.port_id
),

-- ── 匯總計算 ─────────────────────────────────────────────
agg AS (
    SELECT
        p.port_id,
        p.port_name,
        nav.net_asset,
        COALESCE(ca.cash, 0)                                    AS cash,
        -- DLA 分項
        COALESCE(dg.amt, 0)                                     AS dla_govbond,
        COALESCE(dc.amt, 0)                                     AS dla_cd,
        COALESCE(dd.amt, 0)                                     AS dla_deposit,
        COALESCE(dr.amt, 0)                                     AS dla_revrepo,
        -- WLA 分項
        COALESCE(wg.amt, 0)                                     AS wla_govbond,
        COALESCE(wc.amt, 0)                                     AS wla_cd,
        COALESCE(wd.amt, 0)                                     AS wla_deposit,
        COALESCE(wr.amt, 0)                                     AS wla_revrepo,
        COALESCE(wcb.amt, 0)                                    AS wla_corpbond,
        COALESCE(mx.max_days, 0)                                AS max_instrument_days
    FROM fsi.para_portfolio p
    JOIN nav              ON nav.port_id  = p.port_id
    LEFT JOIN cash_amt ca ON ca.port_id   = p.port_id
    LEFT JOIN dla_govbond  dg  ON dg.port_id  = p.port_id
    LEFT JOIN dla_cd       dc  ON dc.port_id  = p.port_id
    LEFT JOIN dla_deposit  dd  ON dd.port_id  = p.port_id
    LEFT JOIN dla_revrepo  dr  ON dr.port_id  = p.port_id
    LEFT JOIN wla_govbond  wg  ON wg.port_id  = p.port_id
    LEFT JOIN wla_cd       wc  ON wc.port_id  = p.port_id
    LEFT JOIN wla_deposit  wd  ON wd.port_id  = p.port_id
    LEFT JOIN wla_revrepo  wr  ON wr.port_id  = p.port_id
    LEFT JOIN wla_corpbond wcb ON wcb.port_id = p.port_id
    LEFT JOIN max_maturity mx  ON mx.port_id  = p.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
)

SELECT
    port_name,

    -- DLA% = (現金 + 政府債T+1 + CD T+1 + 隔夜存款 + 逆回購T+1) / NAV × 100
    ROUND(
        (cash + dla_govbond + dla_cd + dla_deposit + dla_revrepo)
        / NULLIF(net_asset, 0) * 100
    , 4) AS dla_pct,

    -- WLA% = (現金 + 政府債T+5 + CD T+5 + 存款T+5 + 逆回購T+5 + 信用債T+5) / NAV × 100
    ROUND(
        (cash + wla_govbond + wla_cd + wla_deposit + wla_revrepo + wla_corpbond)
        / NULLIF(net_asset, 0) * 100
    , 4) AS wla_pct,

    -- 最大單一工具剩餘期限（天）
    max_instrument_days,

    -- DLA 合規狀態（SFC 下限 7.5%）
    CASE
        WHEN (cash + dla_govbond + dla_cd + dla_deposit + dla_revrepo)
             / NULLIF(net_asset, 0) * 100 >= 7.5
        THEN '合規'
        ELSE '未達標(≥7.5%)'
    END AS dla_status,

    -- WLA 合規狀態（SFC 下限 15%）
    CASE
        WHEN (cash + wla_govbond + wla_cd + wla_deposit + wla_revrepo + wla_corpbond)
             / NULLIF(net_asset, 0) * 100 >= 15
        THEN '合規'
        ELSE '未達標(≥15%)'
    END AS wla_status,

    -- 最大工具期限合規狀態（SFC 上限 397 天，政府/公共證券 730 天）
    CASE
        WHEN max_instrument_days <= 397
        THEN '合規'
        ELSE '超限(≤397天)'
    END AS mat_status

FROM agg
ORDER BY port_name;
