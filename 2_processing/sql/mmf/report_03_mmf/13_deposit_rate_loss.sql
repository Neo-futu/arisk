-- ============================================================
-- 報表03 / 13_deposit_rate_loss.sql
-- 原始：SmartReport/03/13.sql  利息風險敞口（最大利差損金額）
-- Sheet：日报-sql导入数据，標籤13.sql@A78，表頭A79，數據A80
--
-- 欄位說明（對照模版表頭 A79-C79）：
--   组合名称          = port_name
--   组合代码          = port_id
--   最大利差损金额（元）= rate_loss（元）
--
-- 計算公式（對應源 SQL）：
--   rate_loss = SUM( 已持有天數/360 × (存款利率 - 0.35%) × 本金 )
--
-- 含義：有罰息存款若今日提前支取，相較最低基準利率(0.35%)已積累的利差損失
--       = 「鎖定成本」—— 反映提前贖回的隱性代價
--
-- 篩選：is_penalty_on_early_redeem=TRUE（僅計算有罰息的定期存款）
-- 注：源 SQL 中 InterestRate 為百分比（如4.15），除以100後與FSI一致
--     FSI 存儲為小數（0.0415），0.35% 對應 0.0035
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

SELECT
    p.port_name,
    p.port_id,
    ROUND(
        SUM(
            (('2026-06-25'::DATE - d.value_date)::NUMERIC / 360.0)   -- 已持有天數/360
            * (d.interest_rate - 0.0035)                              -- 利率差（存款利率-0.35%）
            * d.principal                                              -- 本金
        ),
    2) AS rate_loss                                                    -- 最大利差损金额（元）
FROM fsi.balance_deposit d
JOIN fsi.para_portfolio p ON p.port_id = d.port_id
WHERE p.is_mmf = TRUE
  AND p.is_active = TRUE
  AND d.evaluate_date = '2026-06-25'::DATE
  AND d.is_penalty_on_early_redeem = TRUE           -- 僅有罰息存款
  AND d.value_date < '2026-06-25'::DATE             -- 已持有（value_date < 今日）
GROUP BY p.port_name, p.port_id
ORDER BY p.port_name;
