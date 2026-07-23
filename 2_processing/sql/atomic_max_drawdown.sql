-- atomic_max_drawdown.sql
-- 最大回撤 (%) (Max Drawdown)
-- 計算公式：Max Drawdown = MAX_t [ (Peak_t - NAV_t) / Peak_t ] * 100%

WITH daily_portfolio AS (
    SELECT
        as_of_date,
        fund_id,
        SUM(COALESCE(market_value_hkd, 0.0)) AS total_mv,
        SUM(COALESCE(pnl_hkd, 0.0)) AS total_pnl
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date BETWEEN :start_date AND :end_date
    GROUP BY as_of_date, fund_id
),
daily_returns AS (
    SELECT
        as_of_date,
        fund_id,
        CASE WHEN total_mv > 0 THEN total_pnl / total_mv ELSE 0.0 END AS r_p
    FROM daily_portfolio
),
nav_series AS (
    SELECT
        as_of_date,
        fund_id,
        r_p,
        -- 計算當日累計淨值指數 (以 1.0 為基期)
        EXP(SUM(LN(1.0 + r_p)) OVER (PARTITION BY fund_id ORDER BY as_of_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)) AS nav_index
    FROM daily_returns
),
peak_series AS (
    SELECT
        as_of_date,
        fund_id,
        nav_index,
        -- 截至當日之歷史最高淨值 Peak_t
        MAX(nav_index) OVER (PARTITION BY fund_id ORDER BY as_of_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS peak_nav
    FROM nav_series
),
drawdown_series AS (
    SELECT
        as_of_date,
        fund_id,
        nav_index,
        peak_nav,
        -- 當日回撤比例 (Peak - NAV) / Peak
        CASE 
            WHEN peak_nav > 0 THEN (peak_nav - nav_index) / peak_nav 
            ELSE 0.0 
        END AS drawdown
    FROM peak_series
),
max_drawdown_summary AS (
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
    
    -- 谷值淨值指數
    ROUND(MIN(d.nav_index) FILTER (WHERE d.drawdown = m.max_drawdown_val), 6) AS trough_nav,
    
    -- 對應高點淨值指數 (Peak NAV)
    ROUND(MIN(d.peak_nav) FILTER (WHERE d.drawdown = m.max_drawdown_val), 6) AS peak_nav
FROM drawdown_series d
JOIN max_drawdown_summary m ON d.fund_id = m.fund_id
GROUP BY d.fund_id, m.max_drawdown_val;