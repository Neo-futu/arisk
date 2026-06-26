-- ============================================================
-- 報表06 / 08_compliance_daily.sql
-- 原始：SmartReport/06/08.sql  十全每日運作簡報（SFC合規核查彙總）
-- 功能：每日 SFC MMF 守則核心指標一覽（規模/每萬份/集中度/流動性/期限/回購）
-- 對應 Sheet：十全每日运作简报原始
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================
nav AS (
    -- 通用 NAV 欄位來自 balance_portfolio_nav（T_Balance_Portfolio）
    -- 貨基專有欄位 income_per_10k/wam_days/wal_days 來自 balance_portfolio_mmf（T_Balance_Portfolio_MMF）
    SELECT n.port_id, n.net_asset,
           m.income_per_10k,
           m.wam_days, m.wal_days, m.nav_deviation
    FROM fsi.balance_portfolio_nav n
    JOIN fsi.balance_portfolio_mmf m ON m.port_id = n.port_id
                                    AND m.evaluate_date = n.evaluate_date
    , params
    WHERE n.port_id = ANY(params.port_ids)
      AND n.evaluate_date = params.evaluate_date
      AND n.class_id IS NULL
),

-- 最大單一信用債/存單/存款佔淨值比（SFC ≤10%）
max_single_credit AS (
    SELECT port_id, MAX(ratio) AS max_credit_ratio FROM (
        SELECT b.port_id,
               COALESCE(b.cost,0) / NULLIF(n2.net_asset,0) * 100 AS ratio
        FROM fsi.balance_bond b
        JOIN fsi.balance_portfolio_nav n2 ON n2.port_id=b.port_id
            AND n2.evaluate_date=b.evaluate_date AND n2.class_id IS NULL
        WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
          AND b.asset_subtype != 'BOND_GOVT'

        UNION ALL

        SELECT c.port_id, COALESCE(c.cost,0) / NULLIF(n2.net_asset,0) * 100
        FROM fsi.balance_cd c
        JOIN fsi.balance_portfolio_nav n2 ON n2.port_id=c.port_id
            AND n2.evaluate_date=c.evaluate_date AND n2.class_id IS NULL
        WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date

        UNION ALL

        SELECT d.port_id, COALESCE(d.principal,0) / NULLIF(n2.net_asset,0) * 100
        FROM fsi.balance_deposit d
        JOIN fsi.balance_portfolio_nav n2 ON n2.port_id=d.port_id
            AND n2.evaluate_date=d.evaluate_date AND n2.class_id IS NULL
        WHERE d.port_id = ANY(params.port_ids) AND d.evaluate_date = params.evaluate_date
    ) t
    GROUP BY port_id
),

-- 流動受限資產（提前支取有罰息的存款 + 超10個交易日逆回購）佔NAV比
restricted_assets AS (
    SELECT port_id, SUM(restricted_mv) / NULLIF(net_asset,0) * 100 AS restricted_ratio
    FROM (
        SELECT d.port_id, SUM(COALESCE(d.principal,0)) AS restricted_mv,
               MAX(n2.net_asset) AS net_asset
        FROM fsi.balance_deposit d
        JOIN fsi.balance_portfolio_nav n2 ON n2.port_id=d.port_id
            AND n2.evaluate_date=d.evaluate_date AND n2.class_id IS NULL
        WHERE d.port_id = ANY(params.port_ids) AND d.evaluate_date = params.evaluate_date
          AND d.is_penalty_on_early_redeem = TRUE
          AND d.maturity_date > params.evaluate_date::DATE + 10
        GROUP BY d.port_id

        UNION ALL

        SELECT r.port_id, SUM(COALESCE(r.principal,0)) AS restricted_mv,
               MAX(n2.net_asset) AS net_asset
        FROM fsi.balance_repo r
        JOIN fsi.balance_portfolio_nav n2 ON n2.port_id=r.port_id
            AND n2.evaluate_date=r.evaluate_date AND n2.class_id IS NULL
        WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
          AND r.repo_type = 'REV_REPO'
          AND COALESCE(r.actual_maturity_date, r.maturity_date) > params.evaluate_date::DATE + 10
        GROUP BY r.port_id
    ) x
    GROUP BY port_id, net_asset
),

-- 正回購佔NAV比
repo_ratio AS (
    SELECT r.port_id,
           SUM(COALESCE(r.principal,0)) / NULLIF(n2.net_asset,0) * 100 AS repo_pct
    FROM fsi.balance_repo r
    JOIN fsi.balance_portfolio_nav n2 ON n2.port_id=r.port_id
        AND n2.evaluate_date=r.evaluate_date AND n2.class_id IS NULL
    WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
      AND r.repo_type = 'REPO'
    GROUP BY r.port_id
),

-- 前十大持有人集中度
top10 AS (
    SELECT h.port_id, SUM(h.pct_of_total) AS top10_pct
    FROM fsi.balance_holder_rank h, params
    WHERE h.port_id = ANY(params.port_ids) AND h.confirm_date = params.evaluate_date AND h.rank_no <= 10
    GROUP BY h.port_id
),

-- 最長利率債剩餘期限
max_govt_days AS (
    SELECT b.port_id, MAX(b.remaining_days) AS max_days
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype = 'BOND_GOVT'
    GROUP BY b.port_id
),

-- 最長存單剩餘期限
max_cd_days AS (
    SELECT c.port_id, MAX(c.remaining_days) AS max_days
    FROM fsi.balance_cd c, params
    WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date
    GROUP BY c.port_id
),

-- 浮息債中剩餘期限>1年的金額佔NAV
float_gt1y AS (
    SELECT b.port_id,
           SUM(CASE WHEN b.coupon_type='FLOAT' AND b.remaining_days>365
                    THEN COALESCE(b.cost,0) ELSE 0 END) * 100
           / NULLIF(n2.net_asset,0) AS float_gt1y_pct
    FROM fsi.balance_bond b
    JOIN fsi.balance_portfolio_nav n2 ON n2.port_id=b.port_id
        AND n2.evaluate_date=b.evaluate_date AND n2.class_id IS NULL
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
    GROUP BY b.port_id, n2.net_asset
)

SELECT
    p.port_name,
    ROUND(n.net_asset / 100000000, 4)                       AS net_asset_100m,
    ROUND(n.income_per_10k, 4)                              AS income_per_10k,
    ROUND(COALESCE(mc.max_credit_ratio,0), 4)               AS max_single_credit_pct,
    ROUND(COALESCE(ra.restricted_ratio,0), 4)               AS restricted_asset_pct,
    ROUND(n.wam_days, 2)                                    AS wam_days,
    ROUND(n.wal_days, 2)                                    AS wal_days,
    COALESCE(mg.max_days, 0)                                AS max_govt_bond_days,
    COALESCE(mcd.max_days, 0)                               AS max_cd_days,
    ROUND(COALESCE(fl.float_gt1y_pct,0), 4)                AS float_gt1y_pct,
    ROUND(COALESCE(rr.repo_pct,0), 4)                      AS repo_pct,
    ROUND(COALESCE(t10.top10_pct,0), 4)                    AS top10_holder_pct,
    -- SFC 合規狀態
    CASE WHEN n.wam_days <= 60  THEN 'OK' ELSE 'BREACH' END AS wam_status,
    CASE WHEN n.wal_days <= 120 THEN 'OK' ELSE 'BREACH' END AS wal_status
FROM nav n
JOIN fsi.para_portfolio p ON p.port_id = n.port_id
LEFT JOIN max_single_credit mc  ON mc.port_id  = n.port_id
LEFT JOIN restricted_assets ra  ON ra.port_id  = n.port_id
LEFT JOIN repo_ratio         rr  ON rr.port_id  = n.port_id
LEFT JOIN top10              t10 ON t10.port_id = n.port_id
LEFT JOIN max_govt_days      mg  ON mg.port_id  = n.port_id
LEFT JOIN max_cd_days        mcd ON mcd.port_id = n.port_id
LEFT JOIN float_gt1y         fl  ON fl.port_id  = n.port_id
ORDER BY n.port_id;
