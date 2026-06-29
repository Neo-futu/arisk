-- ============================================================
-- 報表03 / 15_overnight_repo.sql
-- 原始：SmartReport/03/15.sql  回購明細
-- Sheet：回购明细（A1=表頭，數據 A2）
-- ============================================================

SELECT
    r.port_id,
    p.port_name,
    -- 市场代码：轉為可讀描述
    CASE r.market_id
        WHEN 'IB'       THEN '銀行間'
        WHEN 'EXCH_SH'  THEN '上交所'
        WHEN 'EXCH_SZ'  THEN '深交所'
        WHEN 'HKEX'     THEN '港交所'
        ELSE COALESCE(r.market_id, '銀行間')
    END                                                     AS market_id,
    -- 证券类型：轉為可讀描述（源：AssetLiabilityFlag A/L）
    CASE r.repo_type
        WHEN 'REV_REPO' THEN '逆回購（融出）'
        WHEN 'REPO'     THEN '正回購（融入）'
        ELSE r.repo_type
    END                                                     AS asset_liability_flag,
    COALESCE(r.pledged_security_code, '-')                  AS security_code,
    ROUND(r.principal, 2)                                    AS cost,
    r.interest_rate,
    r.value_date,
    COALESCE(r.actual_maturity_date, r.maturity_date)       AS actual_maturity_date,
    ROUND(r.principal / NULLIF(n.net_asset,0), 8)           AS ratio_to_nav,
    COALESCE(r.counterparty_name, '-')                      AS counterparty_name
FROM fsi.balance_repo r
JOIN fsi.para_portfolio p ON p.port_id=r.port_id
JOIN fsi.balance_portfolio_nav n ON n.port_id=r.port_id
    AND n.evaluate_date=r.evaluate_date AND n.class_id IS NULL
WHERE p.is_mmf=TRUE AND p.is_active=TRUE
  AND r.evaluate_date='2026-06-25'::DATE
ORDER BY r.port_id, r.repo_type, r.counterparty_name;
