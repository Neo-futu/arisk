-- ============================================================
-- 報表03 / 03_deviation_breakdown.sql
-- 原始：SmartReport/03/03.sql  偏離按品種拆分（9列）
-- Sheet：日报-sql导入数据 @ A118
--
-- 欄位說明（對應源 SQL 9列）：
--   PortName, DeviationAmount,
--   cd_deviation, scp_deviation(短融/CP), mtn_deviation(中票),
--   treasury_deviation(國庫券), policybond_deviation(政策性債),
--   cd%, scp%, mtn%, tbond%, pbond%
--
-- HK對應：
--   國庫券→港府票據(BOND_GOVT issuer=HK政府)
--   政策性債→機構債(BOND_GOVT issuer=HKMA/EIB等)
--   短融/CP → asset_subtype='CP'
--   中票MTN → asset_subtype='BOND_CORP' (中期)
--   存單CD → balance_cd
-- ============================================================

WITH total_deviation AS (
    SELECT m.port_id, p.port_name, m.nav_deviation_amount AS deviation_amount
    FROM fsi.balance_portfolio_mmf m
    JOIN fsi.para_portfolio p ON p.port_id=m.port_id
    WHERE p.is_mmf=TRUE AND p.is_active=TRUE
      AND m.evaluate_date='2026-06-25'::DATE
),

cd_dev AS (
    SELECT c.port_id,
           SUM(COALESCE(c.market_value,0)-COALESCE(c.cost,0)) AS cd_dev
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id=c.port_id
    WHERE p.is_mmf=TRUE AND c.evaluate_date='2026-06-25'::DATE
    GROUP BY c.port_id
),

bond_dev AS (
    SELECT b.port_id,
           -- 短融/商票（CP）
           SUM(CASE WHEN b.asset_subtype='CP'
                    THEN COALESCE(b.market_value,0)-COALESCE(b.cost,0) ELSE 0 END) AS scp_dev,
           -- 中票MTN（BOND_CORP 長期信用債近似）
           SUM(CASE WHEN b.asset_subtype='BOND_CORP'
                    THEN COALESCE(b.market_value,0)-COALESCE(b.cost,0) ELSE 0 END) AS mtn_dev,
           -- 港府票據/國庫券（BOND_GOVT，政府直接發行）
           SUM(CASE WHEN b.asset_subtype='BOND_GOVT'
                        AND COALESCE(b.issuer_name,'') NOT ILIKE '%政策%'
                        AND COALESCE(b.issuer_name,'') NOT ILIKE '%HKMA%'
                    THEN COALESCE(b.market_value,0)-COALESCE(b.cost,0) ELSE 0 END) AS treasury_dev,
           -- 政策性債（BOND_GOVT 中機構發行，如HKMA票據/EIB）
           SUM(CASE WHEN b.asset_subtype='BOND_GOVT'
                        AND (COALESCE(b.issuer_name,'') ILIKE '%政策%'
                          OR COALESCE(b.issuer_name,'') ILIKE '%HKMA%'
                          OR COALESCE(b.issuer_name,'') ILIKE '%金管%')
                    THEN COALESCE(b.market_value,0)-COALESCE(b.cost,0) ELSE 0 END) AS policy_dev
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id=b.port_id
    WHERE p.is_mmf=TRUE AND b.evaluate_date='2026-06-25'::DATE
    GROUP BY b.port_id
)

SELECT
    t.port_name,
    ROUND(t.deviation_amount, 2)                              AS total_deviation,
    -- 各品種偏差金額
    ROUND(COALESCE(c.cd_dev,0), 2)                           AS cd_deviation,
    ROUND(COALESCE(b.scp_dev,0), 2)                          AS scp_deviation,     -- 短融/CP
    ROUND(COALESCE(b.mtn_dev,0), 2)                          AS mtn_deviation,     -- 中票/信用債
    ROUND(COALESCE(b.treasury_dev,0), 2)                     AS treasury_deviation,-- 國庫券/港府票據
    ROUND(COALESCE(b.policy_dev,0), 2)                       AS policybond_deviation, -- 政策性債
    -- 各品種佔總偏差比例
    ROUND(COALESCE(c.cd_dev,0)  / NULLIF(t.deviation_amount,0), 6) AS cd_pct,
    ROUND(COALESCE(b.scp_dev,0) / NULLIF(t.deviation_amount,0), 6) AS scp_pct,
    ROUND(COALESCE(b.mtn_dev,0) / NULLIF(t.deviation_amount,0), 6) AS mtn_pct,
    ROUND(COALESCE(b.treasury_dev,0) / NULLIF(t.deviation_amount,0), 6) AS treasury_pct,
    ROUND(COALESCE(b.policy_dev,0) / NULLIF(t.deviation_amount,0), 6) AS policy_pct
FROM total_deviation t
LEFT JOIN cd_dev   c ON c.port_id=t.port_id
LEFT JOIN bond_dev b ON b.port_id=t.port_id
ORDER BY t.port_name;
