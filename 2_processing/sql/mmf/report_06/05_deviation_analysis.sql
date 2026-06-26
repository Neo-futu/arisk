-- ============================================================
-- 報表06 / 05_deviation_analysis.sql
-- 原始：SmartReport/06/05.sql  影子定價偏離度分析（壓力情景）
-- 功能：當前偏離度 + 低/中/高壓情景測試 + 各品種成本/市值/久期拆解
-- 對應 Sheet：影子定价偏离度原始
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================
nav_deviation AS (
    -- nav_deviation/nav_deviation_amount 已移至 balance_portfolio_mmf（T_Balance_Portfolio_MMF）
    SELECT
        n.port_id,
        n.net_asset,
        COALESCE(m.nav_deviation_amount, 0) AS deviation_amount,
        COALESCE(m.nav_deviation, 0)        AS deviation_pct
    FROM fsi.balance_portfolio_nav n
    JOIN fsi.balance_portfolio_mmf m ON m.port_id = n.port_id
                                    AND m.evaluate_date = n.evaluate_date
    , params
    WHERE n.port_id = ANY(params.port_ids)
      AND n.evaluate_date = params.evaluate_date
      AND n.class_id IS NULL
),

-- 政府/利率債（低風險）：用於低/中/高壓情景
govt_bond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost, 0)) * 100                           AS lv_cost,
           SUM(COALESCE(b.market_value, 0)) * 100                   AS lv_mv,
           SUM(COALESCE(b.market_value,0) *
               COALESCE(b.duration, b.remaining_days/365.0)) /
               NULLIF(SUM(COALESCE(b.market_value,0)),0)            AS lv_duration
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype = 'BOND_GOVT'
    GROUP BY b.port_id
),

-- AAA 信用債
credit_aaa AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost,0)) * 100          AS cost,
           SUM(COALESCE(b.market_value,0)) * 100  AS mv,
           SUM(COALESCE(b.market_value,0) *
               COALESCE(b.duration, b.remaining_days/365.0)) /
               NULLIF(SUM(COALESCE(b.market_value,0)),0) AS duration
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype != 'BOND_GOVT'
      AND b.issuer_rating IN ('AAA','AAA+')
    GROUP BY b.port_id
),

-- AAA 存款證
cd_aaa AS (
    SELECT c.port_id,
           SUM(COALESCE(c.cost,0)) * 100          AS cost,
           SUM(COALESCE(c.market_value,0)) * 100  AS mv,
           SUM(COALESCE(c.market_value,0) *
               COALESCE(c.duration, c.remaining_days/365.0)) /
               NULLIF(SUM(COALESCE(c.market_value,0)),0) AS duration
    FROM fsi.balance_cd c, params
    WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date
      AND c.issuer_rating IN ('AAA','AAA+')
    GROUP BY c.port_id
),

-- AA+ 信用債
credit_aaplus AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost,0)) * 100          AS cost,
           SUM(COALESCE(b.market_value,0)) * 100  AS mv,
           SUM(COALESCE(b.market_value,0) *
               COALESCE(b.duration, b.remaining_days/365.0)) /
               NULLIF(SUM(COALESCE(b.market_value,0)),0) AS duration
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype != 'BOND_GOVT'
      AND b.issuer_rating IN ('AA+')
    GROUP BY b.port_id
),

-- AA+ 存款證
cd_aaplus AS (
    SELECT c.port_id,
           SUM(COALESCE(c.cost,0)) * 100          AS cost,
           SUM(COALESCE(c.market_value,0)) * 100  AS mv,
           SUM(COALESCE(c.market_value,0) *
               COALESCE(c.duration, c.remaining_days/365.0)) /
               NULLIF(SUM(COALESCE(c.market_value,0)),0) AS duration
    FROM fsi.balance_cd c, params
    WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date
      AND c.issuer_rating IN ('AA+')
    GROUP BY c.port_id
),

-- 所有持倉加權平均久期（用於整體偏差彙總）
all_duration AS (
    SELECT b.port_id,
           SUM(COALESCE(b.market_value,0)) AS total_mv,
           SUM(COALESCE(b.market_value,0) *
               COALESCE(b.duration, b.remaining_days/365.0)) AS mv_dur
    FROM fsi.balance_bond b, params
    WHERE b.port_id = ANY(params.port_ids) AND b.evaluate_date = params.evaluate_date
    GROUP BY b.port_id
)

SELECT
    nd.port_id,
    -- 當前偏離度（bps）
    ROUND(nd.deviation_pct * 100, 4)                                     AS current_deviation_bp,
    -- 低壓情景（利率+0.5%，久期×0.5）：利率債承壓
    ROUND((nd.deviation_amount * 10000
           - 50 * COALESCE(g.lv_mv,0) * COALESCE(g.lv_duration,0))
          / NULLIF(nd.net_asset,0), 6)                                   AS low_stress_deviation,
    -- 中壓情景（利率+0.75%）
    ROUND((nd.deviation_amount * 10000
           - 75 * COALESCE(g.lv_mv,0) * COALESCE(g.lv_duration,0))
          / NULLIF(nd.net_asset,0), 6)                                   AS mid_stress_deviation,
    -- 高壓情景（利率+1%）
    ROUND((nd.deviation_amount * 10000
           - 100 * COALESCE(g.lv_mv,0) * COALESCE(g.lv_duration,0))
          / NULLIF(nd.net_asset,0), 6)                                   AS high_stress_deviation,
    -- 利率債明細
    ROUND(COALESCE(g.lv_cost,0) / 100000000, 4)                         AS govt_bond_cost_100m,
    ROUND(COALESCE(g.lv_mv,0)   / 100000000, 4)                         AS govt_bond_mv_100m,
    ROUND(COALESCE(g.lv_duration,0), 4)                                  AS govt_bond_duration,
    -- AAA 信用債
    ROUND(COALESCE(ca.cost,0)   / 100000000, 4)                         AS credit_aaa_cost_100m,
    ROUND(COALESCE(ca.mv,0)     / 100000000, 4)                         AS credit_aaa_mv_100m,
    ROUND(COALESCE(ca.duration,0), 4)                                    AS credit_aaa_duration,
    -- AAA 存款證
    ROUND(COALESCE(cda.cost,0)  / 100000000, 4)                         AS cd_aaa_cost_100m,
    ROUND(COALESCE(cda.mv,0)    / 100000000, 4)                         AS cd_aaa_mv_100m,
    ROUND(COALESCE(cda.duration,0), 4)                                   AS cd_aaa_duration,
    -- AA+ 信用債
    ROUND(COALESCE(cap.cost,0)  / 100000000, 4)                         AS credit_aaplus_cost_100m,
    ROUND(COALESCE(cap.mv,0)    / 100000000, 4)                         AS credit_aaplus_mv_100m,
    ROUND(COALESCE(cap.duration,0), 4)                                   AS credit_aaplus_duration,
    -- AA+ 存款證
    ROUND(COALESCE(cdp.cost,0)  / 100000000, 4)                         AS cd_aaplus_cost_100m,
    ROUND(COALESCE(cdp.mv,0)    / 100000000, 4)                         AS cd_aaplus_mv_100m,
    ROUND(COALESCE(cdp.duration,0), 4)                                   AS cd_aaplus_duration
FROM nav_deviation nd
LEFT JOIN govt_bond     g   ON g.port_id   = nd.port_id
LEFT JOIN credit_aaa    ca  ON ca.port_id  = nd.port_id
LEFT JOIN cd_aaa        cda ON cda.port_id = nd.port_id
LEFT JOIN credit_aaplus cap ON cap.port_id = nd.port_id
LEFT JOIN cd_aaplus     cdp ON cdp.port_id = nd.port_id
ORDER BY nd.port_id;
