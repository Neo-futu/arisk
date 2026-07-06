-- ============================================================
-- 報表06 / 01_asset_breakdown.sql
-- 原始：SmartReport/06/01.sql  資產分佈表1
-- 對應 Sheet：资产分布原始（A3 起填入）
-- ============================================================
-- ★ 修改下面兩行即可在 pgAdmin / psql 獨立運行
-- ============================================================
WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================

outline AS (
    SELECT
        v.port_id,
        SUM(CASE WHEN v.subject_code = '100201' THEN COALESCE(v.market_value, 0) ELSE 0 END) AS cash,
        SUM(CASE WHEN v.subject_code = '100203' THEN COALESCE(v.market_value, 0) ELSE 0 END) AS deposit,
        SUM(CASE WHEN v.subject_code = '1111'   THEN COALESCE(v.market_value, 0) ELSE 0 END) AS bond,
        SUM(CASE WHEN v.subject_code = '1202'   THEN COALESCE(v.market_value, 0) ELSE 0 END) AS rev_repo,
        SUM(CASE WHEN v.subject_code = '831'    THEN COALESCE(v.market_value, 0) ELSE 0 END) AS total_asset,
        SUM(CASE WHEN v.subject_code = '2202'   THEN COALESCE(v.market_value, 0) ELSE 0 END) AS repo
    FROM fsi.balance_valuation_sheet v, params
    WHERE v.port_id = ANY(params.port_ids)
      AND v.evaluate_date = params.evaluate_date
      AND v.subject_code IN ('100201','100203','1111','1202','831','2202')
    GROUP BY v.port_id
),

deposit_breakable AS (
    -- IsInterestPenalty='N' → is_penalty_on_early_redeem = FALSE（可提前支取）
    SELECT d.port_id,
           SUM(CASE WHEN d.is_penalty_on_early_redeem = FALSE
                        OR d.is_penalty_on_early_redeem IS NULL
                    THEN COALESCE(d.principal, 0) ELSE 0 END) AS ck_tz
    FROM fsi.balance_deposit d, params
    WHERE d.port_id = ANY(params.port_ids)
      AND d.evaluate_date = params.evaluate_date
    GROUP BY d.port_id
),

bond_detail AS (
    SELECT b.port_id,
           SUM(CASE WHEN b.asset_subtype = 'BOND_GOVT'
                    THEN COALESCE(b.market_value, 0) ELSE 0 END) AS govt_bond,
           SUM(CASE WHEN b.asset_subtype != 'BOND_GOVT'
                    THEN COALESCE(b.market_value, 0) ELSE 0 END) AS credit_bond,
           SUM(CASE WHEN b.asset_subtype != 'BOND_GOVT'
                        AND b.issuer_rating NOT IN ('AAA','AAA+','AA+')
                    THEN COALESCE(b.market_value, 0) ELSE 0 END) AS credit_below_aaplus
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids)
      AND b.evaluate_date = params.evaluate_date
    GROUP BY b.port_id
),

cd_detail AS (
    SELECT c.port_id,
           SUM(COALESCE(c.market_value, 0)) AS cd_total,
           SUM(CASE WHEN c.issuer_rating NOT IN ('AAA','AAA+','AA+')
                    THEN COALESCE(c.market_value, 0) ELSE 0 END) AS cd_below_aaplus
    FROM fsi.balance_cd c, params
    WHERE c.port_id = ANY(params.port_ids)
      AND c.evaluate_date = params.evaluate_date
    GROUP BY c.port_id
)

SELECT
    o.port_id,
    ROUND(o.cash         / 100000000, 4) AS cash_100m,
    ROUND(o.deposit      / 100000000, 4) AS deposit_100m,
    ROUND(o.bond         / 100000000, 4) AS bond_100m,
    ROUND(o.rev_repo     / 100000000, 4) AS rev_repo_100m,
    ROUND(o.total_asset  / 100000000, 4) AS total_asset_100m,
    ROUND(o.repo         / 100000000, 4) AS repo_100m,
    ROUND(COALESCE(d.ck_tz, 0)              / 100000000, 4) AS deposit_breakable_100m,
    ROUND(COALESCE(b.govt_bond, 0)          / 100000000, 4) AS govt_bond_100m,
    ROUND(COALESCE(b.credit_bond, 0)        / 100000000, 4) AS credit_bond_100m,
    ROUND(COALESCE(c.cd_total, 0)           / 100000000, 4) AS cd_100m,
    ROUND(COALESCE(c.cd_below_aaplus, 0)    / 100000000, 4) AS cd_below_aaplus_100m,
    ROUND(COALESCE(b.credit_below_aaplus, 0)/ 100000000, 4) AS credit_below_aaplus_100m
FROM outline o
LEFT JOIN deposit_breakable d ON d.port_id = o.port_id
LEFT JOIN bond_detail       b ON b.port_id = o.port_id
LEFT JOIN cd_detail         c ON c.port_id = o.port_id
ORDER BY o.port_id;
