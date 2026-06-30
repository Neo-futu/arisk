-- ============================================================
-- 報表 report_03_mmf / 42_stress_result.sql
-- 貨幣基金持倉壓力測試結果（+50bp 利率衝擊）
-- Sheet：压力测试结果，A1=表頭，數據從 A2 開始
--
-- 欄位說明：
--   A  port_name            组合名称
--   B  security_code        证券代码
--   C  security_name        证券名称
--   D  bond_type            资产类型
--   E  coupon_type          利率类型（FIXED/FLOAT/DEPOSIT）
--   F  market_value         当前市值（元）
--   G  duration             有效久期（年）
--   H  stressed_mv          压力市值（元）：= 市值 × (1 - 久期 × 0.005)
--   I  stressed_loss        压力损失（万元）：= (市值 - 压力市值) / 10000
--   J  bond_category        债券类别（利率债/信用债/同业存单/存款）
--   K  liq_ratio            变现系数
--   L  stressed_loss_adj    压力损失修正（万元）：= 压力损失 × 变现系数
--
-- 變現係數定義（修正版）：
--   DEPOSIT      → 0      合約本金，不做市場壓力計量
--   FLOAT        → 0.05   浮息債利率敏感度極低
--   BOND_GOVT    → 0.20   政府/政策行債，流動性最好
--   CD           → 0.20   同業存單，銀行間活躍交易，流動性接近利率債
--   BOND_CORP    → 0.80   信用債，壓力下流動性較差
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH nav AS (
    SELECT port_id, net_asset
    FROM fsi.balance_portfolio_nav
    WHERE evaluate_date = '2026-06-25'::DATE AND class_id IS NULL
),

-- 固定利率債（BOND_GOVT / BOND_CORP）
bonds AS (
    SELECT
        p.port_name,
        b.security_code,
        b.security_name,
        b.asset_subtype::TEXT                                       AS bond_type,
        COALESCE(b.coupon_type, 'FIXED')                           AS coupon_type,
        COALESCE(b.market_value, 0)                                AS market_value,
        -- 有效久期：浮息債取距下次重設日天數，固定/零息取存儲久期
        ROUND(
            CASE WHEN COALESCE(b.coupon_type,'FIXED') = 'FLOAT'
                THEN (b.maturity_date - '2026-06-25'::DATE)::NUMERIC / 365.0 * 0.5
                   + 0.5 * COALESCE(
                         (b.next_coupon_date - '2026-06-25'::DATE)::NUMERIC / 365.0,
                         (b.maturity_date - '2026-06-25'::DATE)::NUMERIC / 365.0)
                ELSE COALESCE(b.duration, b.remaining_days / 365.0, 0.0)
            END
        , 4)                                                        AS duration,
        n.net_asset
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    JOIN nav n ON n.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.quantity > 0
),

-- 存款證 CD（固定利率）
cds AS (
    SELECT
        p.port_name,
        c.security_code,
        c.security_name,
        'CD'                                                        AS bond_type,
        'FIXED'                                                     AS coupon_type,
        COALESCE(c.market_value, 0)                                AS market_value,
        ROUND(COALESCE(c.duration, c.remaining_days / 365.0, 0.0), 4) AS duration,
        n.net_asset
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    JOIN nav n ON n.port_id = c.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND c.maturity_date >= '2026-06-25'::DATE
),

-- 存款（不做壓力測試，但列入匯總供完整性）
deposits AS (
    SELECT
        p.port_name,
        d.deposit_id                                               AS security_code,
        d.deposit_name                                             AS security_name,
        'DEPOSIT'                                                  AS bond_type,
        'DEPOSIT'                                                  AS coupon_type,
        COALESCE(d.principal, 0)                                   AS market_value,
        0::NUMERIC                                                 AS duration,
        n.net_asset
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    JOIN nav n ON n.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND (d.maturity_date > '2026-06-25'::DATE OR d.maturity_date IS NULL)
),

all_holdings AS (
    SELECT * FROM bonds
    UNION ALL SELECT * FROM cds
    UNION ALL SELECT * FROM deposits
),

stress AS (
    SELECT
        port_name,
        security_code,
        security_name,
        bond_type,
        coupon_type,
        market_value,
        duration,

        -- 債券類別（U列）
        CASE
            WHEN bond_type = 'CD'                               THEN '同业存单'
            WHEN bond_type = 'DEPOSIT'                         THEN '存款'
            WHEN bond_type = 'BOND_GOVT'                       THEN '利率债'
            WHEN bond_type IN ('BOND_CORP','BOND_FLOAT')       THEN '信用债'
            ELSE '其他'
        END                                                     AS bond_category,

        -- 變現係數（V列，修正版）
        CASE
            WHEN coupon_type = 'DEPOSIT'                       THEN 0.00  -- 存款不計
            WHEN coupon_type = 'FLOAT'                         THEN 0.05  -- 浮息債
            WHEN bond_type   = 'BOND_GOVT'                     THEN 0.20  -- 利率債
            WHEN bond_type   = 'CD'                            THEN 0.20  -- 同業存單（修正：與利率債同）
            WHEN bond_type   = 'BOND_CORP'                     THEN 0.80  -- 信用債
            ELSE 0.20
        END                                                     AS liq_ratio,

        -- 壓力市值（+50bp 久期近似法）
        ROUND(
            CASE WHEN coupon_type = 'DEPOSIT' THEN market_value
                 ELSE market_value * (1.0 - duration * 0.005)
            END
        , 2)                                                    AS stressed_mv

    FROM all_holdings
)

SELECT
    port_name                                                   AS port_name,
    security_code,
    security_name,
    bond_type,
    coupon_type,
    market_value,
    duration,
    stressed_mv,
    -- 壓力損失（萬元）
    ROUND((market_value - stressed_mv) / 10000, 4)             AS stressed_loss,
    bond_category,
    liq_ratio,
    -- 壓力損失修正（考慮變現係數）
    ROUND((market_value - stressed_mv) / 10000 * liq_ratio, 4) AS stressed_loss_adj
FROM stress
ORDER BY port_name DESC,
         (market_value - stressed_mv) DESC,  -- 損失最大排前
         bond_type;
