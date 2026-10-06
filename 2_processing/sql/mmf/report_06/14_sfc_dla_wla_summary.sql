-- ============================================================
-- 報表06 / 14_sfc_dla_wla_summary.sql
-- SFC DLA/WLA 合規表（口徑 B）— 寫入「SFC壓力測試」sheet 表格2（獨立表格塊）
-- 對應文檔：SFC UT Code §8.2(n)（DLA≥7.5% / WLA≥15%，雙場景均須滿足）
--
-- 前置：必須先執行 10_sfc_stress.sql（生成 compliance 結果）
--
-- 輸出（5 列，寫入 SFC壓力測試!A13 起；表頭在 R12）：
--   A row_label    組合名稱 + 場景
--   B dla_pct      DLA / NAV %（SFC 下限 7.5%）
--   C dla_status   DLA 合規狀態
--   D wla_pct      WLA / NAV %（SFC 下限 15%）
--   E wla_status   WLA 合規狀態
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
