-- ============================================================
-- 報表06 / 02_bank_cd_summary.sql
-- 原始：SmartReport/06/02.sql  銀行存單分類匯總（存款+CD 按銀行）
-- 功能：按銀行合計存款+CD，按持倉金額排名，附合計行
-- 參數：params.port_ids TEXT[], params.evaluate_date DATE
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE                      AS evaluate_date,
        ARRAY['BHMMF001', 'BHMMF002']::TEXT[]   AS port_ids
),
-- ============================================================
deposit AS (
    SELECT d.port_id,
           COALESCE(d.bank_id, d.bank_name)   AS bank_id,
           COALESCE(d.bank_name, d.bank_id)   AS bank_name,
           SUM(COALESCE(d.principal, 0)) * 100 AS cost  -- 原始×100 對齊原始 SQL
    FROM fsi.balance_deposit d, params
    WHERE d.port_id = ANY(params.port_ids) AND d.evaluate_date = params.evaluate_date
    GROUP BY d.port_id, d.bank_id, d.bank_name
),

cd AS (
    SELECT c.port_id,
           COALESCE(c.issuer_id, c.issuer_name) AS bank_id,
           COALESCE(c.issuer_name, c.issuer_id) AS bank_name,
           SUM(COALESCE(c.market_value, 0)) * 100 AS cost
    FROM fsi.balance_cd c, params
    WHERE c.port_id = ANY(params.port_ids) AND c.evaluate_date = params.evaluate_date
    GROUP BY c.port_id, c.issuer_id, c.issuer_name
),

total AS (
    SELECT t.port_id, t.bank_id, SUM(t.cost) AS cost
    FROM (
        SELECT port_id, bank_id, cost FROM deposit
        UNION ALL
        SELECT port_id, bank_id, cost FROM cd
    ) t
    GROUP BY t.port_id, t.bank_id
),

data AS (
    SELECT
        tt.port_id,
        tt.bank_id,
        COALESCE(bn.bank_name, tt.bank_id)     AS bank_name,
        COALESCE(d.cost, 0)                     AS deposit_cost,
        COALESCE(c.cost, 0)                     AS cd_cost,
        tt.cost                                 AS total_cost,
        ROW_NUMBER() OVER (PARTITION BY tt.port_id ORDER BY tt.cost DESC) AS rk
    FROM total tt
    LEFT JOIN deposit d  ON d.port_id = tt.port_id AND d.bank_id = tt.bank_id
    LEFT JOIN cd      c  ON c.port_id = tt.port_id AND c.bank_id = tt.bank_id
    LEFT JOIN (
        -- 取每個機構最常見名稱
        SELECT DISTINCT ON (bank_id) bank_id, bank_name FROM (
            SELECT issuer_id AS bank_id, issuer_name AS bank_name FROM fsi.balance_cd
            WHERE evaluate_date = params.evaluate_date
            UNION
            SELECT bank_id, bank_name FROM fsi.balance_deposit
            WHERE evaluate_date = params.evaluate_date
        ) bn_raw
    ) bn ON bn.bank_id = tt.bank_id
)

-- 明細行
SELECT
    port_id,
    bank_id,
    bank_name,
    ROUND(deposit_cost / 100000000, 4) AS deposit_100m,
    ROUND(cd_cost      / 100000000, 4) AS cd_100m,
    ROUND(total_cost   / 100000000, 4) AS total_100m,
    rk
FROM data

UNION ALL

-- 合計行（每個 port 一行）
SELECT
    port_id,
    'TOTAL' AS bank_id,
    '合計'  AS bank_name,
    ROUND(SUM(deposit_cost) / 100000000, 4),
    ROUND(SUM(cd_cost)      / 100000000, 4),
    ROUND(SUM(total_cost)   / 100000000, 4),
    NULL    AS rk
FROM data
GROUP BY port_id

ORDER BY port_id, rk;
