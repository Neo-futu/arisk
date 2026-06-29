-- ============================================================
-- 報表03 / 18_online_channel.sql
-- 原始：SmartReport/03/18.sql  網商渠道存量規模
-- Sheet：其他监控-sql导入数据，標籤18.sql@A2，表頭A3，數據A4
--
-- 欄位說明（對照模版表頭 A3-B3）：
--   组合名称              = port_name
--   网商渠道存量规模(亿元) = shares_100m
--                          （Shares/100M，MMF中1份≈1元，故近似億元）
--
-- 源 SQL：
--   SELECT PortName, SUM(Shares)/1E8
--   FROM T_Balance_Port_Holder_FundShare_SalesChannel
--   WHERE SalesChannelId='000392'   -- 螞蟻財富渠道代碼
--
-- FSI 對應表：fsi.balance_holder_by_channel（channel_id='000392'）
-- 香港等效：可替換為主要分銷渠道ID（如螞蟻HK/渣打/匯豐等）
--
-- ★ 修改 evaluate_date 和 channel_id 即可獨立運行
-- ============================================================

SELECT
    p.port_name,
    ROUND(COALESCE(SUM(h.shares), 0) / 100000000, 4) AS shares_100m   -- 网商渠道存量规模（亿份≈亿元）
FROM fsi.balance_holder_by_channel h
JOIN fsi.para_portfolio p ON p.port_id = h.port_id
WHERE h.confirm_date = '2026-06-25'::DATE
  AND h.channel_id   = '000392'        -- 網商渠道（螞蟻財富）代碼
  AND p.is_mmf = TRUE
  AND p.is_active = TRUE
GROUP BY p.port_name
ORDER BY p.port_name;
