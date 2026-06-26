-- ============================================================
-- 報表06 / 09_t1_liquidity.sql
-- 原始：SmartReport/06/09.sql  T+1日可用流動性預估
-- 功能：T+1日流動性來源拆解：
--   ① 現金（截止日） ② 自然到期 ③ 回購融出淨差（到期回收-到期還款）
--   ④ 可獲得回購融資（未到期逆回購按折扣率計） ⑤ 債券存單變現
--   ⑥ 協議存款前支取
-- 對應 Sheet：T+1日可用流动性原始
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================
t1_date AS (
    -- T+1（簡化：+1日曆日，生產替換為交易日曆）
    SELECT params.evaluate_date::DATE + 1 AS t1
),

-- ① 現金（活期）
cash AS (
    SELECT v.port_id,
           SUM(CASE WHEN v.subject_code = '100201' THEN COALESCE(v.market_value,0) ELSE 0 END) AS cash
    FROM fsi.balance_valuation_sheet v, params
    WHERE v.port_id = ANY(params.port_ids) AND v.evaluate_date = params.evaluate_date
    GROUP BY v.port_id
),

-- ② 自然到期（T+1 到期的債券/存單/存款）
natural_mature AS (
    SELECT t.port_id, SUM(t.mv) AS mv FROM (
        SELECT b.port_id, SUM(COALESCE(b.cost,0)) * 100 AS mv
        FROM fsi.balance_bond b, t1_date d
        WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
          AND b.maturity_date > params.evaluate_date AND b.maturity_date <= d.t1
        GROUP BY b.port_id

        UNION ALL

        SELECT c.port_id, SUM(COALESCE(c.cost,0)) * 100
        FROM fsi.balance_cd c, t1_date d
        WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date
          AND c.maturity_date > params.evaluate_date AND c.maturity_date <= d.t1
        GROUP BY c.port_id

        UNION ALL

        SELECT d2.port_id, SUM(COALESCE(d2.principal,0)) * 100
        FROM fsi.balance_deposit d2, t1_date d
        WHERE d2.port_id = ANY(params.port_ids) AND d2.evaluate_date = params.evaluate_date
          AND d2.maturity_date > params.evaluate_date AND d2.maturity_date <= d.t1
        GROUP BY d2.port_id
    ) t
    GROUP BY t.port_id
),

-- ③ 回購到期流出淨差 = 逆回購到期回收 - 正回購到期還款
repo_net AS (
    SELECT t.port_id, SUM(t.mv) AS mv FROM (
        -- 逆回購（融出）到期回收（正值）
        SELECT r.port_id,
               SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date) > params.evaluate_date
                             AND COALESCE(r.actual_maturity_date,r.maturity_date) <= (SELECT t1 FROM t1_date)
                        THEN COALESCE(r.principal,0)*100 ELSE 0 END) AS mv
        FROM fsi.balance_repo r
        WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
          AND r.repo_type = 'REV_REPO'
        GROUP BY r.port_id

        UNION ALL

        -- 正回購（融入）到期還款（負值）
        SELECT r.port_id,
               -SUM(CASE WHEN COALESCE(r.actual_maturity_date,r.maturity_date) > params.evaluate_date
                              AND COALESCE(r.actual_maturity_date,r.maturity_date) <= (SELECT t1 FROM t1_date)
                         THEN COALESCE(r.principal,0)*100 ELSE 0 END)
        FROM fsi.balance_repo r
        WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
          AND r.repo_type = 'REPO'
        GROUP BY r.port_id
    ) t
    GROUP BY t.port_id
),

-- ④ 可獲得回購融資（未到期逆回購按折扣率估算可再融資額）
potential_repo AS (
    SELECT r.port_id,
           SUM(COALESCE(r.principal,0) * 0.20) * 100 AS mv   -- 保守估計：20%折扣率
    FROM fsi.balance_repo r, params
    WHERE r.port_id = ANY(params.port_ids) AND r.evaluate_date = params.evaluate_date
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) > (SELECT t1 FROM t1_date)
    GROUP BY r.port_id
),

-- ⑤ 債券存單變現（未到期，按流動性折扣估算）
bond_cd_realize AS (
    SELECT t.port_id, SUM(t.mv) AS mv FROM (
        -- 債券存單按折扣率變現
        SELECT b.port_id, SUM(COALESCE(b.cost,0) * 0.95) * 100 AS mv
        FROM fsi.balance_bond b
        WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
          AND b.maturity_date > (SELECT t1 FROM t1_date)
          AND b.asset_subtype != 'BOND_GOVT'
        GROUP BY b.port_id

        UNION ALL

        SELECT c.port_id, SUM(COALESCE(c.cost,0) * 0.95) * 100
        FROM fsi.balance_cd c
        WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date
          AND c.maturity_date > (SELECT t1 FROM t1_date)
        GROUP BY c.port_id
    ) t
    GROUP BY t.port_id
),

-- ⑥ 協議存款前支取（可提前支取的存款）
deposit_early AS (
    SELECT d.port_id,
           SUM(COALESCE(d.principal,0)) * 100 AS mv
    FROM fsi.balance_deposit d, params
    WHERE d.port_id = ANY(params.port_ids) AND d.evaluate_date = params.evaluate_date
      AND (d.is_penalty_on_early_redeem = FALSE OR d.is_penalty_on_early_redeem IS NULL)
      AND d.maturity_date > (SELECT t1 FROM t1_date)
    GROUP BY d.port_id
)

SELECT
    p.port_name,
    ROUND(COALESCE(c.cash,0)        / 100000000, 4) AS cash_100m,
    ROUND(COALESCE(nm.mv,0)         / 100000000, 4) AS natural_mature_100m,
    ROUND(COALESCE(rn.mv,0)         / 100000000, 4) AS repo_net_100m,
    ROUND(COALESCE(pr.mv,0)         / 100000000, 4) AS potential_repo_100m,
    ROUND(COALESCE(bcr.mv,0)        / 100000000, 4) AS bond_cd_realize_100m,
    ROUND(COALESCE(de.mv,0)         / 100000000, 4) AS deposit_early_100m,
    -- 合計
    ROUND((COALESCE(c.cash,0) + COALESCE(nm.mv,0) + COALESCE(rn.mv,0) +
           COALESCE(pr.mv,0) + COALESCE(bcr.mv,0) + COALESCE(de.mv,0))
          / 100000000, 4)                           AS total_liquidity_100m
FROM fsi.para_portfolio p
JOIN fsi.balance_portfolio_nav n ON n.port_id=p.port_id
    AND n.evaluate_date=params.evaluate_date AND n.class_id IS NULL
LEFT JOIN cash            c   ON c.port_id   = p.port_id
LEFT JOIN natural_mature  nm  ON nm.port_id  = p.port_id
LEFT JOIN repo_net        rn  ON rn.port_id  = p.port_id
LEFT JOIN potential_repo  pr  ON pr.port_id  = p.port_id
LEFT JOIN bond_cd_realize bcr ON bcr.port_id = p.port_id
LEFT JOIN deposit_early   de  ON de.port_id  = p.port_id
WHERE p.port_id = ANY(params.port_ids)
ORDER BY p.port_id;
