WITH -- ============================================================
-- 報表03 / 06_asset_portfolio.sql
-- 原始：SmartReport/03/06.sql  資產組合月度（含各細分類）
-- 功能：NAV/現金/債券/存款/CD/逆回購/正回購 + 利率債/浮息債/信用債/計息存款細分
-- 參數：params.evaluate_date DATE
-- ============================================================

base AS (
    SELECT
        p.port_name,
        a.port_id,
        SUM(CASE WHEN a.asset_class = 'CASH'     THEN COALESCE(a.market_value,0) ELSE 0 END) / 100000000 AS cash,
        SUM(CASE WHEN a.asset_class IN ('BOND_GOVT','BOND_CORP','BOND_ABS','CP','BOND_CONVERT')
                 THEN COALESCE(a.market_value,0) ELSE 0 END) / 100000000                                  AS bond,
        SUM(CASE WHEN a.asset_class = 'DEPOSIT'  THEN COALESCE(a.market_value,0) ELSE 0 END) / 100000000 AS deposit,
        SUM(CASE WHEN a.asset_class = 'CD'       THEN COALESCE(a.market_value,0) ELSE 0 END) / 100000000 AS cd,
        SUM(CASE WHEN a.asset_class = 'REV_REPO' THEN COALESCE(a.market_value,0) ELSE 0 END) / 100000000 AS rev_repo,
        SUM(CASE WHEN a.asset_class = 'REPO'     THEN COALESCE(a.market_value,0) ELSE 0 END) / 100000000 AS repo
    FROM fsi.balance_portfolio_asset a
    JOIN fsi.para_portfolio p ON p.port_id = a.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND a.evaluate_date = params.evaluate_date
    GROUP BY p.port_name, a.port_id
),

nav AS (
    SELECT port_id, net_asset / 100000000 AS net_asset
    FROM fsi.balance_portfolio_nav, params
    WHERE evaluate_date = params.evaluate_date AND class_id IS NULL
),

-- 債券細分
govt_bond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.market_value,0)) / 100000000  AS govt_bond,
           -- 浮息債（floating rate）
           SUM(CASE WHEN b.coupon_type = 'FLOAT'
                    THEN COALESCE(b.market_value,0) ELSE 0 END) / 100000000 AS float_bond
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id, params
    WHERE p.is_mmf = TRUE AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype = 'BOND_GOVT'
    GROUP BY b.port_id
),

credit_bond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.market_value,0)) / 100000000 AS credit_bond
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id, params
    WHERE p.is_mmf = TRUE AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype NOT IN ('BOND_GOVT')
    GROUP BY b.port_id
),

-- 存款細分：計息（提前支取有罰息）vs 不計息
deposit_detail AS (
    SELECT d.port_id,
           SUM(CASE WHEN d.is_penalty_on_early_redeem = TRUE
                    THEN COALESCE(d.principal,0) ELSE 0 END) / 100000000 AS deposit_penalty,   -- 有罰息（不可提前支取）
           SUM(CASE WHEN d.is_penalty_on_early_redeem = FALSE OR d.is_penalty_on_early_redeem IS NULL
                    THEN COALESCE(d.principal,0) ELSE 0 END) / 100000000 AS deposit_breakable  -- 可提前支取
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id, params
    WHERE p.is_mmf = TRUE AND d.evaluate_date = params.evaluate_date
    GROUP BY d.port_id
)

SELECT
    b.port_name,
    ROUND(n.net_asset, 4)                                AS net_asset_100m,
    ROUND(b.cash, 4)                                     AS cash_100m,
    ROUND(b.bond, 4)                                     AS bond_total_100m,
    ROUND(b.deposit, 4)                                  AS deposit_total_100m,
    ROUND(b.cd, 4)                                       AS cd_100m,
    ROUND(b.rev_repo, 4)                                 AS rev_repo_100m,
    ROUND(b.repo, 4)                                     AS repo_100m,
    -- 債券細分
    ROUND(COALESCE(g.govt_bond, 0), 4)                   AS govt_bond_100m,
    ROUND(COALESCE(g.float_bond, 0), 4)                  AS float_bond_100m,
    ROUND(COALESCE(cr.credit_bond, 0), 4)               AS credit_bond_100m,
    -- 存款細分
    ROUND(COALESCE(d.deposit_penalty, 0), 4)             AS deposit_with_penalty_100m,
    ROUND(COALESCE(d.deposit_breakable, 0), 4)           AS deposit_breakable_100m
FROM base b
JOIN nav n ON n.port_id = b.port_id
LEFT JOIN govt_bond      g  ON g.port_id  = b.port_id
LEFT JOIN credit_bond    cr ON cr.port_id = b.port_id
LEFT JOIN deposit_detail d  ON d.port_id  = b.port_id
ORDER BY b.port_name;
