-- ============================================================
-- 報表03 / 17_stress_test.sql
-- 原始：SmartReport/03/17.sql  壓力測試持倉明細
-- Sheet：持仓数据（A1=表頭，數據從 A2 開始）
--
-- 輸出 16 列（對應 Excel A~P 列表頭）：
--   A  port_name            组合名称
--   B  bond_type            证券类型
--   C  security_code        证券代码
--   D  security_name        证券名称
--   E  quantity             数量
--   F  cost                 成本（攤余成本，元）
--   G  clean_mv             市值净价（元）
--   H  cost_dirty           成本全价（元）
--   I  shadow_dev           影价偏离度（bp/萬份）
--   J  pct_nav              市值占净值比（%）
--   K  dev_10k              偏离金额（万元）
--   L  maturity_date        到期日
--   M  coupon_type          利率类型（FI=固息 FL=浮息 ZC=零息 0=存款）
--                          ↑ 輸出值對齊 Excel 模板 M$1="FI" 的判斷邏輯
--   N  duration             久期（年）：浮息債 = 0.5×剩餘全期 + 0.5×距下次付息日
--   O  rating               评级
--   P  is_current_quarter   是否当季到期
--
-- 壓力值在 CTE 內計算，僅用於排序，不進入最終輸出
-- 壓力公式（對應原始 17.sql）：
--   stressed_mv = market_value × (1 - duration × 0.005)
--
-- 覆蓋：債券 + 存款證（CD）+ 存款（定期）
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH nav AS (
    SELECT port_id, net_asset
    FROM fsi.balance_portfolio_nav
    WHERE evaluate_date = '2026-06-25'::DATE AND class_id IS NULL
),

quarter_end AS (
    SELECT DATE_TRUNC('quarter', '2026-06-25'::DATE)
           + INTERVAL '3 month' - INTERVAL '1 day' AS qend
),

bonds AS (
    SELECT
        p.port_name,
        -- 浮息債用特殊類型代碼，其餘沿用資產子類型
        CASE WHEN COALESCE(b.coupon_type,'FIXED') = 'FLOAT'
             THEN 'BOND_FLOAT'
             ELSE b.asset_subtype::TEXT
        END                                                         AS bond_type,
        b.security_code,
        b.security_name,
        COALESCE(b.quantity, 0)                                     AS quantity,
        COALESCE(b.cost, 0)                                         AS cost,
        COALESCE(b.market_value, 0)                                 AS clean_mv,
        COALESCE(b.cost, 0) + COALESCE(b.accrued_interest, 0)      AS cost_dirty,
        -- 影子定價偏離度 = (市值 - 成本) / NAV × 10000
        ROUND(
            (COALESCE(b.market_value,0) - COALESCE(b.cost,0))
            / NULLIF(n.net_asset, 0) * 10000
        , 6)                                                        AS shadow_dev,
        ROUND(COALESCE(b.market_value,0) / NULLIF(n.net_asset,0) * 100, 6) AS pct_nav,
        ROUND((COALESCE(b.market_value,0) - COALESCE(b.cost,0)) / 10000, 4) AS dev_10k,
        b.maturity_date,
        -- 轉換為 Excel 模板格式：FI/FL/ZC/0，與 M$1="FI" 判斷對齊
        CASE COALESCE(b.coupon_type, 'FIXED')
            WHEN 'FIXED' THEN 'FI'
            WHEN 'FLOAT' THEN 'FL'
            WHEN 'ZERO'  THEN 'ZC'
            WHEN 'ZC'    THEN 'ZC'
            ELSE COALESCE(b.coupon_type, 'FI')
        END                                                         AS coupon_type,
        -- 浮息債久期 = 0.5×剩餘全期天數/365 + 0.5×距下次付息日天數/365（同原始17.sql）
        -- 固定/零息債：直接使用存儲久期，缺失時用剩餘天數估算
        ROUND(
            CASE WHEN COALESCE(b.coupon_type,'FIXED') = 'FLOAT'
                THEN (b.maturity_date - '2026-06-25'::DATE)::NUMERIC / 365.0 * 0.5
                   + 0.5 * COALESCE(
                         (b.next_coupon_date - '2026-06-25'::DATE)::NUMERIC / 365.0,
                         (b.maturity_date - '2026-06-25'::DATE)::NUMERIC / 365.0
                     )
                ELSE COALESCE(b.duration, b.remaining_days / 365.0)
            END
        , 4)                                                        AS duration,
        COALESCE(b.debt_rating, b.issuer_rating, 'NR')             AS rating,
        CASE WHEN b.maturity_date <= qe.qend THEN '是' ELSE '否' END AS is_current_quarter,
        -- 壓力偏離絕對值（供 ORDER BY 使用，不輸出）
        ABS(
            COALESCE(b.market_value,0)
            - COALESCE(b.market_value,0) * (1 - 0.005 *
                CASE WHEN COALESCE(b.coupon_type,'FIXED') = 'FLOAT'
                    THEN (b.maturity_date - '2026-06-25'::DATE)::NUMERIC / 365.0 * 0.5
                       + 0.5 * COALESCE(
                             (b.next_coupon_date - '2026-06-25'::DATE)::NUMERIC / 365.0,
                             (b.maturity_date - '2026-06-25'::DATE)::NUMERIC / 365.0
                         )
                    ELSE COALESCE(b.duration, b.remaining_days / 365.0, 0.0)
                END
            )
            - COALESCE(b.cost, 0)
        ) / 10000                                                   AS stressed_dev_abs
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    JOIN nav n ON n.port_id = b.port_id
    CROSS JOIN quarter_end qe
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND b.evaluate_date = '2026-06-25'::DATE
      AND b.quantity > 0
),

cds AS (
    SELECT
        p.port_name,
        'CD'                                                        AS bond_type,
        c.security_code,
        c.security_name,
        COALESCE(c.quantity, 0),
        COALESCE(c.cost, 0),
        COALESCE(c.market_value, 0),
        -- CD：成本全價 = 成本（無應計利息或已含）
        COALESCE(c.cost, 0) + COALESCE(c.accrued_interest, 0)      AS cost_dirty,
        ROUND(
            (COALESCE(c.market_value,0) - COALESCE(c.cost,0))
            / NULLIF(n.net_asset,0) * 10000
        , 6),
        ROUND(COALESCE(c.market_value,0) / NULLIF(n.net_asset,0) * 100, 6),
        ROUND((COALESCE(c.market_value,0) - COALESCE(c.cost,0)) / 10000, 4),
        c.maturity_date,
        'FI'                                                        AS coupon_type,  -- CD 為固定利率
        ROUND(COALESCE(c.duration, c.remaining_days / 365.0), 4),
        COALESCE(c.issuer_rating, 'NR'),
        CASE WHEN c.maturity_date <= qe.qend THEN '是' ELSE '否' END,
        -- 壓力偏離絕對值（供排序）
        ABS(COALESCE(c.market_value,0)
            * (1 - 0.005 * COALESCE(c.duration, c.remaining_days / 365.0, 0.0))
            - COALESCE(c.cost, 0)) / 10000
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    JOIN nav n ON n.port_id = c.port_id
    CROSS JOIN quarter_end qe
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND c.evaluate_date = '2026-06-25'::DATE
      AND c.maturity_date >= '2026-06-25'::DATE
),

deposits AS (
    SELECT
        p.port_name,
        'DEPOSIT'                                                   AS bond_type,
        d.deposit_id,
        d.deposit_name,
        0::NUMERIC,
        COALESCE(d.principal, 0),
        COALESCE(d.principal, 0),
        COALESCE(d.principal, 0),
        0::NUMERIC,
        ROUND(COALESCE(d.principal,0) / NULLIF(n.net_asset,0) * 100, 6),
        0::NUMERIC,
        d.maturity_date,
        '0'                                                         AS coupon_type,  -- 存款不重定價
        0::NUMERIC,
        COALESCE(d.bank_rating, 'NR'),
        CASE WHEN d.maturity_date <= qe.qend THEN '是' ELSE '否' END,
        0::NUMERIC                                                  AS stressed_dev_abs
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    JOIN nav n ON n.port_id = d.port_id
    CROSS JOIN quarter_end qe
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND d.evaluate_date = '2026-06-25'::DATE
      AND (d.maturity_date > '2026-06-25'::DATE OR d.maturity_date IS NULL)
)

SELECT
    port_name,
    bond_type,
    security_code,
    security_name,
    quantity,
    cost,
    clean_mv,
    cost_dirty,
    shadow_dev,
    pct_nav,
    dev_10k,
    maturity_date,
    coupon_type,
    duration,
    rating,
    is_current_quarter
FROM (
    SELECT * FROM bonds
    UNION ALL SELECT * FROM cds
    UNION ALL SELECT * FROM deposits
) t
ORDER BY
    port_name DESC,
    is_current_quarter,
    stressed_dev_abs DESC,                        -- 壓力偏離大的排前面
    CASE bond_type
        WHEN 'BOND_GOVT'  THEN 1
        WHEN 'BOND_CORP'  THEN 2
        WHEN 'BOND_FLOAT' THEN 3
        WHEN 'CD'         THEN 4
        WHEN 'DEPOSIT'    THEN 5
        ELSE 6
    END,
    quantity DESC,
    pct_nav DESC;
