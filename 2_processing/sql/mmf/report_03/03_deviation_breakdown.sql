-- ============================================================
-- 報表03 / 03_deviation_breakdown.sql
-- 原始：SmartReport/03/03.sql  偏離按品種拆分
-- 功能：影子定價偏差拆解為：CD / 企業債(CP/短融) / 政府債 / ABS
-- ★ 修改下面 evaluate_date 值即可獨立運行
-- ============================================================

WITH total_deviation AS (
    -- 總偏差從 balance_portfolio_mmf 取（T_Balance_Portfolio_MMF.DeviationAmount）
    SELECT
        m.port_id,
        p.port_name,
        m.nav_deviation_amount AS deviation_amount
    FROM fsi.balance_portfolio_mmf m
    JOIN fsi.para_portfolio p ON p.port_id = m.port_id
    WHERE p.is_mmf = TRUE
      AND p.is_active = TRUE
      AND m.evaluate_date = '2026-06-25'::DATE
),

cd_dev AS (
    SELECT c.port_id,
           SUM(COALESCE(c.market_value, 0) - COALESCE(c.cost, 0)) AS cd_deviation
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
    GROUP BY c.port_id
),

bond_dev AS (
    SELECT b.port_id,
           SUM(CASE WHEN b.asset_subtype = 'BOND_GOVT'
                    THEN COALESCE(b.market_value,0) - COALESCE(b.cost,0) ELSE 0 END) AS govt_deviation,
           SUM(CASE WHEN b.asset_subtype IN ('BOND_CORP','CP')
                    THEN COALESCE(b.market_value,0) - COALESCE(b.cost,0) ELSE 0 END) AS corp_deviation,
           SUM(CASE WHEN b.asset_subtype = 'BOND_ABS'
                    THEN COALESCE(b.market_value,0) - COALESCE(b.cost,0) ELSE 0 END) AS abs_deviation
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
    GROUP BY b.port_id
)

SELECT
    t.port_name,
    ROUND(t.deviation_amount, 2)                              AS total_deviation,
    ROUND(COALESCE(c.cd_deviation, 0), 2)                    AS cd_deviation,
    ROUND(COALESCE(b.corp_deviation, 0), 2)                  AS corp_bond_deviation,
    ROUND(COALESCE(b.govt_deviation, 0), 2)                  AS govt_bond_deviation,
    ROUND(COALESCE(b.abs_deviation, 0), 2)                   AS abs_deviation,
    ROUND(COALESCE(c.cd_deviation, 0) /
          NULLIF(t.deviation_amount, 0), 6)                  AS cd_pct,
    ROUND(COALESCE(b.corp_deviation, 0) /
          NULLIF(t.deviation_amount, 0), 6)                  AS corp_pct,
    ROUND(COALESCE(b.govt_deviation, 0) /
          NULLIF(t.deviation_amount, 0), 6)                  AS govt_pct
FROM total_deviation t
LEFT JOIN cd_dev   c ON c.port_id = t.port_id
LEFT JOIN bond_dev b ON b.port_id = t.port_id
ORDER BY t.port_name;
