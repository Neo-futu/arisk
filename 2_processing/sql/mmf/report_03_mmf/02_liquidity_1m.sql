-- ============================================================
-- 報表03 / 02_liquidity_1m.sql
-- 1年以內到期的流動性資產（HK MMF 口徑）
-- Sheet：日报-sql导入数据，標籤02.sql@I3，表頭I4，數據I5
--
-- 業務含義（對應 SFC UT Code §8.2(n) 流動性監控）：
--   cash_100m   = 現金及活期存款（最高流動性，計入 DLA 及 WLA）
--   gov1y_100m  = 1年以內到期的政府/公共債券（按市值）
--                 → 符合 SFC WLA 定義（T+5以內部分可計入 WLA）
--
-- 數據說明：
--   現金：來自 balance_valuation_sheet（科目 100201 銀行活期存款）
--   政府/公共債：balance_bond WHERE asset_subtype='BOND_GOVT'
--               AND remaining_days <= 365 天（對應1年內到期）
--
-- 修正說明（vs 原版）：
--   [原] irbond 用 cost（成本），與 06_asset_portfolio 市值口徑不一致
--   [新] 改用 market_value，統一採用公允價值，與日報其他表格一致
--   [新] 欄位名稱改為 HK 術語：irbond → gov1y（政府/公共債1年內）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH

-- 現金：銀行活期存款（科目 100201）
cash AS (
    SELECT v.port_id,
           p.port_name,
           SUM(COALESCE(v.market_value, 0)) / 100000000.0 AS cash
    FROM fsi.balance_valuation_sheet v
    JOIN fsi.para_portfolio p ON p.port_id = v.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND v.evaluate_date = '2026-06-25'::DATE
      AND v.subject_code  = '100201'
    GROUP BY v.port_id, p.port_name
),

-- 1年內到期的政府/公共債券（市值，符合SFC WLA/DLA計算口徑）
gov1y AS (
    SELECT b.port_id,
           -- 使用市值（market_value）與日報其他表格統一口徑
           SUM(COALESCE(b.market_value, 0)) / 100000000.0 AS gov1y
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date   = '2026-06-25'::DATE
      AND b.asset_subtype   = 'BOND_GOVT'
      AND b.remaining_days  <= 365
      AND b.quantity > 0
    GROUP BY b.port_id
)

SELECT
    c.port_name,
    -- 政府/公共債券1年內到期市值（亿元）— 流動性分析基礎數據
    ROUND(COALESCE(g.gov1y, 0), 4) AS gov1y_100m,
    -- 現金金額（亿元）— DLA 的核心組成
    ROUND(COALESCE(c.cash,  0), 4) AS cash_100m
FROM cash c
LEFT JOIN gov1y g ON g.port_id = c.port_id
ORDER BY c.port_name;
