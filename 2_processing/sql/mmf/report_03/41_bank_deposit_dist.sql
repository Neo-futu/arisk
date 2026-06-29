-- ============================================================
-- 報表03 / 41_bank_deposit_dist.sql
-- 原始：SmartReport/03/41.sql  存款+CD 按銀行/期限分佈
-- Sheet：其他监控-sql导入数据，標籤 A25，表頭 A26，數據 A27
--
-- 欄位說明（對應模版表頭）：
--   组合名称     = port_name
--   银行/发行人  = bank_name
--   3月以内（亿）= within_3m
--   3~6月（亿）  = m3_to_6m
--   6月~1年（亿）= m6_to_1y
--   1年以上（亿）= over_1y
--   存款小计（亿）= deposit_subtotal
--   存单小计（亿）= cd_subtotal
--   合计（亿）   = total
--
-- 用途：監控存款/CD 集中在哪些銀行、各期限段分佈是否合理
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH bank_detail AS (
    -- 定期存款
    SELECT
        d.port_id,
        COALESCE(d.bank_id, d.bank_name)    AS bank_id,
        COALESCE(d.bank_name, d.bank_id)    AS bank_name,
        'DEPOSIT'                            AS item_type,
        COALESCE(d.principal, 0)             AS amount,
        d.remaining_days
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND d.maturity_date >= '2026-06-25'::DATE

    UNION ALL

    -- 存款證（CD）
    SELECT
        c.port_id,
        COALESCE(c.issuer_id, c.issuer_name),
        COALESCE(c.issuer_name, c.issuer_id),
        'CD',
        COALESCE(c.principal, COALESCE(c.market_value, 0)),
        c.remaining_days
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND c.maturity_date >= '2026-06-25'::DATE
),

bank_sum AS (
    SELECT
        port_id,
        bank_id,
        MAX(bank_name)                                                                       AS bank_name,
        ROUND(SUM(CASE WHEN remaining_days <= 92                    THEN amount ELSE 0 END) / 100000000, 4) AS within_3m,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 93  AND 184      THEN amount ELSE 0 END) / 100000000, 4) AS m3_to_6m,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 185 AND 365      THEN amount ELSE 0 END) / 100000000, 4) AS m6_to_1y,
        ROUND(SUM(CASE WHEN remaining_days > 365                    THEN amount ELSE 0 END) / 100000000, 4) AS over_1y,
        ROUND(SUM(CASE WHEN item_type = 'DEPOSIT' THEN amount ELSE 0 END) / 100000000, 4)   AS deposit_subtotal,
        ROUND(SUM(CASE WHEN item_type = 'CD'      THEN amount ELSE 0 END) / 100000000, 4)   AS cd_subtotal,
        ROUND(SUM(amount) / 100000000, 4)                                                    AS total
    FROM bank_detail
    GROUP BY port_id, bank_id
)

SELECT
    p.port_name,
    bs.bank_name,
    bs.within_3m,
    bs.m3_to_6m,
    bs.m6_to_1y,
    bs.over_1y,
    bs.deposit_subtotal,
    bs.cd_subtotal,
    bs.total
FROM bank_sum bs
JOIN fsi.para_portfolio p ON p.port_id = bs.port_id
WHERE p.is_active = TRUE
ORDER BY p.port_name, bs.total DESC;
