-- 持倉暴露彙總查詢（用於 Processing API）

-- 按資產類型彙總
SELECT
    p.fund_id,
    p.as_of_date,
    p.asset_type,
    COUNT(*)                                    AS position_count,
    SUM(p.market_value_hkd)                     AS total_mv_hkd,
    SUM(p.market_value_hkd) / n.total_nav * 100 AS weight_pct
FROM fsi.positions p
JOIN (
    SELECT fund_id, as_of_date, SUM(market_value_hkd) AS total_nav
    FROM fsi.positions
    WHERE fund_id = :fund_id AND as_of_date = :as_of_date
    GROUP BY fund_id, as_of_date
) n USING (fund_id, as_of_date)
WHERE p.fund_id = :fund_id
  AND p.as_of_date = :as_of_date
GROUP BY p.fund_id, p.as_of_date, p.asset_type, n.total_nav
ORDER BY weight_pct DESC;

-- 按發行人集中度
SELECT
    p.issuer_name,
    p.issuer_group,
    COUNT(*)                                    AS instrument_count,
    SUM(p.market_value_hkd)                     AS total_mv_hkd,
    SUM(p.market_value_hkd) / n.total_nav * 100 AS weight_pct,
    MAX(p.credit_rating)                        AS credit_rating,
    -- SFC 守則合規：單一實體 ≤10%（重要財務機構 ≤25%）
    CASE WHEN SUM(p.market_value_hkd) / n.total_nav * 100 > 10 THEN 'BREACH' ELSE 'OK' END AS compliance
FROM fsi.positions p
JOIN (
    SELECT fund_id, as_of_date, SUM(market_value_hkd) AS total_nav
    FROM fsi.positions
    WHERE fund_id = :fund_id AND as_of_date = :as_of_date
    GROUP BY fund_id, as_of_date
) n USING (fund_id, as_of_date)
WHERE p.fund_id = :fund_id
  AND p.as_of_date = :as_of_date
GROUP BY p.issuer_name, p.issuer_group, n.total_nav
ORDER BY weight_pct DESC;

-- WAM / WAL 計算
SELECT
    fund_id,
    as_of_date,
    SUM(weight_pct / 100 * LEAST(GREATEST((maturity_date - as_of_date), 0), 397)) AS wam_days,
    SUM(weight_pct / 100 * GREATEST((maturity_date - as_of_date), 0))              AS wal_days,
    -- 合規檢查
    CASE WHEN SUM(weight_pct / 100 * LEAST(GREATEST((maturity_date - as_of_date), 0), 397)) > 60
         THEN 'WAM_BREACH' ELSE 'OK' END AS wam_status,
    CASE WHEN SUM(weight_pct / 100 * GREATEST((maturity_date - as_of_date), 0)) > 120
         THEN 'WAL_BREACH' ELSE 'OK' END AS wal_status
FROM fsi.positions
WHERE fund_id = :fund_id
  AND as_of_date = :as_of_date
  AND maturity_date IS NOT NULL
GROUP BY fund_id, as_of_date;
