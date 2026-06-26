-- ============================================================
-- 報表06 / 04_deposit_early_redeem.sql
-- 原始：SmartReport/06/04.sql  可提前支取協議存款到期日期分佈
-- 功能：僅統計可提前支取（is_penalty_on_early_redeem=FALSE）存款
--        按銀行/到期天數展示 D+1 至 D+7+
-- 對應 Sheet：可提支存款到期原始
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================
data AS (
    SELECT
        d.port_id,
        COALESCE(d.bank_id, d.bank_name) AS bank_id,
        COALESCE(d.bank_name, d.bank_id) AS bank_name,
        d.remaining_days,
        COALESCE(d.principal, 0) * 100   AS principal   -- ×100 對齊原始 SQL
    FROM fsi.balance_deposit d, params
    WHERE d.port_id = ANY(params.port_ids)
      AND d.evaluate_date = params.evaluate_date
      AND (d.is_penalty_on_early_redeem = FALSE
           OR d.is_penalty_on_early_redeem IS NULL)    -- 可提前支取
      AND d.maturity_date >= params.evaluate_date::DATE
),

pivot AS (
    SELECT
        port_id,
        bank_id,
        MAX(bank_name) AS bank_name,
        ROUND(SUM(CASE WHEN remaining_days = 1            THEN principal ELSE 0 END) / 100000000, 4) AS d1,
        ROUND(SUM(CASE WHEN remaining_days = 2            THEN principal ELSE 0 END) / 100000000, 4) AS d2,
        ROUND(SUM(CASE WHEN remaining_days = 3            THEN principal ELSE 0 END) / 100000000, 4) AS d3,
        ROUND(SUM(CASE WHEN remaining_days = 4            THEN principal ELSE 0 END) / 100000000, 4) AS d4,
        ROUND(SUM(CASE WHEN remaining_days = 5            THEN principal ELSE 0 END) / 100000000, 4) AS d5,
        ROUND(SUM(CASE WHEN remaining_days = 6            THEN principal ELSE 0 END) / 100000000, 4) AS d6,
        ROUND(SUM(CASE WHEN remaining_days = 7            THEN principal ELSE 0 END) / 100000000, 4) AS d7,
        ROUND(SUM(CASE WHEN remaining_days > 7            THEN principal ELSE 0 END) / 100000000, 4) AS d7plus
    FROM data
    GROUP BY port_id, bank_id
)

-- 明細行
SELECT p.port_id, pv.bank_id, pv.bank_name,
       pv.d1, pv.d2, pv.d3, pv.d4, pv.d5, pv.d6, pv.d7, pv.d7plus,
       ROUND(pv.d1+pv.d2+pv.d3+pv.d4+pv.d5+pv.d6+pv.d7+pv.d7plus, 4) AS total
FROM pivot pv
JOIN fsi.para_portfolio p ON p.port_id = pv.port_id

UNION ALL

-- 合計行
SELECT p.port_id, 'TOTAL', '合計',
       ROUND(SUM(pv.d1),4), ROUND(SUM(pv.d2),4), ROUND(SUM(pv.d3),4), ROUND(SUM(pv.d4),4),
       ROUND(SUM(pv.d5),4), ROUND(SUM(pv.d6),4), ROUND(SUM(pv.d7),4), ROUND(SUM(pv.d7plus),4),
       ROUND(SUM(pv.d1+pv.d2+pv.d3+pv.d4+pv.d5+pv.d6+pv.d7+pv.d7plus),4)
FROM pivot pv
JOIN fsi.para_portfolio p ON p.port_id = pv.port_id
GROUP BY p.port_id

ORDER BY port_id, CASE bank_id WHEN 'TOTAL' THEN 'ZZZZ' ELSE bank_id END;
