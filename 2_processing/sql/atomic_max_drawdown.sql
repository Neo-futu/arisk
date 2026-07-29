-- atomic_max_drawdown.sql
-- 最大回撤 (%) (Max Drawdown)
-- 計算公式：Max Drawdown = MAX_t [ (Peak_t - NAV_t) / Peak_t ] * 100%
-- 表中需要添加totalreturn

WITH nav_series AS (
    -- 1. 取出指定基金在指定日期範圍內的每日 NAV 数据
    -- 优先使用累计单位净值 acc_unit_nav，若无则依次降级使用 unit_nav, net_asset
    SELECT
        port_id AS fund_id,
        evaluate_date AS as_of_date,
        COALESCE(acc_unit_nav, unit_nav, net_asset, 0.0) AS nav_val
    FROM fsi.balance_portfolio_nav
    WHERE port_id = :fid
      AND evaluate_date BETWEEN :start_date AND :end_date
),
peak_series AS (
    -- 2. 計算截至當日之歷史最高淨值 Peak_t
    SELECT
        fund_id,
        as_of_date,
        nav_val,
        MAX(nav_val) OVER (
            PARTITION BY fund_id 
            ORDER BY as_of_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS peak_nav
    FROM nav_series
),
drawdown_series AS (
    -- 3. 計算當日回撤比例 (Peak - NAV) / Peak
    SELECT
        fund_id,
        as_of_date,
        nav_val,
        peak_nav,
        CASE 
            WHEN peak_nav IS NOT NULL AND peak_nav > 0 
            THEN (peak_nav - nav_val) / peak_nav 
            ELSE 0.0 
        END AS drawdown
    FROM peak_series
),
max_drawdown_summary AS (
    -- 4. 取得最大回撤值
    SELECT
        fund_id,
        MAX(drawdown) AS max_drawdown_val
    FROM drawdown_series
    GROUP BY fund_id
)
SELECT
    d.fund_id,
    :start_date AS start_date,
    :end_date AS end_date,
    
    -- 最大回撤 (%)
    ROUND(m.max_drawdown_val * 100.0, 6) AS max_drawdown_pct,
    
    -- 發生最大回撤之谷值日期 (Trough Date)
    MIN(d.as_of_date) FILTER (WHERE d.drawdown = m.max_drawdown_val) AS trough_date,
    
    -- 谷值淨值
    ROUND(MIN(d.nav_val) FILTER (WHERE d.drawdown = m.max_drawdown_val), 6) AS trough_nav,
    
    -- 對應高點淨值 (Peak NAV)
    ROUND(MIN(d.peak_nav) FILTER (WHERE d.drawdown = m.max_drawdown_val), 6) AS peak_nav
FROM drawdown_series d
JOIN max_drawdown_summary m ON d.fund_id = m.fund_id
GROUP BY d.fund_id, m.max_drawdown_val;

