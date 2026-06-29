-- ============================================================
-- 報表03 / 01_nav_deviation.sql
-- 原始：SmartReport/03/01.sql  偏离展示(平均指数)
-- Sheet：日报-sql导入数据，標籤01.sql@A3，表頭A4，數據A5
--
-- 欄位說明（對照模版表頭）：
--   组合/指标       = port_name
--   净值(成本,元)   = net_asset（原始元，攤余成本法NAV）
--   偏离度（bp）    = nav_deviation_amount / net_asset * 10000
--                    （基點：1bp=0.01%，公式同源 DeviationAmount/NetAsset*10000）
--   偏离金额（元）  = nav_deviation_amount（原始元）
--   万份收益        = income_per_10k（元/萬份）
--   七日收益率（%） = return_rate_7d（%）
--   平均剩余期限    = wam_days（天，SFC守則≤60天）
--   平均剩余存续期  = wal_days（天，SFC守則≤120天）
--
-- ★ 修改 evaluate_date 即可在 pgAdmin / psql 獨立運行
-- ============================================================

SELECT
    p.port_name,
    n.net_asset,                                                -- 净值(成本,元) 原始元
    ROUND(m.nav_deviation_amount / NULLIF(n.net_asset, 0) * 10000, 2)
                                                                AS deviation_bp,     -- 偏离度（bp）
    m.nav_deviation_amount,                                     -- 偏离金额（元）
    m.income_per_10k,                                           -- 万份收益
    m.return_rate_7d,                                           -- 七日收益率（%）
    m.wam_days,                                                 -- 平均剩余期限（天）
    m.wal_days                                                  -- 平均剩余存续期（天）
FROM fsi.balance_portfolio_nav n
JOIN fsi.para_portfolio       p ON p.port_id = n.port_id
JOIN fsi.balance_portfolio_mmf m ON m.port_id = n.port_id
                                 AND m.evaluate_date = n.evaluate_date
WHERE p.is_mmf    = TRUE
  AND p.is_active = TRUE
  AND n.evaluate_date = '2026-06-25'::DATE
  AND n.class_id IS NULL
ORDER BY n.net_asset DESC;
