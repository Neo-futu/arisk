-- ============================================================
-- 報表03 / 13_deposit_rate_loss.sql
-- 有罰息存款的提前支取隱性損失（最大利差損金額）
-- Sheet：日报-sql导入数据，標籤13.sql@A78，表頭A79，數據A80
--
-- 業務含義（SFC UT Code §8.2(n) 流動性風險 + 內控指標）：
--   有罰息的定期存款若提前支取，需放棄已積累的超額利息收益。
--   本 SQL 計算「若今日強制提前支取所有有罰息存款」的最大潛在損失，
--   作為流動性壓力下的隱性成本評估，屬內控參考指標（非 SFC 強制計算方式）。
--
-- 計算公式：
--   rate_loss = SUM(
--     已持有天數/365       -- HK 慣例使用 365 天計息（非內地 360 天）
--     × (存款利率 - 基準利率)  -- 若提前支取只能獲得基準利率
--     × 本金
--   )
--   rate_loss > 0：提前支取會損失超額利息收益（不划算）
--   rate_loss < 0：存款利率低於基準利率（罕見，通常不適用）
--
-- 基準利率說明：
--   原版硬編碼 0.35%（人民幣活期利率），不適合 HK MMF。
--   HK 場景下基準利率通常參考：
--     - HKMA 活期結算帳利率（當前約 0.5-1.0%）
--     - 隔夜回購利率（HIBOR ON）
--   本 SQL 以 0.5% 為預設基準，可按月調整（參考 params 表）。
--
-- 計息慣例修正（vs 原版）：
--   [原] 除以 360（人民幣/美元債券惯例）
--   [新] 除以 365（港元 / HK 銀行業慣例，Act/365）
--
-- 欄位說明（3列）：
--   port_name   組合名稱
--   port_id     組合代碼
--   rate_loss   最大利差損金額（元）
--
-- ★ 修改 evaluate_date 可獨立運行
-- ★ BASE_RATE 為基準利率（小數，如 0.005=0.5%），按月更新
-- ============================================================

WITH params AS (
    SELECT
        '2026-06-25'::DATE  AS eval_date,
        0.005               AS base_rate   -- 基準利率 0.5%（HK HKMA 活期參考利率）
                                           -- 可按月更新為當月 HIBOR ON 或 HKMA 結算利率
)

SELECT
    p.port_name,
    p.port_id,
    ROUND(
        SUM(
            -- 已持有天數 / 365（HK Act/365 計息慣例）
            (pr.eval_date - d.value_date)::NUMERIC / 365.0
            -- 存款利率與基準利率之差（超額收益，若提前支取則損失此部分）
            * GREATEST(d.interest_rate - pr.base_rate, 0)
            -- 本金
            * d.principal
        ),
    2) AS rate_loss
FROM fsi.balance_deposit d
JOIN fsi.para_portfolio p ON p.port_id = d.port_id
CROSS JOIN params pr
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
  AND d.evaluate_date  = (SELECT eval_date FROM params)
  AND d.is_penalty_on_early_redeem = TRUE       -- 僅計算有提前支取罰息的存款
  AND d.value_date < (SELECT eval_date FROM params) -- 已過起息日
  AND d.maturity_date > (SELECT eval_date FROM params) -- 尚未到期
  AND d.principal > 0
GROUP BY p.port_name, p.port_id
ORDER BY p.port_name;
