-- ============================================================
-- 報表06 / 05_deviation_analysis.sql  基金 VNAV 定價 · 成本/影子價值/久期拆解
-- 對應 Sheet：基金原始成本影子定价偏离度原始
--
-- ═══ 業務背景（VNAV 口徑）══════════════════════════════════════
-- 香港 SFC 貨幣市場基金採用 VNAV（Variable Net Asset Value）估值，
-- 即市值法估值，無「攤余成本法 vs 影子定價」偏離度概念（與境內貨幣基金不同）。
-- 本報表保留「成本 vs 影子價值（市值）」拆解，用於：
--   · 監控持倉市值相對成本的浮動（VNAV 下的成本基準對比）
--   · 各品種久期，支撐利率風險分析
--   · 不再計算「偏離度 BP」（VNAV 無此指標）
--
-- 輸出列：
--   A port_name             組合名稱
--   B port_id              組合代碼
--   C govt_bond_cost_100m  利率債成本（億元）
--   D govt_bond_mv_100m    利率債影子價值/市值（億元）
--   E govt_bond_duration   利率債平均久期（年）
--   F credit_aaa_cost_100m / mv / duration      AAA 信用債
--   I cd_aaa_cost_100m / mv / duration          AAA 存款證
--   L credit_aaplus_cost_100m / mv / duration   AA+ 信用債
--   O cd_aaplus_cost_100m / mv / duration      AA+ 存款證
--
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),

-- 政府/利率債（成本/市值/久期加權）
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

-- 所有持倉加權平均久期（整體利率敏感度）
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
    p.port_name,
    n.port_id,
    -- 利率債（VNAV 下成本 vs 市值拆解，無偏離度）
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
FROM fsi.balance_portfolio_nav n
JOIN fsi.para_portfolio p ON p.port_id = n.port_id, params
LEFT JOIN govt_bond     g   ON g.port_id   = n.port_id
LEFT JOIN credit_aaa    ca  ON ca.port_id  = n.port_id
LEFT JOIN cd_aaa        cda ON cda.port_id = n.port_id
LEFT JOIN credit_aaplus cap ON cap.port_id = n.port_id
LEFT JOIN cd_aaplus     cdp ON cdp.port_id = n.port_id
WHERE n.port_id = ANY(params.port_ids)
  AND n.evaluate_date = params.evaluate_date
  AND n.class_id IS NULL
ORDER BY n.port_id;
