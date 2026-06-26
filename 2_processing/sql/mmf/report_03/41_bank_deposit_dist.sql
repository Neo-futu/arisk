WITH -- ============================================================
-- 報表03 / 41_bank_deposit_dist.sql
-- 原始：SmartReport/03/41.sql  存款按銀行/期限分佈
-- 功能：存款+CD 按銀行分組，按期限段（3月/6月/1年/1年以上）統計
-- 參數：params.evaluate_date DATE
-- ============================================================

bank_detail AS (
    -- 定期存款
    SELECT
        d.port_id,
        COALESCE(d.bank_id, d.bank_name) AS bank_id,
        COALESCE(d.bank_name, d.bank_id) AS bank_name,
        'DEPOSIT'                          AS type,
        COALESCE(d.principal, 0)           AS amount,
        d.remaining_days
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id, params
    WHERE p.is_mmf = TRUE AND d.evaluate_date = params.evaluate_date
      AND d.maturity_date >= params.evaluate_date

    UNION ALL

    -- 存款證（CD）
    SELECT
        c.port_id,
        COALESCE(c.issuer_id, c.issuer_name),
        COALESCE(c.issuer_name, c.issuer_id),
        'CD',
        COALESCE(c.principal, 0),
        c.remaining_days
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id, params
    WHERE p.is_mmf = TRUE AND c.evaluate_date = params.evaluate_date
),

bank_sum AS (
    SELECT
        port_id,
        bank_id,
        MAX(bank_name) AS bank_name,
        ROUND(SUM(amount) / 100000000, 4)                                               AS total_100m,
        ROUND(SUM(CASE WHEN remaining_days <= 92  THEN amount ELSE 0 END) / 100000000, 4) AS m3_100m,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 93 AND 184 THEN amount ELSE 0 END) / 100000000, 4) AS m36_100m,
        ROUND(SUM(CASE WHEN remaining_days BETWEEN 185 AND 365 THEN amount ELSE 0 END) / 100000000, 4) AS m69_100m,
        ROUND(SUM(CASE WHEN remaining_days > 365 THEN amount ELSE 0 END) / 100000000, 4) AS y1plus_100m,
        ROUND(SUM(CASE WHEN type = 'DEPOSIT' THEN amount ELSE 0 END) / 100000000, 4)    AS deposit_100m,
        ROUND(SUM(CASE WHEN type = 'CD'      THEN amount ELSE 0 END) / 100000000, 4)    AS cd_100m
    FROM bank_detail
    GROUP BY port_id, bank_id
)

SELECT
    p.port_name,
    bs.bank_id,
    bs.bank_name,
    bs.m3_100m        AS within_3m,
    bs.m36_100m       AS m3_to_6m,
    bs.m69_100m       AS m6_to_1y,
    bs.y1plus_100m    AS over_1y,
    bs.deposit_100m   AS deposit_subtotal,
    bs.cd_100m        AS cd_subtotal,
    bs.total_100m     AS total
FROM bank_sum bs
JOIN fsi.para_portfolio p ON p.port_id = bs.port_id
WHERE p.is_active = TRUE
ORDER BY p.port_name, bs.total_100m DESC;
