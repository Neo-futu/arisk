-- ============================================================
-- 報表03 / 02_liquidity_1m.sql
-- 原始：SmartReport/03/02.sql  一個月以內的流動性
-- Sheet：日报-sql导入数据，標籤02.sql@I3，表頭I4，數據I5
--
-- 欄位說明（對照模版表頭）：
--   组合/指标                        = port_name
--   1y内利率债（国债、政金债）金额（亿） = irbond（利率債剩餘期限≤365天，成本億元）
--   现金金额（亿）                   = cash（科目100201銀行活期，億元）
--
-- 原始邏輯：
--   irbond = T_Balance_Bond WHERE ItemTypeIdLevel2 IN ('004001','004006')
--            AND DATEDIFF(day, EvaluateDate, MaturityDate) <= 365
--            → FSI: asset_subtype='BOND_GOVT' AND remaining_days <= 365
--   cash   = T_Balance_BalanceSheet WHERE SubjectCode='100201'
--            → FSI: balance_valuation_sheet WHERE subject_code='100201'
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH cash AS (
    SELECT
        v.port_id,
        p.port_name,
        SUM(CASE WHEN v.subject_code = '100201'
                 THEN COALESCE(v.market_value, 0) ELSE 0 END) / 100000000 AS cash
    FROM fsi.balance_valuation_sheet v
    JOIN fsi.para_portfolio p ON p.port_id = v.port_id
    WHERE p.is_mmf = TRUE
      AND p.is_active = TRUE
      AND v.evaluate_date = '2026-06-25'::DATE
      AND v.subject_code = '100201'
    GROUP BY v.port_id, p.port_name
),

irbond AS (
    -- 政府/利率債 剩餘期限 ≤ 365 天（對應源 004001=国债, 004006=政金债）
    SELECT
        b.port_id,
        SUM(COALESCE(b.cost, 0)) / 100000000 AS irbond   -- 源用 Cost，非 market_value
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE
      AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype = 'BOND_GOVT'
      AND b.remaining_days <= 365
    GROUP BY b.port_id
)

SELECT
    c.port_name,
    ROUND(COALESCE(i.irbond, 0), 4) AS irbond_100m,   -- 1y内利率债（国债、政金债）金额（亿）
    ROUND(COALESCE(c.cash, 0), 4)   AS cash_100m       -- 现金金额（亿）
FROM cash c
LEFT JOIN irbond i ON i.port_id = c.port_id
ORDER BY c.port_name;
