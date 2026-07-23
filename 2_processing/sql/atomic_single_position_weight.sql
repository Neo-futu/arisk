-- atomic_single_position_weight.sql
-- 原子指標：個股/個券市值佔淨值比 (%)

WITH position_summary AS (
    SELECT
        fund_id,
        as_of_date,
        COALESCE(security_code, instrument_id, 'UNKNOWN') AS security_code,
        COALESCE(security_name, 'UNNAMED') AS security_name,
        SUM(market_value_hkd) AS position_mv_hkd,
        SUM(SUM(market_value_hkd)) OVER (PARTITION BY fund_id, as_of_date) AS total_nav
    FROM fsi.positions
    WHERE fund_id = :fid
      AND as_of_date = :as_of_date
    GROUP BY fund_id, as_of_date, COALESCE(security_code, instrument_id, 'UNKNOWN'), COALESCE(security_name, 'UNNAMED')
)
SELECT
    fund_id,
    as_of_date,
    security_code,
    security_name,
    position_mv_hkd,
    total_nav,
    -- 個股/個券市值佔淨值比 (%) = (單一持倉市值 / 基金淨資產 NAV) * 100
    CASE
        WHEN total_nav IS NULL OR total_nav = 0 THEN NULL
        ELSE ROUND((position_mv_hkd / total_nav) * 100.0, 6)
    END AS weight_pct
FROM position_summary
ORDER BY weight_pct DESC NULLS LAST;