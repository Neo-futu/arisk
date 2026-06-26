WITH -- ============================================================
-- 報表03 / 05_assets_5y.sql
-- 原始：SmartReport/03/05.sql  五年以內到期資產
-- 功能：T+1~T+5個交易日內到期的各類資產彙總（流動性管理）
-- 參數：params.evaluate_date DATE, params.trade_days_ahead INT (默認5)
-- ============================================================

date_range AS (
    -- 簡化版：用日曆日計算（生產環境替換為交易日曆查詢）
    SELECT params.evaluate_date::DATE + params.trade_days_ahead AS cutoff_date
),

govt_bond AS (
    SELECT b.port_id, SUM(COALESCE(b.market_value, 0)) / 100000000 AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype = 'BOND_GOVT'
      AND b.maturity_date > params.evaluate_date
      AND b.maturity_date <= '2026-06-25'::DATE + 5
    GROUP BY b.port_id
),

credit_bond AS (
    SELECT b.port_id, SUM(COALESCE(b.market_value, 0)) / 100000000 AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype NOT IN ('BOND_GOVT')
      AND b.maturity_date > params.evaluate_date
      AND b.maturity_date <= '2026-06-25'::DATE + 5
    GROUP BY b.port_id
),

cd AS (
    SELECT c.port_id, SUM(COALESCE(c.market_value, 0)) / 100000000 AS mv
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = params.evaluate_date
      AND c.maturity_date > params.evaluate_date
      AND c.maturity_date <= '2026-06-25'::DATE + 5
    GROUP BY c.port_id
),

deposit AS (
    SELECT dep.port_id, SUM(COALESCE(dep.principal, 0)) / 100000000 AS mv
    FROM fsi.balance_deposit dep
    JOIN fsi.para_portfolio p ON p.port_id = dep.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND dep.evaluate_date = params.evaluate_date
      AND dep.maturity_date > params.evaluate_date
      AND dep.maturity_date <= '2026-06-25'::DATE + 5
    GROUP BY dep.port_id
),

rev_repo AS (
    -- 逆回購（融出，到期收回現金，計入流動資產）
    SELECT r.port_id, SUM(COALESCE(r.principal, 0)) / 100000000 AS mv
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p ON p.port_id = r.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND r.evaluate_date = params.evaluate_date
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) > params.evaluate_date
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= '2026-06-25'::DATE + 5
    GROUP BY r.port_id
)

SELECT
    p.port_name,
    ROUND(COALESCE(g.mv,0) + COALESCE(cb.mv,0) + COALESCE(c.mv,0) +
          COALESCE(dep.mv,0) + COALESCE(rr.mv,0), 4) AS total_100m,
    ROUND(COALESCE(g.mv,  0), 4) AS govt_bond_100m,
    ROUND(COALESCE(cb.mv, 0), 4) AS credit_bond_100m,
    ROUND(COALESCE(c.mv,  0), 4) AS cd_100m,
    ROUND(COALESCE(dep.mv,0), 4) AS deposit_100m,
    ROUND(COALESCE(rr.mv, 0), 4) AS rev_repo_100m,
    params.trade_days_ahead              AS days_window
FROM fsi.para_portfolio p
JOIN fsi.balance_portfolio_nav n ON n.port_id = p.port_id
    AND n.evaluate_date = params.evaluate_date AND n.class_id IS NULL
LEFT JOIN govt_bond  g   ON g.port_id   = p.port_id
LEFT JOIN credit_bond cb ON cb.port_id  = p.port_id
LEFT JOIN cd          c  ON c.port_id   = p.port_id
LEFT JOIN deposit     dep ON dep.port_id = p.port_id
LEFT JOIN rev_repo    rr  ON rr.port_id  = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
