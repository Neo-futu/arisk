-- ============================================================
-- 報表06 / 12_sfc_bucket_profile.sql  口徑 A：SFC 流動性分層（Indicative Liquidity Profile）
-- 對應文檔：lmt-mmf-test-sfc.docx §1 表格
-- 對應 Sheet：SFC流動性分層（專用展示層）
--
-- ═══ 口徑 A 定義（回答「兩個口徑是什麼」）═══════════════════════
-- 回答監管問題：「如果明天整個組合都要變現，各時間段能變現多少？」
--   每筆持倉的【全額市值】按「完全變現所需天數」歸入 5 檔時間桶：
--     1D / 2-7D / 8-30D / 31-90D / >90D（非累計，雙場景各求和=組合資產 100%）
--   完全變現天數 = ⌈持倉市值 / 日可變現規模⌉
--     日可變現規模 = ADTV × 10% 參與率 × (1 - 場景折扣)（Stressed ADTV 50% haircut）
--   用途：SFC 文檔 §1 Indicative Liquidity Profile 表格（面向投資者/監管披露）
--
-- ═══ 與口徑 B 的區別 ═════════════════════════════════════════
--   口徑 A：全額市值歸桶 → 「組合的流動性結構長什麼樣」（形態披露）
--   口徑 B：ADTV 約束下 1 日/5 日能真實拿到多少錢 → 「能覆蓋多少贖回」（覆蓋能力）
--
-- 輸入：讀 fsi.sfc_liquidity_stress（10_sfc_stress.sql 落庫的明細）
-- 輸出：port_name | scenario | bucket | market_value | pct_of_total（組合內合計=100%）
--       共 port × 2場景 × 5桶 = 20 行
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
bucket_agg AS (
    SELECT
        s.port_id,
        s.scenario,
        s.liquidation_bucket,
        SUM(s.market_value) AS bucket_mv
    FROM fsi.sfc_liquidity_stress s, params
    WHERE s.evaluate_date = params.evaluate_date
      AND s.port_id = ANY(params.port_ids)
    GROUP BY s.port_id, s.scenario, s.liquidation_bucket
),
port_total AS (
    SELECT port_id, scenario, SUM(bucket_mv) AS total_mv
    FROM bucket_agg
    GROUP BY port_id, scenario
),
ports AS (
    SELECT DISTINCT s.port_id, s.scenario
    FROM fsi.sfc_liquidity_stress s, params
    WHERE s.evaluate_date = params.evaluate_date AND s.port_id = ANY(params.port_ids)
),
buckets(dim) AS (
    (VALUES ('1D'), ('2-7D'), ('8-30D'), ('31-90D'), ('GT90D'))
),
grid AS (   -- 組合×場景×5桶 全網格（空桶補 0，保證每場景 5 行）
    SELECT po.port_id, po.scenario, bk.dim AS liquidation_bucket
    FROM ports po CROSS JOIN buckets bk
)
SELECT
    p.port_name,
    CASE g.scenario WHEN 'NORMAL' THEN 'Normal scenario'
                    WHEN 'STRESSED' THEN 'Stressed scenario' END AS scenario_label,
    g.liquidation_bucket,
    ROUND(COALESCE(b.bucket_mv, 0), 2)                  AS market_value,
    ROUND(COALESCE(b.bucket_mv, 0) / NULLIF(t.total_mv, 0) * 100, 4) AS pct_of_total,
    ROUND(t.total_mv, 2)                                AS portfolio_total_mv,
    g.scenario
FROM grid g
LEFT JOIN bucket_agg b ON b.port_id = g.port_id AND b.scenario = g.scenario
                      AND b.liquidation_bucket = g.liquidation_bucket
JOIN port_total t ON t.port_id = g.port_id AND t.scenario = g.scenario
JOIN fsi.para_portfolio p ON p.port_id = g.port_id, params
ORDER BY p.port_name, g.scenario,
         CASE g.liquidation_bucket
             WHEN '1D' THEN 1
             WHEN '2-7D' THEN 2
             WHEN '8-30D' THEN 3
             WHEN '31-90D' THEN 4
             WHEN 'GT90D' THEN 5
         END;
