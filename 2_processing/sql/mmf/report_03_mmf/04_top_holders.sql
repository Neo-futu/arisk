-- ============================================================
-- 報表03 / 04_top_holders.sql
-- 原始：SmartReport/03/04.sql  投资者持有情况
-- Sheet：日报-sql导入数据，標籤04.sql@D23，表頭D24-D25，數據D26
--
-- 欄位說明（對照模版表頭 D24-H25）：
--   组合                   = port_name
--   机构投资者 总占比（%）  = institutional_pct
--   机构投资者 单一最大（%）= top1_pct（Rank1金額/全部持有人金額×100）
--   前10大 总占比（%）      = top10_all_pct（前10大金額/NAV×100，含所有持有人）
--   前10大 扣固（%）        = top10_excl_pct（排除固定持有人後）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH nav AS (
    SELECT port_id, net_asset
    FROM fsi.balance_portfolio_nav
    WHERE evaluate_date = '2026-06-25'::DATE
      AND class_id IS NULL
),

institutional AS (
    SELECT hs.port_id,
           ROUND(COALESCE(hs.institutional_holders,0)::NUMERIC /
                 NULLIF(hs.total_holders,0) * 100, 2) AS institutional_pct
    FROM fsi.balance_holder_summary hs
    WHERE hs.confirm_date = '2026-06-25'::DATE
      AND hs.class_id = 'ALL'
),

top1 AS (
    SELECT r.port_id,
           ROUND(r.pct_of_total, 2) AS top1_pct
    FROM fsi.balance_holder_rank r
    WHERE r.confirm_date = '2026-06-25'::DATE
      AND r.rank_no = 1
),

top10_all AS (
    SELECT r.port_id,
           ROUND(SUM(r.amount) / NULLIF(n.net_asset,0) * 100, 4) AS top10_all_pct
    FROM fsi.balance_holder_rank r
    JOIN nav n ON n.port_id = r.port_id
    WHERE r.confirm_date = '2026-06-25'::DATE AND r.rank_no <= 10
    GROUP BY r.port_id, n.net_asset
),

-- 扣固：生產環境加 AND r.holder_id NOT IN ('固定持有人ID')
top10_excl AS (
    SELECT r.port_id,
           ROUND(SUM(r.amount) / NULLIF(n.net_asset,0) * 100, 4) AS top10_excl_pct
    FROM fsi.balance_holder_rank r
    JOIN nav n ON n.port_id = r.port_id
    WHERE r.confirm_date = '2026-06-25'::DATE AND r.rank_no <= 10
    GROUP BY r.port_id, n.net_asset
)

SELECT
    p.port_name,
    COALESCE(i.institutional_pct, 0)  AS institutional_pct,
    COALESCE(t1.top1_pct, 0)          AS top1_pct,
    COALESCE(ta.top10_all_pct, 0)     AS top10_all_pct,
    COALESCE(te.top10_excl_pct, 0)    AS top10_excl_pct
FROM fsi.para_portfolio p
LEFT JOIN institutional i  ON i.port_id  = p.port_id
LEFT JOIN top1         t1  ON t1.port_id = p.port_id
LEFT JOIN top10_all    ta  ON ta.port_id = p.port_id
LEFT JOIN top10_excl   te  ON te.port_id = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
