-- ============================================================
-- 019_am_category_tables.sql
-- 按资管数据类别拆表，不再把下列属性挂在行情/持仓/机构主表上：
--   固收信用定价、证券停牌、债券投资者保护条款、权益风格、发行人主体。
-- ============================================================

-- 1. 固收信用定价（隐含违约率 / 隐含评级 / 信用利差）
CREATE TABLE IF NOT EXISTS fsi.mktdata_fi_credit (
    price_date       DATE          NOT NULL,
    security_code    VARCHAR(32)   NOT NULL,
    implied_pd       NUMERIC(12,8),
    implied_rating   VARCHAR(8),
    credit_spread    NUMERIC(12,8),
    data_source      VARCHAR(16)   NOT NULL DEFAULT 'INTERNAL',
    loaded_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (price_date, security_code)
);
COMMENT ON TABLE fsi.mktdata_fi_credit IS '固收信用定价：隐含违约率、隐含评级、信用利差';
COMMENT ON COLUMN fsi.mktdata_fi_credit.implied_pd IS '隐含违约率，小数';
COMMENT ON COLUMN fsi.mktdata_fi_credit.credit_spread IS '信用利差，小数';

CREATE INDEX IF NOT EXISTS idx_fi_credit_sec ON fsi.mktdata_fi_credit(security_code, price_date DESC);

-- 2. 证券停牌
CREATE TABLE IF NOT EXISTS fsi.mktdata_security_halt (
    security_code  VARCHAR(32)  NOT NULL,
    asset_class    VARCHAR(16)  NOT NULL,   -- EQUITY / BOND
    halt_date      DATE         NOT NULL,
    is_halted      BOOLEAN      NOT NULL DEFAULT TRUE,
    resume_date    DATE,
    halt_reason    VARCHAR(200),
    data_source    VARCHAR(16)  NOT NULL DEFAULT 'INTERNAL',
    loaded_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (security_code, asset_class, halt_date)
);
COMMENT ON TABLE fsi.mktdata_security_halt IS '证券停牌：股票与债券分开记录停牌区间';

CREATE INDEX IF NOT EXISTS idx_security_halt_date ON fsi.mktdata_security_halt(halt_date DESC, asset_class);

-- 3. 债券投资者保护条款
CREATE TABLE IF NOT EXISTS fsi.mktdata_bond_covenant (
    security_code   VARCHAR(32)  NOT NULL,
    clause_code     VARCHAR(32)  NOT NULL,
    effective_date  DATE         NOT NULL,
    clause_name     VARCHAR(200) NOT NULL,
    triggered       BOOLEAN      NOT NULL DEFAULT FALSE,
    trigger_date    DATE,
    data_source     VARCHAR(16)  NOT NULL DEFAULT 'INTERNAL',
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (security_code, clause_code, effective_date)
);
COMMENT ON TABLE fsi.mktdata_bond_covenant IS '债券特殊条款：投资者保护条款及是否触发';

-- 4. 权益风格（大盘/小盘，成长/价值）
CREATE TABLE IF NOT EXISTS fsi.mktdata_equity_style (
    as_of_date     DATE         NOT NULL,
    security_code  VARCHAR(32)  NOT NULL,
    size_bucket    VARCHAR(16)  NOT NULL,   -- LARGE / MID / SMALL
    style_bucket   VARCHAR(16)  NOT NULL,   -- GROWTH / VALUE / BLEND
    data_source    VARCHAR(16)  NOT NULL DEFAULT 'INTERNAL',
    loaded_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, security_code)
);
COMMENT ON TABLE fsi.mktdata_equity_style IS '权益风格分类：规模（大盘/中盘/小盘）与价值成长';

CREATE INDEX IF NOT EXISTS idx_equity_style_sec ON fsi.mktdata_equity_style(security_code, as_of_date DESC);

-- 5. 发行人主体（净资产、存续信用债、实际控制人）
CREATE TABLE IF NOT EXISTS fsi.mktdata_issuer_profile (
    as_of_date                DATE         NOT NULL,
    issuer_id                 VARCHAR(16)  NOT NULL,
    net_assets                NUMERIC(24,2),
    outstanding_credit_bond   NUMERIC(24,2),
    actual_controller_id      VARCHAR(16),
    actual_controller_name    VARCHAR(200),
    data_source               VARCHAR(16)  NOT NULL DEFAULT 'INTERNAL',
    loaded_at                 TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, issuer_id)
);
COMMENT ON TABLE fsi.mktdata_issuer_profile IS '发行人主体：净资产、存续信用债余额、实际控制人';

CREATE INDEX IF NOT EXISTS idx_issuer_profile_ctrl ON fsi.mktdata_issuer_profile(actual_controller_id);

-- ────────────────────────────────────────────────────────────
-- 从曾挂在主表上的列迁出（列已删除时跳过）
-- ────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsi' AND table_name = 'balance_bond' AND column_name = 'implied_pd'
    ) THEN
        EXECUTE $sql$
            INSERT INTO fsi.mktdata_fi_credit (price_date, security_code, implied_pd, implied_rating, credit_spread)
            SELECT evaluate_date, security_code,
                   MAX(implied_pd), MAX(implied_rating), NULL
            FROM fsi.balance_bond
            WHERE implied_pd IS NOT NULL OR implied_rating IS NOT NULL
            GROUP BY evaluate_date, security_code
            ON CONFLICT (price_date, security_code) DO UPDATE
                SET implied_pd = COALESCE(fsi.mktdata_fi_credit.implied_pd, EXCLUDED.implied_pd),
                    implied_rating = COALESCE(fsi.mktdata_fi_credit.implied_rating, EXCLUDED.implied_rating)
        $sql$;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsi' AND table_name = 'balance_bond' AND column_name = 'is_suspended'
    ) THEN
        EXECUTE $sql$
            INSERT INTO fsi.mktdata_security_halt (security_code, asset_class, halt_date, is_halted, halt_reason)
            SELECT security_code, 'BOND', evaluate_date, TRUE, '自持仓标记迁入'
            FROM fsi.balance_bond
            WHERE is_suspended
            GROUP BY security_code, evaluate_date
            ON CONFLICT (security_code, asset_class, halt_date) DO NOTHING
        $sql$;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsi' AND table_name = 'balance_stock' AND column_name = 'is_suspended'
    ) THEN
        EXECUTE $sql$
            INSERT INTO fsi.mktdata_security_halt (security_code, asset_class, halt_date, is_halted, halt_reason)
            SELECT security_code, 'EQUITY', evaluate_date, TRUE, '自持仓标记迁入'
            FROM fsi.balance_stock
            WHERE is_suspended
            GROUP BY security_code, evaluate_date
            ON CONFLICT (security_code, asset_class, halt_date) DO NOTHING
        $sql$;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsi' AND table_name = 'balance_bond' AND column_name = 'protection_triggered'
    ) THEN
        EXECUTE $sql$
            INSERT INTO fsi.mktdata_bond_covenant (
                security_code, clause_code, effective_date, clause_name, triggered, trigger_date
            )
            SELECT security_code, 'INVESTOR_PROTECTION', evaluate_date, '投资者保护条款', TRUE, evaluate_date
            FROM fsi.balance_bond
            WHERE protection_triggered
            GROUP BY security_code, evaluate_date
            ON CONFLICT (security_code, clause_code, effective_date) DO NOTHING
        $sql$;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsi' AND table_name = 'mktdata_stock_static' AND column_name = 'style_size'
    ) THEN
        EXECUTE $sql$
            INSERT INTO fsi.mktdata_equity_style (as_of_date, security_code, size_bucket, style_bucket)
            SELECT DATE '2026-06-25', security_code,
                   COALESCE(style_size, 'LARGE'), COALESCE(style_value, 'BLEND')
            FROM fsi.mktdata_stock_static
            WHERE style_size IS NOT NULL OR style_value IS NOT NULL
            ON CONFLICT (as_of_date, security_code) DO UPDATE
                SET size_bucket = EXCLUDED.size_bucket,
                    style_bucket = EXCLUDED.style_bucket
        $sql$;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fsi' AND table_name = 'para_institution' AND column_name = 'net_assets'
    ) THEN
        EXECUTE $sql$
            INSERT INTO fsi.mktdata_issuer_profile (
                as_of_date, issuer_id, net_assets, outstanding_credit_bond, actual_controller_id
            )
            SELECT DATE '2026-06-25', institution_id, net_assets, outstanding_credit_bond, actual_controller_id
            FROM fsi.para_institution
            WHERE net_assets IS NOT NULL
               OR outstanding_credit_bond IS NOT NULL
               OR actual_controller_id IS NOT NULL
            ON CONFLICT (as_of_date, issuer_id) DO UPDATE
                SET net_assets = COALESCE(fsi.mktdata_issuer_profile.net_assets, EXCLUDED.net_assets),
                    outstanding_credit_bond = COALESCE(fsi.mktdata_issuer_profile.outstanding_credit_bond, EXCLUDED.outstanding_credit_bond),
                    actual_controller_id = COALESCE(fsi.mktdata_issuer_profile.actual_controller_id, EXCLUDED.actual_controller_id)
        $sql$;
    END IF;
END $$;

-- 类别表示例（已有记录不覆盖）
INSERT INTO fsi.mktdata_fi_credit (price_date, security_code, implied_pd, implied_rating, credit_spread)
SELECT b.evaluate_date, b.security_code, 0.0035, COALESCE(b.debt_rating, b.issuer_rating, 'AA'), 0.0080
FROM fsi.balance_bond b
WHERE b.evaluate_date = DATE '2026-06-25'
ON CONFLICT (price_date, security_code) DO UPDATE
    SET implied_pd = COALESCE(fsi.mktdata_fi_credit.implied_pd, EXCLUDED.implied_pd),
        implied_rating = COALESCE(fsi.mktdata_fi_credit.implied_rating, EXCLUDED.implied_rating),
        credit_spread = COALESCE(fsi.mktdata_fi_credit.credit_spread, EXCLUDED.credit_spread);

INSERT INTO fsi.mktdata_equity_style (as_of_date, security_code, size_bucket, style_bucket)
VALUES
    (DATE '2026-06-25', '0700.HK', 'LARGE', 'GROWTH'),
    (DATE '2026-06-25', '9988.HK', 'LARGE', 'GROWTH')
ON CONFLICT (as_of_date, security_code) DO NOTHING;

INSERT INTO fsi.mktdata_issuer_profile (
    as_of_date, issuer_id, net_assets, outstanding_credit_bond, actual_controller_id, actual_controller_name
) VALUES
    (DATE '2026-06-25', 'BOCHK', 280000000000, 45000000000, 'BOC_GROUP', '中银集团'),
    (DATE '2026-06-25', 'HSBC',  520000000000, 80000000000, 'HSBC_GROUP', '汇丰集团'),
    (DATE '2026-06-25', 'SCB',   190000000000, 30000000000, 'SCB_GROUP', '渣打集团')
ON CONFLICT (as_of_date, issuer_id) DO NOTHING;

-- 从主表去掉已迁出的列
ALTER TABLE fsi.mktdata_bond_risk
    DROP COLUMN IF EXISTS implied_pd,
    DROP COLUMN IF EXISTS implied_rating,
    DROP COLUMN IF EXISTS credit_spread;

ALTER TABLE fsi.mktdata_bond_static
    DROP COLUMN IF EXISTS is_suspended,
    DROP COLUMN IF EXISTS protection_triggered,
    DROP COLUMN IF EXISTS actual_controller_id;

ALTER TABLE fsi.mktdata_stock_static
    DROP COLUMN IF EXISTS style_size,
    DROP COLUMN IF EXISTS style_value,
    DROP COLUMN IF EXISTS is_suspended;

ALTER TABLE fsi.balance_bond
    DROP COLUMN IF EXISTS implied_pd,
    DROP COLUMN IF EXISTS implied_rating,
    DROP COLUMN IF EXISTS is_suspended,
    DROP COLUMN IF EXISTS protection_triggered,
    DROP COLUMN IF EXISTS actual_controller_id;

ALTER TABLE fsi.balance_stock
    DROP COLUMN IF EXISTS is_suspended;

ALTER TABLE fsi.para_institution
    DROP COLUMN IF EXISTS net_assets,
    DROP COLUMN IF EXISTS outstanding_credit_bond,
    DROP COLUMN IF EXISTS actual_controller_id;
