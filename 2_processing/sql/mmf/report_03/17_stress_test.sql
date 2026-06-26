WITH -- ============================================================
-- 報表03 / 17_stress_test.sql
-- 原始：SmartReport/03/17.sql  壓力測試分佈（+50bp利率衝擊）
-- 功能：各持倉的壓測後估值、偏差貢獻
-- 參數：params.evaluate_date DATE, params.rate_shock_bps NUMERIC (默認50)
-- ============================================================

shock AS (
    SELECT COALESCE(params.rate_shock_bps, 50) / 10000.0 AS rate_shock  -- 50bps → 0.005
),

bond_positions AS (
    SELECT
        b.port_id,
        b.security_code,
        b.security_name,
        b.asset_subtype::TEXT                       AS bond_type,
        b.coupon_type,
        b.quantity,
        b.cost,
        COALESCE(b.market_value, 0)                 AS market_value,
        COALESCE(b.accrued_interest, 0)             AS accrued_interest,
        COALESCE(b.market_value, 0) / NULLIF(n.net_asset, 0) * 100 AS pct_of_nav,
        COALESCE(b.market_value, 0) - COALESCE(b.cost, 0)          AS deviation,
        b.maturity_date,
        COALESCE(b.duration, b.remaining_days / 365.0)              AS duration,
        -- 壓測後市值 = 市值 × (1 - duration × rate_shock)
        COALESCE(b.market_value, 0) *
            (1 - COALESCE(b.duration, b.remaining_days/365.0) * s.rate_shock) AS stressed_mv,
        -- 壓測偏差貢獻（萬元）
        (COALESCE(b.market_value,0) *
            (1 - COALESCE(b.duration, b.remaining_days/365.0) * s.rate_shock)
         - COALESCE(b.cost,0)) / 10000                              AS stressed_deviation_contribution,
        CASE
            WHEN b.maturity_date <= DATE_TRUNC('quarter',params.evaluate_date::DATE)
                                  + INTERVAL '3 month' - INTERVAL '1 day'
            THEN '是當季到期' ELSE '不是當季到期'
        END AS is_current_quarter,
        b.issuer_rating,
        CASE
            WHEN b.asset_subtype = 'BOND_GOVT'          THEN '政府/利率債'
            WHEN b.issuer_rating IN ('A+','A')           THEN 'AA-以下'
            ELSE COALESCE(b.issuer_rating, 'NR')
        END AS credit_label
    FROM fsi.balance_bond b
    JOIN fsi.balance_portfolio_nav n ON n.port_id = b.port_id
        AND n.evaluate_date = b.evaluate_date AND n.class_id IS NULL
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    CROSS JOIN shock s
    WHERE p.is_mmf = TRUE AND b.evaluate_date = params.evaluate_date
      AND b.quantity > 0
),

cd_positions AS (
    SELECT
        c.port_id,
        c.security_code,
        c.security_name,
        'CD'                                        AS bond_type,
        'FIXED'                                     AS coupon_type,
        c.quantity,
        c.cost,
        COALESCE(c.market_value, 0)                 AS market_value,
        0                                           AS accrued_interest,
        COALESCE(c.market_value,0) / NULLIF(n.net_asset,0) * 100   AS pct_of_nav,
        COALESCE(c.market_value,0) - COALESCE(c.cost,0)             AS deviation,
        c.maturity_date,
        COALESCE(c.duration, c.remaining_days/365.0) AS duration,
        COALESCE(c.market_value,0) *
            (1 - COALESCE(c.duration, c.remaining_days/365.0) * s.rate_shock) AS stressed_mv,
        (COALESCE(c.market_value,0) *
            (1 - COALESCE(c.duration,c.remaining_days/365.0)*s.rate_shock)
          - COALESCE(c.cost,0)) / 10000                             AS stressed_deviation_contribution,
        CASE
            WHEN c.maturity_date <= DATE_TRUNC('quarter',params.evaluate_date::DATE)
                                  + INTERVAL '3 month' - INTERVAL '1 day'
            THEN '是當季到期' ELSE '不是當季到期'
        END AS is_current_quarter,
        c.issuer_rating,
        COALESCE(c.issuer_rating, 'NR') AS credit_label
    FROM fsi.balance_cd c
    JOIN fsi.balance_portfolio_nav n ON n.port_id = c.port_id
        AND n.evaluate_date = c.evaluate_date AND n.class_id IS NULL
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    CROSS JOIN shock s
    WHERE p.is_mmf = TRUE AND c.evaluate_date = params.evaluate_date
      AND c.maturity_date >= params.evaluate_date
)

SELECT
    p.port_name,
    pos.bond_type,
    pos.security_code,
    pos.security_name,
    ROUND(pos.quantity, 2)                               AS quantity,
    ROUND(pos.cost, 2)                                   AS cost,
    ROUND(pos.market_value, 2)                           AS market_value,
    ROUND(pos.pct_of_nav, 4)                             AS pct_of_nav,
    ROUND(pos.deviation / 10000, 4)                      AS deviation_10k,
    pos.maturity_date,
    pos.coupon_type,
    ROUND(pos.duration, 4)                               AS duration,
    pos.credit_label,
    pos.is_current_quarter,
    ROUND(pos.stressed_mv / 100000000, 4)                AS stressed_mv_100m,
    ROUND(pos.stressed_deviation_contribution, 4)        AS stressed_dev_contribution_10k,
    ABS(ROUND(pos.stressed_deviation_contribution, 4))   AS stressed_dev_abs
FROM (SELECT * FROM bond_positions UNION ALL SELECT * FROM cd_positions) pos
JOIN fsi.para_portfolio p ON p.port_id = pos.port_id
ORDER BY p.port_name, pos.is_current_quarter,
         ABS(pos.stressed_deviation_contribution) DESC,
         pos.pct_of_nav DESC;
