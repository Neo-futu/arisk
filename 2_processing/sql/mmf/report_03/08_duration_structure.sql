WITH -- ============================================================
-- 報表03 / 08_duration_structure.sql
-- 原始：SmartReport/03/08.sql  偏離債務組合期限結構
-- 功能：按評級類別分組的加權平均久期
-- 參數：params.evaluate_date DATE
-- ============================================================

detail AS (
    SELECT
        b.port_id,
        b.security_code,
        b.market_value,
        -- 浮息債用下次重定價日，固息債用到期日
        CASE
            WHEN b.coupon_type = 'FLOAT' AND b.next_coupon_date IS NOT NULL
                THEN (b.next_coupon_date - params.evaluate_date::DATE) / 365.0
            ELSE COALESCE(b.duration, b.remaining_days / 365.0)
        END AS effective_duration,
        CASE
            WHEN b.asset_subtype = 'BOND_GOVT'              THEN 1  -- 利率/政府債
            WHEN b.issuer_rating IN ('AAA','AAA+')          THEN 2  -- AAA 信用債
            WHEN b.issuer_rating IN ('AA+')                 THEN 3  -- AA+
            WHEN b.issuer_rating IN ('AA','AA-')            THEN 4  -- AA
            ELSE 5                                                    -- 其他/未評級
        END AS rating_category
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = params.evaluate_date
      AND b.market_value > 0

    UNION ALL

    SELECT
        c.port_id,
        c.security_code,
        c.market_value,
        COALESCE(c.duration, c.remaining_days / 365.0) AS effective_duration,
        CASE
            WHEN c.issuer_rating IN ('AAA','AAA+') THEN 2
            WHEN c.issuer_rating IN ('AA+')        THEN 3
            WHEN c.issuer_rating IN ('AA','AA-')   THEN 4
            ELSE 5
        END AS rating_category
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = params.evaluate_date
      AND c.market_value > 0
),

category_labels AS (
    SELECT 1 AS rating_category, '利率/政府債' AS label
    UNION ALL SELECT 2, 'AAA信用債/存單'
    UNION ALL SELECT 3, 'AA+信用債/存單'
    UNION ALL SELECT 4, 'AA信用債/存單'
    UNION ALL SELECT 5, '其他/未評級'
)

SELECT
    p.port_name,
    lbl.label                                                       AS rating_category,
    ROUND(SUM(d.market_value) / 100000000, 4)                       AS mv_100m,
    ROUND(SUM(d.market_value * d.effective_duration) /
          NULLIF(SUM(d.market_value), 0), 4)                        AS weighted_duration
FROM detail d
JOIN category_labels lbl ON lbl.rating_category = d.rating_category
JOIN fsi.para_portfolio p ON p.port_id = d.port_id
GROUP BY p.port_name, lbl.label
ORDER BY p.port_name, lbl.label;
