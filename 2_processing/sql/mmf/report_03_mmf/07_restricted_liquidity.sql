-- ============================================================
-- 報表03 / 07_restricted_liquidity.sql
-- 原始：SmartReport/03/07.sql  普通渠道存量规模（流通受限资产）
-- Sheet：日报-sql导入数据，標籤07.sql@L3，表頭L4，數據L5
--
-- 欄位說明（對照模版表頭）：
--   第一列（無標題）= port_name
--   流通受限资产（10日以上存款、逆回购、abs）(亿） = restricted_assets_100m
--
-- 流通受限資產定義（三類合計）：
--   1. 提前支取有罰息的存款（is_penalty_on_early_redeem=TRUE）且剩餘期限 > 10個工作日
--   2. 逆回購（融出，REV_REPO）到期日 > T+10個工作日
--   3. ABS/流動性較差的特殊債券（asset_subtype='BOND_ABS'）
--
-- 注：源 SQL 用 DeltaTransactDate 計算10個交易日
--     FSI 簡化為 +14 日曆日（約等於10個交易日），生產環境可接交易日曆
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

SELECT
    p.port_name,
    ROUND(SUM(mv) / 100000000, 4) AS restricted_assets_100m   -- 流通受限资产（亿）
FROM (
    -- 1. 提前支取有罰息的存款（到期日超過10個工作日）
    SELECT d.port_id,
           SUM(COALESCE(d.principal, 0)) AS mv
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p2 ON p2.port_id = d.port_id
    WHERE p2.is_mmf = TRUE
      AND p2.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND d.is_penalty_on_early_redeem = TRUE            -- 有罰息
      AND d.maturity_date > '2026-06-25'::DATE + 14     -- > T+14日（≈10個交易日）
    GROUP BY d.port_id

    UNION ALL

    -- 2. 逆回購（融出）到期日超過10個工作日
    SELECT r.port_id,
           SUM(COALESCE(r.principal, 0)) AS mv
    FROM fsi.balance_repo r
    JOIN fsi.para_portfolio p2 ON p2.port_id = r.port_id
    WHERE p2.is_mmf = TRUE
      AND p2.is_active = TRUE
      AND r.evaluate_date = '2026-06-25'::DATE
      AND r.repo_type = 'REV_REPO'
      AND COALESCE(r.actual_maturity_date, r.maturity_date) > '2026-06-25'::DATE
      AND COALESCE(r.actual_maturity_date, r.maturity_date) > '2026-06-25'::DATE + 14
    GROUP BY r.port_id

    UNION ALL

    -- 3. ABS 類債券（流動性較差）
    SELECT b.port_id,
           SUM(COALESCE(b.cost, 0)) AS mv
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p2 ON p2.port_id = b.port_id
    WHERE p2.is_mmf = TRUE
      AND p2.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype = 'BOND_ABS'
    GROUP BY b.port_id
) t
JOIN fsi.para_portfolio p ON p.port_id = t.port_id
GROUP BY p.port_name
ORDER BY p.port_name;
