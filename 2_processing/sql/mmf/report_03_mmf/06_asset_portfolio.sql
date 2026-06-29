-- ============================================================
-- 報表03 / 06_asset_portfolio.sql
-- 原始：SmartReport/03/06.sql  資產配置細則
-- Sheet：日报-sql导入数据，標籤06.sql@A42，表頭A43，數據A44
--
-- 欄位說明（對照模版表頭，共15列）：
--   组合 净资产 现金 债券 债券利息 存款 存款利息 存单 逆回购 正回购
--   利率债 浮息债 信用债 存款提支罚息 存款提支不罚息
--
-- 前10列來自 balance_portfolio_asset（彙總層，對應 T_Balance_Portfolio_Asset）
-- 後5列來自明細持倉表（bond/deposit），用 Cost/Principal（成本）
--
-- ★ 修改 evaluate_date 即可獨立運行
-- ============================================================

WITH base AS (
    -- 從資產配置彙總表取各類別市值和應計收益（對應 T_Balance_Portfolio_Asset）
    SELECT
        a.port_id,
        -- 現金
        SUM(CASE WHEN a.asset_class = 'CASH'
                 THEN COALESCE(a.market_value, 0) ELSE 0 END) / 100000000     AS cash,
        -- 債券市值合計（利率債+信用債+CD+CP+ABS）
        SUM(CASE WHEN a.asset_class IN ('BOND_GOVT','BOND_CORP','BOND_ABS',
                                        'CP','BOND_CONVERT')
                 THEN COALESCE(a.market_value, 0) ELSE 0 END) / 100000000     AS bond,
        -- 債券應計利息
        SUM(CASE WHEN a.asset_class IN ('BOND_GOVT','BOND_CORP','BOND_ABS',
                                        'CP','BOND_CONVERT')
                 THEN COALESCE(a.accrued_income, 0) ELSE 0 END) / 100000000  AS bond_interest,
        -- 存款市值
        SUM(CASE WHEN a.asset_class = 'DEPOSIT'
                 THEN COALESCE(a.market_value, 0) ELSE 0 END) / 100000000     AS deposit,
        -- 存款應計利息
        SUM(CASE WHEN a.asset_class = 'DEPOSIT'
                 THEN COALESCE(a.accrued_income, 0) ELSE 0 END) / 100000000  AS deposit_interest,
        -- 存款證
        SUM(CASE WHEN a.asset_class = 'CD'
                 THEN COALESCE(a.market_value, 0) ELSE 0 END) / 100000000     AS cd,
        -- 逆回購（融出）
        SUM(CASE WHEN a.asset_class = 'REV_REPO'
                 THEN COALESCE(a.market_value, 0) ELSE 0 END) / 100000000     AS rev_repo,
        -- 正回購（融入）
        SUM(CASE WHEN a.asset_class = 'REPO'
                 THEN COALESCE(a.market_value, 0) ELSE 0 END) / 100000000     AS repo
    FROM fsi.balance_portfolio_asset a
    JOIN fsi.para_portfolio p ON p.port_id = a.port_id
    WHERE p.is_mmf = TRUE AND p.is_active = TRUE
      AND a.evaluate_date = '2026-06-25'::DATE
    GROUP BY a.port_id
),

-- 利率債（對應 ItemTypeIdLevel2 IN '004001','004006'）
irbond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost, 0)) / 100000000 AS interest_rate_bond
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype = 'BOND_GOVT'
    GROUP BY b.port_id
),

-- 浮息債（利率債中 CouponType='FL'）
flbond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost, 0)) / 100000000 AS fl_bond
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype = 'BOND_GOVT'
      AND b.coupon_type = 'FLOAT'
    GROUP BY b.port_id
),

-- 信用債（非利率債）
creditbond AS (
    SELECT b.port_id,
           SUM(COALESCE(b.cost, 0)) / 100000000 AS credit_bond
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE p.is_mmf = TRUE AND b.evaluate_date = '2026-06-25'::DATE
      AND b.asset_subtype != 'BOND_GOVT'
    GROUP BY b.port_id
),

-- 存款：罰息 vs 不罰息（對應 IsInterestPenalty='Y'/'N'）
dep_detail AS (
    SELECT d.port_id,
           SUM(CASE WHEN d.is_penalty_on_early_redeem = TRUE
                    THEN COALESCE(d.principal, 0) ELSE 0 END) / 100000000 AS deposit_y,
           SUM(CASE WHEN d.is_penalty_on_early_redeem = FALSE
                        OR d.is_penalty_on_early_redeem IS NULL
                    THEN COALESCE(d.principal, 0) ELSE 0 END) / 100000000 AS deposit_n
    FROM fsi.balance_deposit d
    JOIN fsi.para_portfolio p ON p.port_id = d.port_id
    WHERE p.is_mmf = TRUE AND d.evaluate_date = '2026-06-25'::DATE
    GROUP BY d.port_id
)

SELECT
    p.port_name,
    ROUND(n.net_asset / 100000000, 4)           AS net_asset,       -- 净资产（亿）
    ROUND(COALESCE(b.cash, 0), 4)               AS cash,            -- 现金
    ROUND(COALESCE(b.bond, 0), 4)               AS bond,            -- 债券
    ROUND(COALESCE(b.bond_interest, 0), 4)      AS bond_interest,   -- 债券利息
    ROUND(COALESCE(b.deposit, 0), 4)            AS deposit,         -- 存款
    ROUND(COALESCE(b.deposit_interest, 0), 4)   AS deposit_interest,-- 存款利息
    ROUND(COALESCE(b.cd, 0), 4)                 AS cd,              -- 存单
    ROUND(COALESCE(b.rev_repo, 0), 4)           AS rev_repo,        -- 逆回购
    ROUND(COALESCE(b.repo, 0), 4)               AS repo,            -- 正回购
    ROUND(COALESCE(i.interest_rate_bond, 0), 4) AS interest_rate_bond, -- 利率债
    ROUND(COALESCE(f.fl_bond, 0), 4)            AS fl_bond,         -- 浮息债
    ROUND(COALESCE(c.credit_bond, 0), 4)        AS credit_bond,     -- 信用债
    ROUND(COALESCE(d.deposit_y, 0), 4)          AS deposit_y,       -- 存款提支罚息
    ROUND(COALESCE(d.deposit_n, 0), 4)          AS deposit_n        -- 存款提支不罚息
FROM fsi.para_portfolio p
JOIN fsi.balance_portfolio_nav n ON n.port_id = p.port_id
    AND n.evaluate_date = '2026-06-25'::DATE AND n.class_id IS NULL
LEFT JOIN base       b ON b.port_id = p.port_id
LEFT JOIN irbond     i ON i.port_id = p.port_id
LEFT JOIN flbond     f ON f.port_id = p.port_id
LEFT JOIN creditbond c ON c.port_id = p.port_id
LEFT JOIN dep_detail d ON d.port_id = p.port_id
WHERE p.is_mmf = TRUE AND p.is_active = TRUE
ORDER BY p.port_name;
