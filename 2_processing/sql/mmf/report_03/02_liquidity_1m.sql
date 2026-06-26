WITH -- ============================================================
-- 報表03 / 02_liquidity_1m.sql
-- 原始：SmartReport/03/02.sql  一個月以內的流動性
-- 功能：現金 + 一年期以內利率債合計
-- 參數：params.evaluate_date DATE
-- ============================================================

cash AS (
    SELECT
        v.port_id,
        p.port_name,
        -- 科目 100201 = 銀行存款活期（現金）
        SUM(CASE WHEN v.subject_code = '100201' THEN COALESCE(v.market_value, 0) ELSE 0 END) / 100000000 AS cash
    FROM fsi.balance_valuation_sheet v
    JOIN fsi.para_portfolio p ON p.port_id = v.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND v.evaluate_date = params.evaluate_date
      AND v.subject_code = '100201'
    GROUP BY v.port_id, p.port_name
),

govt_bond_1y AS (
    -- 政府/利率債：剩餘期限 ≤ 365 天（SFC 每週流動性可計入）
    SELECT
        b.port_id,
        SUM(COALESCE(b.market_value, 0)) / 100000000 AS govt_bond_1y
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = params.evaluate_date
      AND b.asset_subtype = 'BOND_GOVT'
      AND b.remaining_days <= 365
    GROUP BY b.port_id
)

SELECT
    c.port_name,
    ROUND(COALESCE(g.govt_bond_1y, 0), 4) AS govt_bond_1y_100m,   -- 一年期以內利率債（億）
    ROUND(COALESCE(c.cash, 0), 4)          AS cash_100m            -- 現金活期（億）
FROM cash c
LEFT JOIN govt_bond_1y g ON g.port_id = c.port_id
ORDER BY c.port_name;
