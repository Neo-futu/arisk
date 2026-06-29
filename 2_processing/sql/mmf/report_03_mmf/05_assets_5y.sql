-- ============================================================
-- 報表03 / 05_assets_5y.sql
-- 原始：SmartReport/03/05.sql  5個交易日資產
-- Sheet：日报-sql导入数据，標籤05.sql@I23，表頭I24-I25，數據I26
--
-- 欄位說明（對照模版表頭 I24-O25）：
--   组合              = port_name
--   汇总（亿）        = total（五類資產合計）
--   利率债            = interest_rate_bond（ALL利率債，無到期限制，隨時可變現）
--   债券（非利率）    = credit_bond（T+5內到期的信用債）
--   存单              = cd（T+5內到期的CD）
--   存款              = deposit（T+5內到期的存款，用本金）
--   逆回购            = rev_repo（T+5內到期的逆回購融出）
--
-- 關鍵差異：利率债无到期日过滤（高流动性，随时可出售）
--           其他四类仅计T+5个交易日内到期的
-- T+5交易日 ≈ +7日历日（简化，生产替换为交易日历）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH cutoff AS (
    -- T+5 交易日（簡化：+7日曆日，生產環境替換為交易日曆）
    SELECT '2026-06-25'::DATE + 7 AS t5_date
),

-- 利率債：ALL（無到期日限制，高流動性）
interest_rate_bond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost, 0)) / 100000000 AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype = 'BOND_GOVT'         -- 利率/政府債（對應 004001/004006）
    GROUP BY b.port_id
),

-- 信用債（非利率）：T+5內到期
credit_bond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost, 0)) / 100000000 AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id, cutoff
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype != 'BOND_GOVT'
      AND b.maturity_date > '2026-06-25'::DATE
      AND b.maturity_date <= cutoff.t5_date
    GROUP BY b.port_id
),

-- 存單：T+5內到期
cd AS (
    SELECT c.port_id,
           SUM(COALESCE(c.cost, 0)) / 100000000 AS mv
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id, cutoff
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND c.maturity_date > '2026-06-25'::DATE
      AND c.maturity_date <= cutoff.t5_date
    GROUP BY c.port_id
),

-- 存款：T+5內到期（用本金 Principal）
deposit AS (
    SELECT d.port_id,
           SUM(COALESCE(d.principal, 0)) / 100000000 AS mv
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id, cutoff
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND d.maturity_date > '2026-06-25'::DATE
      AND d.maturity_date <= cutoff.t5_date
    GROUP BY d.port_id
),

-- 逆回購：T+5內到期（融出，REV_REPO，用 principal）
rev_repo AS (
    SELECT r.port_id,
           SUM(COALESCE(r.principal, 0)) / 100000000 AS mv
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p ON p.port_id = r.port_id, cutoff
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) > '2026-06-25'::DATE
      AND COALESCE(r.actual_maturity_date, r.maturity_date) <= cutoff.t5_date
    GROUP BY r.port_id
)

SELECT
    p.port_name,
    ROUND(COALESCE(i.mv,0)+COALESCE(c.mv,0)+COALESCE(cd.mv,0)+
          COALESCE(d.mv,0)+COALESCE(r.mv,0), 4)  AS total,               -- 汇总（亿）
    ROUND(COALESCE(i.mv,   0), 4)                 AS interest_rate_bond,  -- 利率债
    ROUND(COALESCE(c.mv,   0), 4)                 AS credit_bond,         -- 债券（非利率）
    ROUND(COALESCE(cd.mv,  0), 4)                 AS cd,                  -- 存单
    ROUND(COALESCE(d.mv,   0), 4)                 AS deposit,             -- 存款
    ROUND(COALESCE(r.mv,   0), 4)                 AS rev_repo             -- 逆回购
FROM fsi.para_portfolio p
LEFT JOIN interest_rate_bond i  ON i.port_id  = p.port_id
LEFT JOIN credit_bond        c  ON c.port_id  = p.port_id
LEFT JOIN cd                 cd ON cd.port_id = p.port_id
LEFT JOIN deposit            d  ON d.port_id  = p.port_id
LEFT JOIN rev_repo           r  ON r.port_id  = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
