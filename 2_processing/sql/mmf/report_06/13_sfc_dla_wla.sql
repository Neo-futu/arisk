-- ============================================================
-- 報表06 / 13_sfc_dla_wla.sql  口徑 B：SFC DLA/WLA 流動性覆蓋能力（贖回壓力測試）
-- 對應文檔：SFC UT Code §8.2(n)（DLA≥7.5% / WLA≥15%，雙場景）
-- 對應 Sheet：SFC DLA/WLA合規（專用展示層）
--
-- ═══ 口徑 B 定義（回答「兩個口徑是什麼」）═══════════════════════
-- 回答監管問題：「明天/下週到期的贖回，用 1 日/5 日內真實可變現的錢能覆蓋多少？」
--   realizable_1d = 1 交易日內 ADTV 約束下真實可變現額（受市場深度上限）
--     = MIN(市值, ADTV×10%×(1-折扣)) + 現金 + 隔夜 + 1 日到期
--   realizable_5d = 5 交易日內真實可變現額
--     = MIN(市值, ADTV×10%×(1-折扣)×5) + 5 日內到期 + 可早破存款(Normal)
--   DLA% = Σ realizable_1d / NAV × 100，SFC 须 ≥ 7.5%
--   WLA% = Σ realizable_5d / NAV × 100，SFC 须 ≥ 15%
--   Stressed：存款零早破（不計入 5 日可變現）、ADTV 50% haircut
--   用途：贖回壓力測試 / LMT 觸發判斷（流動性管理工具是否需啟動）
--
-- ═══ 與口徑 A 的區別 ═════════════════════════════════════════
--   口徑 A：全額市值按完全變現天數歸桶 → 結構形態（5 桔 sum=100%）
--   口徑 B：ADTV 約束下實際可拿到多少錢 → 覆蓋能力（DLA/WLA 合規）
--   關鍵差異：口徑 A 的「1D 桔」可能含一筆市值 100 億但 ADTV 只能日賣 1 億的債券
--            口徑 A 把 100 億都算進 GT90D（因 ⌈100/1⌉=100 天→ 不在 1D）
--            口徑 B 則只認 1 日內能拿到的 1 億（受 ADTV 上限）
--
-- 輸入：讀 fsi.sfc_liquidity_stress（10_sfc_stress.sql 落庫的明細，含 realizable_amount/realizable_5d_amount）
-- 輸出（組合×場景×資產類別貢獻拆分 + 合規匯總行）：
--   port_name | scenario | asset_category | market_value | dla_contribution | dla_share_pct | wla_contribution | wla_share_pct
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
asset_contrib AS (
    SELECT
        s.port_id,
        s.scenario,
        s.asset_category,
        SUM(s.market_value)          AS market_value,
        SUM(s.realizable_amount)     AS dla_amount,
        SUM(s.realizable_5d_amount)  AS wla_amount
    FROM fsi.sfc_liquidity_stress s, params
    WHERE s.evaluate_date = params.evaluate_date
      AND s.port_id = ANY(params.port_ids)
    GROUP BY s.port_id, s.scenario, s.asset_category
),
port_nav AS (
    SELECT s.port_id, s.scenario, MAX(s.net_asset) AS nav
    FROM fsi.sfc_liquidity_stress s, params
    WHERE s.evaluate_date = params.evaluate_date AND s.port_id = ANY(params.port_ids)
    GROUP BY s.port_id, s.scenario
),
port_total AS (
    SELECT port_id, scenario, SUM(dla_amount) AS dla, SUM(wla_amount) AS wla, SUM(market_value) AS total_mv
    FROM asset_contrib
    GROUP BY port_id, scenario
),
combined AS (
    SELECT
        p.port_name,
        CASE c.scenario WHEN 'NORMAL' THEN 'Normal scenario'
                        WHEN 'STRESSED' THEN 'Stressed scenario' END AS scenario_label,
        c.asset_category,
        ROUND(c.market_value, 2)                          AS market_value,
        ROUND(c.dla_amount, 2)                            AS dla_contribution,
        ROUND(c.dla_amount / NULLIF(pt.dla, 0) * 100, 4) AS dla_share_pct,
        ROUND(c.wla_amount, 2)                            AS wla_contribution,
        ROUND(c.wla_amount / NULLIF(pt.wla, 0) * 100, 4) AS wla_share_pct,
        c.scenario,
        CASE WHEN c.asset_category = '合規匯總' THEN 99
             WHEN c.asset_category = 'CASH' THEN 1
             WHEN c.asset_category = 'REV_REPO' THEN 2
             WHEN c.asset_category = 'DEPOSIT' THEN 3
             WHEN c.asset_category = 'CD' THEN 4
             WHEN c.asset_category = 'BOND_GOVT' THEN 5
             WHEN c.asset_category = 'BOND_FLOAT' THEN 6
             WHEN c.asset_category = 'BOND_CORP' THEN 7
             ELSE 50 END AS sort_key
    FROM asset_contrib c
    JOIN port_total pt ON pt.port_id = c.port_id AND pt.scenario = c.scenario
    JOIN port_nav pn   ON pn.port_id = c.port_id AND pn.scenario = c.scenario
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id, params
    UNION ALL
    SELECT
        p.port_name,
        CASE pt.scenario WHEN 'NORMAL' THEN 'Normal scenario'
                         WHEN 'STRESSED' THEN 'Stressed scenario' END,
        '合規匯總',
        ROUND(pt.total_mv, 2),
        ROUND(pt.dla, 2),
        ROUND(pt.dla / NULLIF(pn.nav, 0) * 100, 4),
        ROUND(pt.wla, 2),
        ROUND(pt.wla / NULLIF(pn.nav, 0) * 100, 4),
        pt.scenario,
        99
    FROM port_total pt
    JOIN port_nav pn ON pn.port_id = pt.port_id AND pn.scenario = pt.scenario
    JOIN fsi.para_portfolio p ON p.port_id = pt.port_id, params
)
SELECT port_name, scenario_label, asset_category, market_value,
       dla_contribution, dla_share_pct, wla_contribution, wla_share_pct, scenario
FROM combined
ORDER BY port_name,
         CASE scenario WHEN 'NORMAL' THEN 1 ELSE 2 END,
         sort_key;
