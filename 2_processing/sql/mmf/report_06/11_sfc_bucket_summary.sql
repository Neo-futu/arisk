-- ============================================================
-- 報表06 / 11_sfc_bucket_summary.sql
-- SFC 流動性分層表（口徑 A）— 寫入「SFC壓力測試」sheet 表格1
-- 對應文檔：lmt-mmf-test-sfc.docx §1（Indicative Liquidity Profile）
--   "Percentages are presented in non-cumulative time buckets
--    and sum to 100% under each scenario."
--
-- 口徑：每檔市值佔【組合資產合計】%（歸一化，每場景五檔求和=100%）
-- 前置：必須先執行 10_sfc_stress.sql（生成 sfc_liquidity_stress 明細）
--
-- 輸出（7 列，寫入 SFC壓力測試!A6 起；表頭在 R5）：
--   A row_label       組合名稱 + 場景
--   B~F 五檔 %        1 Day / 2-7 Days / 8-30 Days / 31-90 Days / > 90 Days
--   G total_pct       五檔合計（=100%）
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
        SUM(CASE WHEN s.liquidation_bucket = '1D'     THEN s.market_value ELSE 0 END) AS b1,
        SUM(CASE WHEN s.liquidation_bucket = '2-7D'    THEN s.market_value ELSE 0 END) AS b2,
        SUM(CASE WHEN s.liquidation_bucket = '8-30D'  THEN s.market_value ELSE 0 END) AS b3,
        SUM(CASE WHEN s.liquidation_bucket = '31-90D' THEN s.market_value ELSE 0 END) AS b4,
        SUM(CASE WHEN s.liquidation_bucket = 'GT90D'  THEN s.market_value ELSE 0 END) AS b5,
        SUM(s.market_value) AS total_mv
    FROM fsi.sfc_liquidity_stress s, params
    WHERE s.evaluate_date = params.evaluate_date
      AND s.port_id = ANY(params.port_ids)
    GROUP BY s.port_id, s.scenario
)
SELECT
    p.port_name || ' ' ||
    CASE b.scenario WHEN 'NORMAL' THEN 'Normal scenario'
                    WHEN 'STRESSED' THEN 'Stressed scenario' END AS row_label,
    ROUND(b.b1 / NULLIF(b.total_mv,0) * 100, 6) AS bucket_1d_pct,
    ROUND(b.b2 / NULLIF(b.total_mv,0) * 100, 6) AS bucket_2_7d_pct,
    ROUND(b.b3 / NULLIF(b.total_mv,0) * 100, 6) AS bucket_8_30d_pct,
    ROUND(b.b4 / NULLIF(b.total_mv,0) * 100, 6) AS bucket_31_90d_pct,
    ROUND(b.b5 / NULLIF(b.total_mv,0) * 100, 6) AS bucket_gt90d_pct,
    100.000000                                  AS total_pct
FROM bucket_agg b
JOIN fsi.para_portfolio p ON p.port_id = b.port_id, params
ORDER BY p.port_name,
         CASE b.scenario WHEN 'NORMAL' THEN 1 ELSE 2 END;
