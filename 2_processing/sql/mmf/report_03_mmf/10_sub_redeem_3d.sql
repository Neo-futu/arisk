-- ============================================================
-- 報表03 / 10_sub_redeem_3d.sql
-- 原始：SmartReport/03/10.sql  前三日申赎金额
-- Sheet：日报-sql导入数据，標籤10.sql@A94，表頭A95，數據A96
--
-- 欄位說明（對照模版表頭 A95-D95）：
--   前三日申赎金额表  = port_name（組合名）
--   明日确认          = next_day_net（T+1確認的淨申購，億）
--   当日&昨日确认     = today_yesterday_net（NAV_T-NAV_{T-1} + NAV_{T-1}-NAV_{T-2}，億）
--   T-2日净值         = nav_t2（T-2日NAV，億，日報中作為參考基準）
--
-- 邏輯說明：
--   明日确认  = T_Transact_Port_Purchase_Redeem[ConfirmDate=T+1].NetPurchaseAmount
--              → FSI: transact_portfolio_cashflow WHERE evaluate_date=T+1
--   当日&昨日 = (NAV_T - NAV_{T-1}) + (NAV_{T-1} - NAV_{T-2})
--              = NAV_T - NAV_{T-2}（兩天NAV總變化，近似兩日淨申購合計）
--   T-2净值  = balance_portfolio_nav WHERE evaluate_date=T-2
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH eval_date AS (
    SELECT '2026-06-25'::DATE AS d
),

-- T+1確認的淨申購（明日確認）
next_day AS (
    SELECT c.port_id,
           SUM(COALESCE(c.net_purchase, 0)) / 100000000 AS net_purchase_100m
    FROM fsi.transact_portfolio_cashflow c, eval_date e
    WHERE c.port_id = ANY(ARRAY(
              SELECT port_id FROM fsi.para_portfolio
              WHERE is_mmf = TRUE AND is_active = TRUE))
      AND c.evaluate_date = e.d + 1
      AND c.currency = 'HKD'
    GROUP BY c.port_id
),

-- T日NAV
nav_t AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n, eval_date e
    WHERE n.evaluate_date = e.d AND n.class_id IS NULL
),

-- T-1日NAV
nav_t1 AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n, eval_date e
    WHERE n.evaluate_date = e.d - 1 AND n.class_id IS NULL
),

-- T-2日NAV（作為基準參考）
nav_t2 AS (
    SELECT n.port_id, n.net_asset
    FROM fsi.balance_portfolio_nav n, eval_date e
    WHERE n.evaluate_date = e.d - 2 AND n.class_id IS NULL
)

SELECT
    p.port_name,
    -- 明日确认（T+1確認淨申購，億）
    ROUND(COALESCE(nd.net_purchase_100m, 0), 4)                      AS next_day_net,
    -- 当日&昨日确认 = (NAV_T - NAV_{T-1}) + (NAV_{T-1} - NAV_{T-2}) = NAV_T - NAV_{T-2}（億）
    ROUND((COALESCE(nt.net_asset, 0) - COALESCE(nt2.net_asset, 0))
          / 100000000, 4)                                             AS today_yesterday_net,
    -- T-2日净值（亿）
    ROUND(COALESCE(nt2.net_asset, 0) / 100000000, 4)                 AS nav_t2
FROM fsi.para_portfolio p
LEFT JOIN next_day nd  ON nd.port_id  = p.port_id
LEFT JOIN nav_t    nt  ON nt.port_id  = p.port_id
LEFT JOIN nav_t1   nt1 ON nt1.port_id = p.port_id
LEFT JOIN nav_t2   nt2 ON nt2.port_id = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
