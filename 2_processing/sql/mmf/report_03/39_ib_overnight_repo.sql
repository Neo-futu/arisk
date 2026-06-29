-- ============================================================
-- 報表03 / 39_ib_overnight_repo.sql
-- 原始：SmartReport/03/39.sql  非直連銀行間逆回購
-- Sheet：其他监控-sql导入数据，標籤39.sql@A14，表頭A15，數據A16
--
-- 欄位說明（對照模版表頭 A15-F15）：
--   组合名          = port_name
--   日期            = evaluate_date
--   到期日          = actual_maturity_date
--   交易对手名      = counterparty_name
--   非直连银行间逆回购金额（元） = principal
--   非直连银行间逆回购占比（%）  = ratio_to_nav
--
-- 「非直连」定義（中國語境）：
--   銀行間市場逆回購中，交易對手為城商行/農商行等無直連資格的機構
--   源 SQL：MarketId='005001' AND AssetLiabilityFlag='A'
--          AND CounterpartyName含"銀行" AND 排除主要大行/機構
--
-- FSI/HK 語境：
--   等效為「非一級交易商/非認可機構」的逆回購敞口
--   可通過 para_counterparty 表或 market_id 標識
--   測試數據：以 market_id 含 'IB'（銀行間）的逆回購為示例
--
-- 生產環境：在 para_counterparty 維護「非直連」標記（如 institution_type='NON_DIRECT'）
--            並替換 WHERE 條件
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

SELECT
    p.port_name,
    r.evaluate_date,
    COALESCE(r.actual_maturity_date, r.maturity_date)  AS actual_maturity_date,
    r.counterparty_name,
    ROUND(SUM(r.principal), 2)                         AS principal,     -- 非直連逆回購金額（元）
    ROUND(SUM(r.principal) / NULLIF(n.net_asset, 0) * 100, 6) AS ratio_to_nav -- 佔NAV比（%）
FROM fsi.balance_repo r
JOIN fsi.para_portfolio p ON p.port_id = r.port_id
JOIN fsi.balance_portfolio_nav n ON n.port_id = r.port_id
    AND n.evaluate_date = r.evaluate_date AND n.class_id IS NULL
WHERE p.is_mmf = TRUE
  AND p.is_active = TRUE
  AND r.evaluate_date   = '2026-06-25'::DATE
  AND r.repo_type       = 'REV_REPO'            -- 逆回購融出（源：AssetLiabilityFlag='A'）
  -- 非直連識別：
  -- 生產環境：AND r.counterparty_id IN (
  --               SELECT institution_id FROM fsi.para_counterparty
  --               WHERE institution_type = 'NON_DIRECT_BANK')
  -- 測試數據：取全部逆回購作示例（無分類數據時）
  AND r.counterparty_name IS NOT NULL
GROUP BY
    p.port_name,
    r.evaluate_date,
    COALESCE(r.actual_maturity_date, r.maturity_date),
    r.counterparty_name,
    n.net_asset
ORDER BY
    p.port_name,
    COALESCE(r.actual_maturity_date, r.maturity_date),
    r.counterparty_name,
    SUM(r.principal) DESC;
