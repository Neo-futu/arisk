-- ============================================================
-- 002_para.sql  參數主數據層  (prefix: para_)
-- FSI Financial Services Intelligence Platform
-- 涵蓋：機構 · 人員 · 組合/基金 · 份額類別
--        組合經理 · 基準定義 · 組合基準配置
--        資產配置限制 · 數據字典 · 證券代碼映射
-- 依賴：001_schema_init.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 機構主數據
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_institution (
    institution_id      VARCHAR(16)  PRIMARY KEY,
    institution_name    VARCHAR(200) NOT NULL,
    institution_name_en VARCHAR(200),
    short_name          VARCHAR(60),
    institution_type    VARCHAR(32)  NOT NULL,  -- ASSET_MGR/TRUSTEE/BROKER/BANK/COUNTERPARTY/SALES_CHANNEL
    country             CHAR(2),
    lei_code            VARCHAR(20),            -- 全球法人識別碼
    swift_code          VARCHAR(11),
    regulator_id        VARCHAR(64),            -- SFC/MAS/SEC 牌照號
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    extra_attrs         JSONB        NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_institution IS '機構主數據：資管公司、托管行、券商、交易對手等';
COMMENT ON COLUMN fsi.para_institution.lei_code IS 'Legal Entity Identifier，MiFID II/EMIR報告要求';

CREATE INDEX IF NOT EXISTS idx_para_inst_type    ON fsi.para_institution(institution_type);
CREATE INDEX IF NOT EXISTS idx_para_inst_country ON fsi.para_institution(country);

-- ────────────────────────────────────────────────────────────
-- 2. 人員主數據
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_person (
    person_id           VARCHAR(16)      PRIMARY KEY,
    person_name         VARCHAR(60)      NOT NULL,
    person_name_en      VARCHAR(120),
    email               VARCHAR(120),
    phone               VARCHAR(30),
    institution_id      VARCHAR(16),
    sfc_licence_no      VARCHAR(32),     -- SFC 持牌代表編號
    is_active           BOOLEAN          NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_person IS '人員主數據：基金經理、交易員、風控、合規等';
COMMENT ON COLUMN fsi.para_person.sfc_licence_no IS 'SFC 證監會持牌代表編號（香港監管要求）';

-- ────────────────────────────────────────────────────────────
-- 3. 組合/基金主數據
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_portfolio (
    port_id              VARCHAR(16)          PRIMARY KEY,
    port_name            VARCHAR(200)         NOT NULL,
    port_name_en         VARCHAR(200),
    port_type            fsi.portfolio_type   NOT NULL,
    base_currency        CHAR(3)              NOT NULL DEFAULT 'HKD',
    inception_date       DATE                 NOT NULL,
    close_date           DATE,
    is_active            BOOLEAN              NOT NULL DEFAULT TRUE,

    -- 監管/市場識別碼
    sfc_code             VARCHAR(64),         -- SFC 認可代號
    isin                 VARCHAR(12),
    lei_code             VARCHAR(20),
    bloomberg_id         VARCHAR(32),
    wind_code            VARCHAR(32),

    -- 費率（基點 bps，1bps = 0.01%）
    mgmt_fee_bps         NUMERIC(8,2),
    trustee_fee_bps      NUMERIC(8,2),
    admin_fee_bps        NUMERIC(8,2),
    perf_fee_pct         NUMERIC(6,4),
    perf_fee_hurdle_pct  NUMERIC(6,4),

    -- 認購門檻
    min_sub_amount       NUMERIC(24,4),
    min_holding_amount   NUMERIC(24,4),
    max_single_holder_pct NUMERIC(6,4),

    -- 機構關係
    asset_mgr_id         VARCHAR(16),
    trustee_id           VARCHAR(16),
    custodian_id         VARCHAR(16),

    -- 貨幣市場基金（MMF）SFC守則參數
    is_mmf               BOOLEAN      NOT NULL DEFAULT FALSE,
    mmf_wam_limit_days   INTEGER      DEFAULT 60,   -- 加權平均期限上限
    mmf_wal_limit_days   INTEGER      DEFAULT 120,  -- 加權平均有效期上限
    mmf_daily_liq_pct    NUMERIC(6,4) DEFAULT 7.5,  -- 每日流動資產下限（%）
    mmf_weekly_liq_pct   NUMERIC(6,4) DEFAULT 15.0, -- 每週流動資產下限（%）

    extra_attrs          JSONB        NOT NULL DEFAULT '{}',
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_portfolio IS '組合/基金主數據：統一管理公募、私募、委托、養老金各類投資組合';
COMMENT ON COLUMN fsi.para_portfolio.mmf_wam_limit_days IS 'SFC MMF守則：加權平均期限（WAM）≤60天';
COMMENT ON COLUMN fsi.para_portfolio.mmf_weekly_liq_pct IS 'SFC MMF守則：每週流動資產≥15%';

CREATE INDEX IF NOT EXISTS idx_para_port_type      ON fsi.para_portfolio(port_type);
CREATE INDEX IF NOT EXISTS idx_para_port_currency  ON fsi.para_portfolio(base_currency);
CREATE INDEX IF NOT EXISTS idx_para_port_mgr       ON fsi.para_portfolio(asset_mgr_id);
CREATE INDEX IF NOT EXISTS idx_para_port_active    ON fsi.para_portfolio(is_active) WHERE is_active;

-- ────────────────────────────────────────────────────────────
-- 4. 份額類別
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_share_class (
    class_id          VARCHAR(32)  PRIMARY KEY,
    port_id           VARCHAR(16)  NOT NULL,
    class_name        VARCHAR(60)  NOT NULL,        -- A/B/I/HKD/USD
    class_name_en     VARCHAR(120),
    currency          CHAR(3)      NOT NULL,
    isin              VARCHAR(12),
    bloomberg_id      VARCHAR(32),
    mgmt_fee_bps      NUMERIC(8,2),                 -- NULL = 繼承組合費率
    trustee_fee_bps   NUMERIC(8,2),
    perf_fee_pct      NUMERIC(6,4),
    min_subscription  NUMERIC(24,4),
    min_redemption    NUMERIC(24,4),
    dealing_frequency VARCHAR(20)  DEFAULT 'DAILY',
    distribution_type VARCHAR(16)  DEFAULT 'ACCUMULATING', -- ACCUMULATING/DISTRIBUTING
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    inception_date    DATE,
    close_date        DATE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_share_class IS '基金份額類別：同一基金多幣種/費率/認購門檻的份額';
COMMENT ON COLUMN fsi.para_share_class.distribution_type IS 'ACCUMULATING=累積型 / DISTRIBUTING=派息型';

CREATE INDEX IF NOT EXISTS idx_para_sc_port ON fsi.para_share_class(port_id);

-- ────────────────────────────────────────────────────────────
-- 5. 組合人員配置（基金經理歷史）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_portfolio_manager (
    port_id     VARCHAR(16)      NOT NULL,
    person_id   VARCHAR(16)      NOT NULL,
    role        fsi.person_role  NOT NULL,
    begin_date  DATE             NOT NULL,
    end_date    DATE,
    is_lead     BOOLEAN          NOT NULL DEFAULT FALSE,
    PRIMARY KEY (port_id, person_id, role, begin_date)
);
COMMENT ON TABLE  fsi.para_portfolio_manager IS '組合人員配置歷史：基金經理/風控任職記錄，支持績效歸因';
COMMENT ON COLUMN fsi.para_portfolio_manager.end_date IS 'NULL=仍在職';

CREATE INDEX IF NOT EXISTS idx_para_pm_port   ON fsi.para_portfolio_manager(port_id);
CREATE INDEX IF NOT EXISTS idx_para_pm_person ON fsi.para_portfolio_manager(person_id);
CREATE INDEX IF NOT EXISTS idx_para_pm_active ON fsi.para_portfolio_manager(port_id) WHERE end_date IS NULL;

-- ────────────────────────────────────────────────────────────
-- 6. 基準定義
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_benchmark_def (
    benchmark_id    VARCHAR(32)  PRIMARY KEY,
    benchmark_name  VARCHAR(200) NOT NULL,
    benchmark_name_en VARCHAR(200),
    benchmark_type  VARCHAR(32)  NOT NULL,  -- INDEX/RATE/COMPOSITE/CUSTOM
    currency        CHAR(3)      NOT NULL,
    source          VARCHAR(16)  NOT NULL,  -- WIND/BLOOMBERG/INTERNAL
    source_ticker   VARCHAR(64),
    plus_bps        NUMERIC(8,2) DEFAULT 0, -- 基準+利差（如HIBOR+50bps）
    description     TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_benchmark_def IS '基準定義：指數、利率基準、複合基準';
COMMENT ON COLUMN fsi.para_benchmark_def.plus_bps IS '相對利差：HIBOR ON+50bps則此列=50';

-- ────────────────────────────────────────────────────────────
-- 7. 組合基準配置（支持多基準、歷史切換）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_portfolio_benchmark (
    port_id        VARCHAR(16)  NOT NULL,
    benchmark_id   VARCHAR(32)  NOT NULL,
    begin_date     DATE         NOT NULL,
    end_date       DATE,
    weight_pct     NUMERIC(7,4) NOT NULL DEFAULT 100.0,
    benchmark_role VARCHAR(16)  NOT NULL DEFAULT 'PRIMARY', -- PRIMARY/SECONDARY/RISK
    PRIMARY KEY (port_id, benchmark_id, begin_date)
);
COMMENT ON TABLE fsi.para_portfolio_benchmark IS '組合基準配置歷史：支持複合基準（如60%股+40%債）';

CREATE INDEX IF NOT EXISTS idx_para_pb_port ON fsi.para_portfolio_benchmark(port_id);

-- ────────────────────────────────────────────────────────────
-- 8a. 監管風控限制（SFC / HKMA 法規要求）
--   來源：SFC MMF守則、SFC UT守則、HKMA指引等強制性規定
--   特點：不可更改（跟隨法規），違規必須強制觸發審核流程
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_risk_limit_regulatory (
    limit_id         BIGSERIAL    PRIMARY KEY,
    port_id          VARCHAR(16)  NOT NULL,
    regulation_src   VARCHAR(64)  NOT NULL,    -- SFC_MMF_CODE / SFC_UT_CODE / HKMA / SFC_FMC
    rule_code        VARCHAR(32)  NOT NULL,    -- 規則代碼，如 MMF_WAM / MMF_SINGLE_ISSUER
    rule_name        VARCHAR(200) NOT NULL,    -- 規則名稱（中文）
    rule_name_en     VARCHAR(200),
    dimension        VARCHAR(32)  NOT NULL,    -- ASSET_CLASS/ISSUER/ISSUER_GROUP/CURRENCY/MATURITY/WAM/WAL/LIQUIDITY
    dimension_key    VARCHAR(64),              -- 適用維度值（NULL=全組合）
    limit_value      NUMERIC(12,4) NOT NULL,   -- 限制數值
    limit_unit       VARCHAR(16)  NOT NULL,    -- PCT=百分比 / DAYS=天數 / ABS=絕對值
    limit_direction  VARCHAR(8)   NOT NULL,    -- MAX=上限 / MIN=下限
    clause_ref       VARCHAR(128),             -- 法規條款引用，如「MMF守則第X.X段」
    effective_date   DATE         NOT NULL,
    expiry_date      DATE,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_risk_limit_regulatory IS '監管風控限制：SFC/HKMA法規強制要求，違規必須走審核流程';
COMMENT ON COLUMN fsi.para_risk_limit_regulatory.rule_code IS '如 MMF_WAM=加權平均期限, MMF_SINGLE_ISSUER=單一發行人集中度';
COMMENT ON COLUMN fsi.para_risk_limit_regulatory.limit_unit IS 'PCT=百分比(%NAV) / DAYS=天數 / ABS=絕對金額';

CREATE INDEX IF NOT EXISTS idx_reg_limit_port    ON fsi.para_risk_limit_regulatory(port_id, is_active);
CREATE INDEX IF NOT EXISTS idx_reg_limit_rule    ON fsi.para_risk_limit_regulatory(rule_code);

-- ────────────────────────────────────────────────────────────
-- 8b. 內部風控限制（風控部門制定，比監管更嚴格）
--   來源：公司風控政策、投資委員會決議
--   特點：可調整，通常比監管限制更保守，有審批流程
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_risk_limit_internal (
    limit_id         BIGSERIAL    PRIMARY KEY,
    port_id          VARCHAR(16)  NOT NULL,
    limit_code       VARCHAR(32)  NOT NULL,    -- 內部風控代碼
    limit_name       VARCHAR(200) NOT NULL,
    limit_category   VARCHAR(32)  NOT NULL,    -- CONCENTRATION/LIQUIDITY/DURATION/VAR/DRAWDOWN/LEVERAGE
    dimension        VARCHAR(32)  NOT NULL,
    dimension_key    VARCHAR(64),
    lower_limit      NUMERIC(12,4),            -- 下限（如股票倉位≥0%）
    upper_limit      NUMERIC(12,4),            -- 上限（如股票倉位≤80%）
    limit_unit       VARCHAR(16)  NOT NULL DEFAULT 'PCT',
    alert_pct        NUMERIC(6,2) DEFAULT 90,  -- 達到限制X%時預警（如到90%就提示）
    is_hard          BOOLEAN      NOT NULL DEFAULT TRUE,  -- FALSE=軟限制僅預警
    approved_by      VARCHAR(64),              -- 審批人員ID
    approved_date    DATE,
    review_date      DATE,                     -- 下次審核日期
    begin_date       DATE         NOT NULL,
    end_date         DATE,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_risk_limit_internal IS '內部風控限制：風控部門制定，通常比監管要求更嚴格，有完整審批記錄';
COMMENT ON COLUMN fsi.para_risk_limit_internal.alert_pct IS '預警閾值：達到限制的X%時觸發預警（如90%則距上限10%時告警）';
COMMENT ON COLUMN fsi.para_risk_limit_internal.is_hard IS 'TRUE=硬限制（觸發審核阻塞），FALSE=軟限制（僅預警，允許繼續）';

CREATE INDEX IF NOT EXISTS idx_int_limit_port ON fsi.para_risk_limit_internal(port_id, is_active);
CREATE INDEX IF NOT EXISTS idx_int_limit_cat  ON fsi.para_risk_limit_internal(limit_category);

-- ────────────────────────────────────────────────────────────
-- 8c. 合同風控限制（投資委托書 / 基金章程中的約定限制）
--   來源：與客戶簽署的委托協議或基金章程
--   特點：具有法律效力，違反需書面通知客戶
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_risk_limit_contract (
    limit_id         BIGSERIAL    PRIMARY KEY,
    port_id          VARCHAR(16)  NOT NULL,
    mandate_ref      VARCHAR(64)  NOT NULL,    -- 委托協議/章程編號
    clause_ref       VARCHAR(64),              -- 協議條款引用
    client_name      VARCHAR(200),             -- 客戶名稱（適用委任管理）
    dimension        VARCHAR(32)  NOT NULL,
    dimension_key    VARCHAR(64),
    lower_limit      NUMERIC(12,4),
    upper_limit      NUMERIC(12,4),
    limit_unit       VARCHAR(16)  NOT NULL DEFAULT 'PCT',
    breach_action    VARCHAR(128),             -- 違規須採取的行動（如「5個工作日內書面通知客戶」）
    begin_date       DATE         NOT NULL,
    end_date         DATE,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_risk_limit_contract IS '合同風控限制：投資委托書/基金章程約定，具法律效力，違反須書面通知客戶';
COMMENT ON COLUMN fsi.para_risk_limit_contract.mandate_ref IS '委托協議或基金章程的唯一編號，對應法律文件';
COMMENT ON COLUMN fsi.para_risk_limit_contract.breach_action IS '合同規定的違規處置程序，如通知義務和整改時限';

CREATE INDEX IF NOT EXISTS idx_con_limit_port     ON fsi.para_risk_limit_contract(port_id, is_active);
CREATE INDEX IF NOT EXISTS idx_con_limit_mandate  ON fsi.para_risk_limit_contract(mandate_ref);

-- ────────────────────────────────────────────────────────────
-- 9. 數據字典
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_dict_category (
    category_id      VARCHAR(16)  PRIMARY KEY,
    category_name    VARCHAR(60)  NOT NULL,
    category_name_en VARCHAR(60),
    description      TEXT
);
COMMENT ON TABLE fsi.para_dict_category IS '數據字典類別：ASSET_TYPE/MARKET_ID/RATING/TRADE_TYPE等';

CREATE TABLE IF NOT EXISTS fsi.para_dict (
    category_id   VARCHAR(16)  NOT NULL,
    dict_key      VARCHAR(32)  NOT NULL,
    dict_value    VARCHAR(100) NOT NULL,
    dict_value_en VARCHAR(100),
    sort_order    INTEGER      DEFAULT 0,
    parent_key    VARCHAR(32),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    PRIMARY KEY (category_id, dict_key)
);
COMMENT ON TABLE  fsi.para_dict IS '數據字典明細：代碼中英文名稱，替代硬編碼';
COMMENT ON COLUMN fsi.para_dict.parent_key IS '父級代碼，支持資產類別一/二級樹形結構';

-- ────────────────────────────────────────────────────────────
-- 10. 證券代碼映射（跨數據源統一）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_security_code_map (
    internal_id    VARCHAR(32)  NOT NULL,
    source         VARCHAR(16)  NOT NULL,  -- WIND/BLOOMBERG/ISIN/HKEX/SSE/SZSE
    source_code    VARCHAR(64)  NOT NULL,
    effective_date DATE         NOT NULL DEFAULT '1900-01-01',
    expiry_date    DATE                  DEFAULT '9999-12-31',
    PRIMARY KEY (internal_id, source, effective_date)
);
COMMENT ON TABLE fsi.para_security_code_map IS '證券代碼映射：Wind/Bloomberg/ISIN/交易所代碼互轉';

CREATE INDEX IF NOT EXISTS idx_para_scm_source ON fsi.para_security_code_map(source, source_code);
CREATE INDEX IF NOT EXISTS idx_para_scm_id     ON fsi.para_security_code_map(internal_id);
