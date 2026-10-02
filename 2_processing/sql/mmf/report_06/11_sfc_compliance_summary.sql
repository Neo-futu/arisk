-- ============================================================
-- 報表06 / 11_sfc_compliance_summary.sql
-- SFC 流動性合規匯總（從 fsi.sfc_liquidity_compliance 讀取）
-- 對應文檔：lmt-mmf-test-sfc.docx §1（Indicative Liquidity Profile）
-- 對應 Sheet：SFC壓力測試（展示層數據源）
--
-- 前置：必須先執行 10_sfc_stress.sql（生成 compliance 結果）
--
-- 輸出（11 列，對應 SFC壓力測試 sheet 第 5 行表頭 A~K）：
--   A row_label          組合名稱 + 場景（如「博匯港元貨幣市場基金I Normal scenario」）
--   B bucket_1d_pct      1D 桶佔 NAV %
--   C bucket_2_7d_pct    2-7D 桶佔 NAV %
--   D bucket_8_30d_pct   8-30D 桶佔 NAV %
--   E bucket_31_90d_pct  31-90D 桶佔 NAV %
--   F bucket_gt90d_pct   >90D 桶佔 NAV %
--   G total_pct          五桶合計（=coverage_pct，資產端分層）
--   H dla_pct            DLA% (≥7.5%)
--   I dla_status         DLA 合規狀態
--   J wla_pct            WLA% (≥15%)
--   K wla_status         WLA 合規狀態
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
)
SELECT
    p.port_name || ' ' ||
    CASE c.scenario WHEN 'NORMAL' THEN 'Normal scenario'
                    WHEN 'STRESSED' THEN 'Stressed scenario' END AS row_label,
    c.bucket_1d_pct,
    c.bucket_2_7d_pct,
    c.bucket_8_30d_pct,
    c.bucket_31_90d_pct,
    c.bucket_gt90d_pct,
    c.total_pct,
    c.dla_pct,
    c.dla_status,
    c.wla_pct,
    c.wla_status
FROM fsi.sfc_liquidity_compliance c
JOIN fsi.para_portfolio p ON p.port_id = c.port_id, params
WHERE c.evaluate_date = params.evaluate_date
  AND c.port_id = ANY(params.port_ids)
ORDER BY p.port_name,
         CASE c.scenario WHEN 'NORMAL' THEN 1 ELSE 2 END;
