-- atomic_daily_income_per_10k.sql
-- 原子指標：每萬份日收益（貨幣市場基金專用）

SELECT
    m.port_id AS fund_id,
    m.evaluate_date AS as_of_date,
    n.total_nav,
    m.income_per_10k
FROM fsi.balance_portfolio_mmf m
LEFT JOIN (
    SELECT 
        port_id, 
        evaluate_date, 
        COALESCE(net_asset, total_asset) AS total_nav
    FROM fsi.balance_portfolio_nav
) n ON m.port_id = n.port_id AND m.evaluate_date = n.evaluate_date
WHERE m.port_id = :fid
  AND m.evaluate_date BETWEEN :start_date AND :end_date
ORDER BY m.evaluate_date ASC;