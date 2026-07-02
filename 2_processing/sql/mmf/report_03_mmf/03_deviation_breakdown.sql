-- ============================================================
-- 報表03 / 03_deviation_breakdown.sql
-- 偏離度按資產類別拆分（HK MMF 口徑）
-- Sheet：日报-sql导入数据 @ A118
--
-- HK MMF 資產分類（對應 UT Code §8.2 及 SFC 監管術語）：
--   港府/公共債券  Government/Public Securities
--     → BOND_GOVT + 政府及交易所基金票據發行人
--   機構債        Agency Bonds
--     → BOND_GOVT + 機構發行人（HKMA、EIB、ADB 等）
--   信用類工具    Credit Instruments（企業債 + CP）
--     → BOND_CORP，asset_subtype IN ('CP','BOND_CORP')
--   同業存單      Certificates of Deposit (CD)
--     → balance_cd 表
--
-- 偏離度貢獻(bp) = 各類別佔總偏差比例 × 基金整體偏離度
--   各資產偏差金額(元) = market_value - cost
--   各類別比例 = 該類偏差 / 組合總偏差
--
-- 欄位說明（12列，對應模版 _DV 範圍）：
--   col1  port_name              組合名稱
--   col2  total_deviation        組合總偏差金額（元）= nav_deviation_amount
--   col3  gov_bond_deviation     港府/公共債券偏差（元）
--   col4  agency_deviation       機構債偏差（元）
--   col5  credit_deviation       信用類工具偏差（元；含企業債+CP）
--   col6  cd_deviation           同業存單偏差（元）
--   col7  gov_bond_mv            港府/公共債券市值（億元）
--   col8  agency_mv              機構債市值（億元）
--   col9  credit_mv              信用類工具市值（億元）
--   col10 cd_mv                  同業存單市值（億元）
--   col11 other_mv               其他資產市值（億元；含存款等）
--   col12 portfolio_yield        組合加權平均收益率（%；來自 01 sql）
--
-- 注意：偏離度貢獻(bp) = col_pct × 組合整體偏離度(bp)
--   其中 col_pct = col_deviation / total_deviation（在模版計算）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH

-- 組合總偏差（來自系統計算，優先用此值作為分母）
total_dev AS (
    SELECT m.port_id,
           p.port_name,
           COALESCE(m.nav_deviation_amount, 0) AS total_deviation
    FROM fsi.balance_portfolio_mmf m
    JOIN fsi.para_portfolio p ON p.port_id = m.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND m.evaluate_date = '2026-06-25'::DATE
),

-- ── 各類別偏差（market_value - cost）────────────────────────

-- 港府/公共債券偏差（Exchange Fund Bills/Notes + HK Govt Bonds）
-- 識別方式：BOND_GOVT 且發行人為港府或交易所基金
gov_bond_dev AS (
    SELECT b.port_id,
           SUM(COALESCE(b.market_value, 0) - COALESCE(b.cost, 0)) AS dev,
           SUM(COALESCE(b.market_value, 0)) / 100000000.0          AS mv_100m
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype = 'BOND_GOVT'
      AND NOT (   COALESCE(b.issuer_name, '') ILIKE '%HKMA%'
               OR COALESCE(b.issuer_name, '') ILIKE '%金管%'
               OR COALESCE(b.issuer_name, '') ILIKE '%Monetary Authority%'
               OR COALESCE(b.issuer_name, '') ILIKE '%EIB%'
               OR COALESCE(b.issuer_name, '') ILIKE '%World Bank%'
               OR COALESCE(b.issuer_name, '') ILIKE '%ADB%'
               OR COALESCE(b.issuer_name, '') ILIKE '%IBRD%'
               OR COALESCE(b.issuer_name, '') ILIKE '%IFC%')
    GROUP BY b.port_id
),

-- 機構債偏差（HKMA、EIB、ADB、World Bank 等機構發行的 BOND_GOVT）
agency_dev AS (
    SELECT b.port_id,
           SUM(COALESCE(b.market_value, 0) - COALESCE(b.cost, 0)) AS dev,
           SUM(COALESCE(b.market_value, 0)) / 100000000.0          AS mv_100m
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype = 'BOND_GOVT'
      AND (   COALESCE(b.issuer_name, '') ILIKE '%HKMA%'
           OR COALESCE(b.issuer_name, '') ILIKE '%金管%'
           OR COALESCE(b.issuer_name, '') ILIKE '%Monetary Authority%'
           OR COALESCE(b.issuer_name, '') ILIKE '%EIB%'
           OR COALESCE(b.issuer_name, '') ILIKE '%World Bank%'
           OR COALESCE(b.issuer_name, '') ILIKE '%ADB%'
           OR COALESCE(b.issuer_name, '') ILIKE '%IBRD%'
           OR COALESCE(b.issuer_name, '') ILIKE '%IFC%')
    GROUP BY b.port_id
),

-- 信用類工具偏差（BOND_CORP 企業債 + CP 商業票據）
-- 中長期信用債、商業票據均歸此類
credit_dev AS (
    SELECT b.port_id,
           SUM(COALESCE(b.market_value, 0) - COALESCE(b.cost, 0)) AS dev,
           SUM(COALESCE(b.market_value, 0)) / 100000000.0          AS mv_100m
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype IN ('BOND_CORP', 'CP', 'BOND_CONVERT', 'BOND_ABS')
    GROUP BY b.port_id
),

-- 同業存單偏差（balance_cd）
cd_dev AS (
    SELECT c.port_id,
           SUM(COALESCE(c.market_value, 0) - COALESCE(c.cost, 0)) AS dev,
           SUM(COALESCE(c.market_value, 0)) / 100000000.0          AS mv_100m
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND c.evaluate_date = '2026-06-25'::DATE
    GROUP BY c.port_id
),

-- 存款市值（活期 + 定期，按本金，無偏差概念）
-- 業務說明：存款採攤余成本法，本金≈市值，偏差≈0，但佔 NAV 約 30%，不可忽視
-- 分類：
--   活期（is_overnight=TRUE 或 maturity_date=T+1）→ 計入 DLA
--   定期1-5天（maturity_date T+2~T+5）            → 計入 WLA
--   定期6天以上                                    → 不計入 DLA/WLA
deposit_mv AS (
    SELECT d.port_id,
           SUM(COALESCE(d.principal, 0)) / 100000000.0               AS mv_100m,
           -- 分期統計，便於報表展示
           SUM(CASE WHEN d.is_overnight = TRUE
                      OR d.maturity_date <= '2026-06-25'::DATE + 1
                    THEN COALESCE(d.principal, 0) ELSE 0 END)
               / 100000000.0                                          AS dla_mv_100m,  -- 計入DLA部分
           SUM(CASE WHEN d.maturity_date BETWEEN '2026-06-25'::DATE + 2
                                              AND '2026-06-25'::DATE + 5
                    THEN COALESCE(d.principal, 0) ELSE 0 END)
               / 100000000.0                                          AS wla_only_100m -- 僅計入WLA部分
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND d.evaluate_date = '2026-06-25'::DATE
    GROUP BY d.port_id
)

SELECT
    t.port_name,

    -- col2: 組合總偏差（元），來自系統 WAM/NAV 計算
    ROUND(t.total_deviation, 2)                                    AS total_deviation,

    -- col3-col6: 各資產類別偏差（元）
    ROUND(COALESCE(gd.dev, 0), 2)                                  AS gov_bond_deviation,
    ROUND(COALESCE(ad.dev, 0), 2)                                  AS agency_deviation,
    ROUND(COALESCE(cd_c.dev, 0), 2)                                AS credit_deviation,
    ROUND(COALESCE(cdd.dev, 0), 2)                                 AS cd_deviation,

    -- col7-col12: 各資產類別市值（億元）— 含存款，覆蓋全部 NAV
    ROUND(COALESCE(gd.mv_100m, 0), 6)                             AS gov_bond_mv,
    ROUND(COALESCE(ad.mv_100m, 0), 6)                             AS agency_mv,
    ROUND(COALESCE(cd_c.mv_100m, 0), 6)                           AS credit_mv,
    ROUND(COALESCE(cdd.mv_100m, 0), 6)                            AS cd_mv,
    -- 存款（偏差固定為0，但佔 NAV 約30%，需在偏離度分解表中明確列示）
    ROUND(COALESCE(dm.mv_100m, 0), 6)                             AS deposit_mv,
    -- 存款中可計 DLA 部分（活期+T+1到期）
    ROUND(COALESCE(dm.dla_mv_100m, 0), 6)                         AS deposit_dla_mv

FROM total_dev t
LEFT JOIN gov_bond_dev gd   ON gd.port_id   = t.port_id
LEFT JOIN agency_dev   ad   ON ad.port_id   = t.port_id
LEFT JOIN credit_dev   cd_c ON cd_c.port_id = t.port_id
LEFT JOIN cd_dev       cdd  ON cdd.port_id  = t.port_id
LEFT JOIN deposit_mv   dm   ON dm.port_id   = t.port_id
ORDER BY t.port_name;
