-- ============================================================
-- 報表06 / 06_asset_liquidity.sql
-- 原始：SmartReport/06/06.sql  貨幣基金流動性（資產變現情況）
-- 功能：各資產類別按到期天數（T+1~T+7）統計可變現金額
-- 對應 Sheet：资产变现原始
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================
govt_bond AS (
    SELECT b.port_id,
           ROUND(SUM(CASE WHEN b.remaining_days = 1 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d1,
           ROUND(SUM(CASE WHEN b.remaining_days = 2 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d2,
           ROUND(SUM(CASE WHEN b.remaining_days = 3 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d3,
           ROUND(SUM(CASE WHEN b.remaining_days = 4 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d4,
           ROUND(SUM(CASE WHEN b.remaining_days = 5 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d5,
           ROUND(SUM(CASE WHEN b.remaining_days = 6 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d6,
           ROUND(SUM(CASE WHEN b.remaining_days = 7 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d7,
           '政府/利率債' AS asset_type
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype = 'BOND_GOVT'
    GROUP BY b.port_id
),

credit_bond AS (
    SELECT b.port_id,
       ROUND(SUM(CASE WHEN b.remaining_days = 1 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d1,
       ROUND(SUM(CASE WHEN b.remaining_days = 2 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d2,
       ROUND(SUM(CASE WHEN b.remaining_days = 3 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d3,
       ROUND(SUM(CASE WHEN b.remaining_days = 4 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d4,
       ROUND(SUM(CASE WHEN b.remaining_days = 5 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d5,
       ROUND(SUM(CASE WHEN b.remaining_days = 6 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d6,
       ROUND(SUM(CASE WHEN b.remaining_days = 7 THEN COALESCE(b.cost,0) ELSE 0 END)*100/100000000,4) AS d7,
       '信用債' AS asset_type
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype != 'BOND_GOVT'
    GROUP BY b.port_id
),

cd AS (
    SELECT c.port_id,
       ROUND(SUM(CASE WHEN c.remaining_days = 1 THEN COALESCE(c.cost,0) ELSE 0 END)*100/100000000,4) AS d1,
       ROUND(SUM(CASE WHEN c.remaining_days = 2 THEN COALESCE(c.cost,0) ELSE 0 END)*100/100000000,4) AS d2,
       ROUND(SUM(CASE WHEN c.remaining_days = 3 THEN COALESCE(c.cost,0) ELSE 0 END)*100/100000000,4) AS d3,
       ROUND(SUM(CASE WHEN c.remaining_days = 4 THEN COALESCE(c.cost,0) ELSE 0 END)*100/100000000,4) AS d4,
       ROUND(SUM(CASE WHEN c.remaining_days = 5 THEN COALESCE(c.cost,0) ELSE 0 END)*100/100000000,4) AS d5,
       ROUND(SUM(CASE WHEN c.remaining_days = 6 THEN COALESCE(c.cost,0) ELSE 0 END)*100/100000000,4) AS d6,
       ROUND(SUM(CASE WHEN c.remaining_days = 7 THEN COALESCE(c.cost,0) ELSE 0 END)*100/100000000,4) AS d7,
       '存款證(CD)' AS asset_type
    FROM fsi.balance_cd c, params
    WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date
    GROUP BY c.port_id
),

-- 銀行間逆回購（融出，到期收回）
ib_rev_repo AS (
    SELECT r.port_id,
       ROUND(SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=1 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d1,
       ROUND(SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=2 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d2,
       ROUND(SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=3 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d3,
       ROUND(SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=4 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d4,
       ROUND(SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=5 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d5,
       ROUND(SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=6 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d6,
       ROUND(SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=7 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d7,
       '銀行間逆回購' AS asset_type
    FROM fsi.balance_repo r, params
    WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
      AND r.repo_type = 'REV_REPO'
      AND r.market_id LIKE '%IB%' OR r.market_id IS NULL   -- 銀行間市場
    GROUP BY r.port_id
),

-- 正回購（融入，到期還款，負流動性）
repo_outflow AS (
    SELECT r.port_id,
       ROUND(-SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=1 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d1,
       ROUND(-SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=2 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d2,
       ROUND(-SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=3 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d3,
       ROUND(-SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=4 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d4,
       ROUND(-SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=5 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d5,
       ROUND(-SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=6 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d6,
       ROUND(-SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date)-r.evaluate_date=7 THEN COALESCE(r.principal,0) ELSE 0 END)*100/100000000,4) AS d7,
       '正回購（融入還款）' AS asset_type
    FROM fsi.balance_repo r, params
    WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
      AND r.repo_type = 'REPO'
    GROUP BY r.port_id
)

SELECT p.port_name, t.asset_type, t.d1, t.d2, t.d3, t.d4, t.d5, t.d6, t.d7
FROM (
    SELECT port_id, asset_type, d1, d2, d3, d4, d5, d6, d7 FROM govt_bond
    UNION ALL SELECT port_id, asset_type, d1, d2, d3, d4, d5, d6, d7 FROM credit_bond
    UNION ALL SELECT port_id, asset_type, d1, d2, d3, d4, d5, d6, d7 FROM cd
    UNION ALL SELECT port_id, asset_type, d1, d2, d3, d4, d5, d6, d7 FROM ib_rev_repo
    UNION ALL SELECT port_id, asset_type, d1, d2, d3, d4, d5, d6, d7 FROM repo_outflow
) t
JOIN fsi.para_portfolio p ON p.port_id = t.port_id
ORDER BY p.port_name, t.asset_type;
