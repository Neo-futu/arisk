-- ============================================================
-- 003_balance.sql  持倉數據層  (prefix: balance_)
-- FSI Financial Services Intelligence Platform
-- 涵蓋：組合NAV · 資產配置匯總 · 現金 · 存款 · 存款證
--        債券 · 股票 · 基金 · 期貨 · 期權 · 回購 · 持有人
-- 依賴：001_schema_init.sql · 002_para.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1a. 組合淨值日快照（通用）
--   對應 T_Balance_Portfolio：所有基金類型通用
--   週/月/YTD/成立以來收益率 → 由 2_processing 計算後存入 svc_risk_perf
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_portfolio_nav (
    evaluate_date      DATE          NOT NULL,
    port_id            VARCHAR(16)   NOT NULL,
    currency           CHAR(3)       NOT NULL,
    total_asset        NUMERIC(24,2),
    total_liability    NUMERIC(24,2),
    net_asset          NUMERIC(24,2) NOT NULL,
    shares_outstanding NUMERIC(24,6),
    unit_nav           NUMERIC(16,8),
    acc_unit_nav       NUMERIC(16,8),   -- 累計單位淨值（含歷史分紅）；T_Balance_Portfolio.AccUnitNetAsset
    day_return         NUMERIC(16,10),  -- 當日收益率，估值系統直接提供；T_Balance_Portfolio.DayReturn
    class_id           VARCHAR(32),     -- 份額類別；T_Balance_Portfolio_FundShare.FundCode，NULL=組合整體
    loaded_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, currency)
);
COMMENT ON TABLE fsi.balance_portfolio_nav IS
    '組合淨值日快照（通用）：所有基金類型，對應 T_Balance_Portfolio。
     貨基專有指標（每萬份/7日年化/偏差/WAM/WAL）在 balance_portfolio_mmf。
     多期業績（週/月/YTD/SI）在 svc_risk_perf。';

CREATE INDEX IF NOT EXISTS idx_bal_nav_port_date ON fsi.balance_portfolio_nav(port_id, evaluate_date DESC);

-- ────────────────────────────────────────────────────────────
-- 1b. 貨幣市場基金每日專有指標
--   對應 T_Balance_Portfolio_MMF：僅 MMF 基金有此表數據
--   來源：估值系統每日計算後推送（Wind AMS / 托管行接口）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_portfolio_mmf (
    evaluate_date        DATE          NOT NULL,
    port_id              VARCHAR(16)   NOT NULL,
    income_per_10k       NUMERIC(12,4),  -- 每萬份收益（元）；T_Balance_Portfolio_MMF.Income10KShare
    return_rate_7d       NUMERIC(11,3),  -- 7日年化收益率（%）；ReturnRate7D
    nav_deviation        NUMERIC(6,2),   -- 影子定價偏差（%）；Deviation；SFC要求>0.5%須採取行動
    nav_deviation_amount NUMERIC(24,2),  -- 影子定價偏差金額（元）；DeviationAmount
    wam_days             INTEGER,        -- 加權平均剩餘期限（天）；AverageRemainingMaturity；SFC守則≤60天
    wal_days             INTEGER,        -- 加權平均剩餘存續期（天）；AverageRemainingPeriod；SFC守則≤120天
    loaded_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id)
);
COMMENT ON TABLE fsi.balance_portfolio_mmf IS
    '貨幣市場基金每日專有指標，對應 T_Balance_Portfolio_MMF。
     股票/債券/混合基金無此表數據。
     來源：估值系統（Wind AMS）每日計算後推送。';
COMMENT ON COLUMN fsi.balance_portfolio_mmf.nav_deviation        IS '影子定價偏差%：市價法NAV - 攤余成本法NAV，SFC超0.5%需採取行動';
COMMENT ON COLUMN fsi.balance_portfolio_mmf.wam_days             IS 'WAM：加權平均剩餘期限，浮息債用下次重定價日，SFC MMF守則≤60天';
COMMENT ON COLUMN fsi.balance_portfolio_mmf.wal_days             IS 'WAL：加權平均剩餘存續期，全部用最終到期日，SFC MMF守則≤120天';

CREATE INDEX IF NOT EXISTS idx_bal_mmf_port_date ON fsi.balance_portfolio_mmf(port_id, evaluate_date DESC);

-- ────────────────────────────────────────────────────────────
-- 2. 資產配置匯總（按類別）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_portfolio_asset (
    evaluate_date     DATE             NOT NULL,
    port_id           VARCHAR(16)      NOT NULL,
    asset_class       fsi.asset_class  NOT NULL,
    market_value      NUMERIC(24,2)    NOT NULL DEFAULT 0,
    market_value_base NUMERIC(24,2),              -- 換算基幣
    accrued_income    NUMERIC(24,2)    DEFAULT 0,
    weight_pct        NUMERIC(10,6),              -- 佔NAV比例（%）
    loaded_at         TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, asset_class)
);
COMMENT ON TABLE fsi.balance_portfolio_asset IS '資產配置匯總：按資產類別匯總市值，暴露分析和限制檢查用';

-- ────────────────────────────────────────────────────────────
-- 3. 現金持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_cash (
    evaluate_date   DATE         NOT NULL,
    port_id         VARCHAR(16)  NOT NULL,
    cash_account_id VARCHAR(32)  NOT NULL,
    account_name    VARCHAR(120),
    bank_id         VARCHAR(16),
    currency        CHAR(3)      NOT NULL,
    amount          NUMERIC(24,2) NOT NULL,
    amount_base_ccy NUMERIC(24,2),
    fx_rate         NUMERIC(16,8),
    weight_pct      NUMERIC(10,6),
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, cash_account_id)
);
COMMENT ON TABLE fsi.balance_cash IS '現金及活期存款持倉：按賬戶、幣種明細記錄';

CREATE INDEX IF NOT EXISTS idx_bal_cash_port_date ON fsi.balance_cash(port_id, evaluate_date DESC);

-- ────────────────────────────────────────────────────────────
-- 4. 定期存款持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_deposit (
    evaluate_date     DATE                NOT NULL,
    port_id           VARCHAR(16)         NOT NULL,
    deposit_id        VARCHAR(48)         NOT NULL,
    deposit_name      VARCHAR(120),
    bank_id           VARCHAR(16),
    bank_name         VARCHAR(200),
    bank_group        VARCHAR(200),                    -- 集團名（集中度計算）
    bank_rating       VARCHAR(8),
    rating_agency     fsi.rating_agency   DEFAULT 'NR',
    currency          CHAR(3)             NOT NULL,
    value_date        DATE                NOT NULL,
    maturity_date     DATE                NOT NULL,
    remaining_days    INTEGER GENERATED ALWAYS AS (maturity_date - evaluate_date) STORED,
    principal         NUMERIC(24,2)       NOT NULL,
    interest_rate     NUMERIC(12,8)       NOT NULL,
    accrued_interest  NUMERIC(24,2),
    total_value       NUMERIC(24,2),
    total_value_base  NUMERIC(24,2),
    fx_rate           NUMERIC(16,8),
    weight_pct        NUMERIC(10,6),
    is_overnight      BOOLEAN             NOT NULL DEFAULT FALSE,
    bank_branch_name  VARCHAR(200),                -- 銀行支行名稱；T_Balance_Deposit.BankBranchName
    loaded_at         TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, deposit_id)
);
COMMENT ON TABLE  fsi.balance_deposit IS '定期存款持倉：銀行定存明細，流動性分析和信用集中度計算';
COMMENT ON COLUMN fsi.balance_deposit.bank_group IS '銀行集團名，計算集團敞口（如「工銀集團」含各子公司）';
COMMENT ON COLUMN fsi.balance_deposit.is_overnight IS 'True計入MMF每日流動資產（SFC守則≥7.5%）';
COMMENT ON COLUMN fsi.balance_deposit.remaining_days IS '剩餘天數，資料庫自動計算';

CREATE INDEX IF NOT EXISTS idx_bal_dep_port_date ON fsi.balance_deposit(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_bal_dep_maturity  ON fsi.balance_deposit(maturity_date);
CREATE INDEX IF NOT EXISTS idx_bal_dep_bank      ON fsi.balance_deposit(bank_id);

-- ────────────────────────────────────────────────────────────
-- 5. 存款證（CD）持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_cd (
    evaluate_date    DATE               NOT NULL,
    port_id          VARCHAR(16)        NOT NULL,
    security_code    VARCHAR(32)        NOT NULL,
    security_name    VARCHAR(120),
    issuer_id        VARCHAR(16),
    issuer_name      VARCHAR(200),
    issuer_group     VARCHAR(200),
    issuer_rating    VARCHAR(8),
    rating_agency    fsi.rating_agency  DEFAULT 'NR',
    currency         CHAR(3)            NOT NULL,
    issue_amount     NUMERIC(24,2),
    value_date       DATE,
    maturity_date    DATE,
    remaining_days   INTEGER GENERATED ALWAYS AS (maturity_date - evaluate_date) STORED,
    quantity         NUMERIC(20,4)      NOT NULL,
    cost             NUMERIC(24,2),
    unit_cost        NUMERIC(24,8),
    price            NUMERIC(24,8),
    principal        NUMERIC(24,2),
    accrued_interest NUMERIC(24,2),
    market_value     NUMERIC(24,2),
    market_value_base NUMERIC(24,2),
    fx_rate          NUMERIC(16,8),
    coupon_rate      NUMERIC(12,8),
    ytm              NUMERIC(14,10),
    duration         NUMERIC(12,8),
    convexity        NUMERIC(12,8),
    weight_pct       NUMERIC(10,6),
    loaded_at        TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, security_code)
);
COMMENT ON TABLE fsi.balance_cd IS '存款證（Certificate of Deposit）持倉：香港貨幣市場重要工具';

CREATE INDEX IF NOT EXISTS idx_bal_cd_port_date ON fsi.balance_cd(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_bal_cd_issuer    ON fsi.balance_cd(issuer_id);
CREATE INDEX IF NOT EXISTS idx_bal_cd_maturity  ON fsi.balance_cd(maturity_date);

-- ────────────────────────────────────────────────────────────
-- 6. 債券持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_bond (
    evaluate_date       DATE               NOT NULL,
    port_id             VARCHAR(16)        NOT NULL,
    security_code       VARCHAR(32)        NOT NULL,
    isin                VARCHAR(12),
    security_name       VARCHAR(200),
    market_id           VARCHAR(16),                -- HKEX/IB/SSE/SZSE/OTC
    asset_subtype       fsi.asset_class    NOT NULL DEFAULT 'BOND_CORP',
    issuer_id           VARCHAR(16),
    issuer_name         VARCHAR(200),
    issuer_group        VARCHAR(200),
    country             CHAR(2),
    sector              VARCHAR(64),
    currency            CHAR(3)            NOT NULL,
    fx_rate             NUMERIC(16,8),
    issue_amount        NUMERIC(24,2),
    outstanding_amount  NUMERIC(24,2),
    issue_date          DATE,
    value_date          DATE,
    maturity_date       DATE,
    remaining_days      INTEGER GENERATED ALWAYS AS (maturity_date - evaluate_date) STORED,
    coupon_type         VARCHAR(16),                -- FIXED/FLOAT/ZERO/STEP
    coupon_rate         NUMERIC(12,8),
    next_coupon_date    DATE,
    next_coupon_rate    NUMERIC(12,8),
    coupon_frequency    INTEGER,
    quantity            NUMERIC(20,4)      NOT NULL,
    cost                NUMERIC(24,2),
    unit_cost           NUMERIC(24,8),
    principal           NUMERIC(24,2),
    accrued_interest    NUMERIC(24,2),
    clean_price         NUMERIC(24,8),              -- 淨價
    dirty_price         NUMERIC(24,8),              -- 全價
    market_value        NUMERIC(24,2)      NOT NULL,
    market_value_base   NUMERIC(24,2),
    total_market_value  NUMERIC(24,2),              -- 市值+應計利息
    ytm                 NUMERIC(14,10),
    duration            NUMERIC(12,8),              -- 修正久期（年）
    convexity           NUMERIC(12,8),
    dv01                NUMERIC(16,6),              -- 每基點美元值（本幣）
    dv01_base           NUMERIC(16,6),              -- DV01折算基幣
    issuer_rating       VARCHAR(8),
    debt_rating         VARCHAR(8),
    internal_rating     VARCHAR(8),
    rating_agency       fsi.rating_agency  DEFAULT 'NR',
    weight_pct          NUMERIC(10,6),
    investment_strategy VARCHAR(32),
    loaded_at           TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, security_code)
);
COMMENT ON TABLE  fsi.balance_bond IS '債券持倉：含完整利率風險指標，支持WAM/WAL/DV01計算';
COMMENT ON COLUMN fsi.balance_bond.dv01 IS 'Dollar Value of 1bp：利率上升1bp時市值變動，利率風險核心指標';
COMMENT ON COLUMN fsi.balance_bond.remaining_days IS '剩餘天數自動計算，用於WAM加權平均期限分析';

CREATE INDEX IF NOT EXISTS idx_bal_bond_port_date ON fsi.balance_bond(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_bal_bond_issuer    ON fsi.balance_bond(issuer_id);
CREATE INDEX IF NOT EXISTS idx_bal_bond_maturity  ON fsi.balance_bond(maturity_date);
CREATE INDEX IF NOT EXISTS idx_bal_bond_isin      ON fsi.balance_bond(isin) WHERE isin IS NOT NULL;

-- ────────────────────────────────────────────────────────────
-- 7. 股票持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_stock (
    evaluate_date     DATE         NOT NULL,
    port_id           VARCHAR(16)  NOT NULL,
    security_code     VARCHAR(32)  NOT NULL,
    isin              VARCHAR(12),
    security_name     VARCHAR(200),
    market_id         VARCHAR(16)  NOT NULL,       -- HKEX/NYSE/LSE/SSE/SZSE
    country           CHAR(2),
    sector            VARCHAR(64),
    currency          CHAR(3)      NOT NULL,
    fx_rate           NUMERIC(16,8),
    quantity          NUMERIC(20,4) NOT NULL,
    cost              NUMERIC(24,2),
    unit_cost         NUMERIC(24,8),
    price             NUMERIC(24,8),
    market_value      NUMERIC(24,2) NOT NULL,
    market_value_base NUMERIC(24,2),
    unrealized_pnl    NUMERIC(24,2),
    is_sellable       BOOLEAN       DEFAULT TRUE,  -- 鎖定期標記
    weight_pct        NUMERIC(10,6),
    investment_strategy VARCHAR(32),
    loaded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, security_code)
);
COMMENT ON TABLE  fsi.balance_stock IS '股票持倉：支持全球市場（HKEX/NYSE/LSE/A股）';
COMMENT ON COLUMN fsi.balance_stock.is_sellable IS '鎖定期內標記FALSE，影響流動性計算';

CREATE INDEX IF NOT EXISTS idx_bal_stock_port_date ON fsi.balance_stock(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_bal_stock_market    ON fsi.balance_stock(market_id);

-- ────────────────────────────────────────────────────────────
-- 8. 基金持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_fund (
    evaluate_date     DATE         NOT NULL,
    port_id           VARCHAR(16)  NOT NULL,
    security_code     VARCHAR(32)  NOT NULL,
    security_name     VARCHAR(200),
    fund_type         VARCHAR(16),               -- PUBLIC/ETF/PRIVATE/HEDGE
    market_id         VARCHAR(16),
    currency          CHAR(3)      NOT NULL,
    fx_rate           NUMERIC(16,8),
    quantity          NUMERIC(20,4) NOT NULL,
    cost              NUMERIC(24,2),
    unit_nav          NUMERIC(16,8),
    market_value      NUMERIC(24,2) NOT NULL,
    market_value_base NUMERIC(24,2),
    weight_pct        NUMERIC(10,6),
    loaded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, security_code)
);
COMMENT ON TABLE fsi.balance_fund IS '基金持倉：FOF架構下底層基金持倉';

CREATE INDEX IF NOT EXISTS idx_bal_fund_port_date ON fsi.balance_fund(port_id, evaluate_date DESC);

-- ────────────────────────────────────────────────────────────
-- 9. 期貨持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_futures (
    evaluate_date         DATE                NOT NULL,
    port_id               VARCHAR(16)         NOT NULL,
    contract_code         VARCHAR(32)         NOT NULL,
    contract_name         VARCHAR(120),
    contract_category     VARCHAR(16)         NOT NULL,      -- 股指/利率/商品
    market_id             VARCHAR(16),
    currency              CHAR(3)             NOT NULL,
    long_short            fsi.long_short_flag NOT NULL,
    quantity              INTEGER             NOT NULL,
    contract_multiplier   NUMERIC(12,4),
    notional_amount       NUMERIC(24,2),
    notional_pct_of_nav   NUMERIC(10,6),                    -- 名義金額/NAV（槓桿指標）
    cost                  NUMERIC(24,2),
    unit_cost             NUMERIC(24,8),
    settlement_price      NUMERIC(24,8),
    last_settlement_price NUMERIC(24,8),
    market_value          NUMERIC(24,2),
    mtm_pnl               NUMERIC(24,2),                    -- 逐日盯市盈虧
    margin_balance        NUMERIC(24,2),
    weight_pct            NUMERIC(10,6),
    loaded_at             TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, contract_code, long_short)
);
COMMENT ON TABLE  fsi.balance_futures IS '期貨持倉：含名義金額（槓桿指標）和每日盯市盈虧';
COMMENT ON COLUMN fsi.balance_futures.notional_pct_of_nav IS '期貨名義金額佔NAV比例，監管槓桿指標';

CREATE INDEX IF NOT EXISTS idx_bal_fut_port_date ON fsi.balance_futures(port_id, evaluate_date DESC);

-- ────────────────────────────────────────────────────────────
-- 10. 期權持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_options (
    evaluate_date       DATE                NOT NULL,
    port_id             VARCHAR(16)         NOT NULL,
    contract_code       VARCHAR(48)         NOT NULL,
    contract_name       VARCHAR(120),
    underlying_code     VARCHAR(32),
    underlying_type     VARCHAR(16),
    option_type         VARCHAR(4)          NOT NULL,  -- CALL/PUT
    long_short          fsi.long_short_flag NOT NULL,
    exercise_style      VARCHAR(4)          DEFAULT 'EU',
    strike_price        NUMERIC(24,8)       NOT NULL,
    expiry_date         DATE                NOT NULL,
    currency            CHAR(3)             NOT NULL,
    quantity            INTEGER             NOT NULL,
    contract_multiplier NUMERIC(12,4),
    premium             NUMERIC(24,8),
    market_price        NUMERIC(24,8),
    market_value        NUMERIC(24,2),
    delta               NUMERIC(12,8),
    gamma               NUMERIC(12,8),
    vega                NUMERIC(12,8),
    theta               NUMERIC(12,8),
    rho                 NUMERIC(12,8),
    implied_vol         NUMERIC(10,6),
    notional_amount     NUMERIC(24,2),
    weight_pct          NUMERIC(10,6),
    loaded_at           TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, contract_code, long_short)
);
COMMENT ON TABLE  fsi.balance_options IS '期權持倉：含完整Greeks指標，支持Delta中性策略';
COMMENT ON COLUMN fsi.balance_options.implied_vol IS '隱含波動率（Implied Volatility）';

CREATE INDEX IF NOT EXISTS idx_bal_opt_port_date ON fsi.balance_options(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_bal_opt_expiry    ON fsi.balance_options(expiry_date);

-- ────────────────────────────────────────────────────────────
-- 11. 回購持倉
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_repo (
    evaluate_date         DATE         NOT NULL,
    port_id               VARCHAR(16)  NOT NULL,
    repo_id               VARCHAR(64)  NOT NULL,
    repo_type             VARCHAR(8)   NOT NULL,  -- REPO=正回購 / REV_REPO=逆回購
    market_id             VARCHAR(16),
    counterparty_id       VARCHAR(16),
    counterparty_name     VARCHAR(200),
    pledged_security_code VARCHAR(32),
    pledged_security_name VARCHAR(200),
    currency              CHAR(3)      NOT NULL,
    value_date            DATE         NOT NULL,
    maturity_date         DATE         NOT NULL,
    remaining_days        INTEGER GENERATED ALWAYS AS (maturity_date - evaluate_date) STORED,
    principal             NUMERIC(24,2) NOT NULL,
    interest_rate         NUMERIC(12,8) NOT NULL,
    accrued_interest      NUMERIC(24,2),
    total_value           NUMERIC(24,2),
    discount_rate         NUMERIC(8,6),
    pledged_face_value    NUMERIC(24,2),
    interest_days         INTEGER,                 -- 計息天數；T_Transact_Repo.InterestDays
    actual_maturity_date  DATE,                    -- 實際到期日（提前終止時）；T_Balance_Repo.ActualMaturityDate
    weight_pct            NUMERIC(10,6),
    loaded_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, repo_id)
);
COMMENT ON TABLE  fsi.balance_repo IS '回購持倉：正回購（融出）和逆回購（融入），流動性管理工具';
COMMENT ON COLUMN fsi.balance_repo.repo_type IS 'REPO=正回購（賣出質押券融入資金）/ REV_REPO=逆回購（融出資金）';

CREATE INDEX IF NOT EXISTS idx_bal_repo_port_date    ON fsi.balance_repo(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_bal_repo_maturity     ON fsi.balance_repo(maturity_date);
CREATE INDEX IF NOT EXISTS idx_bal_repo_counterparty ON fsi.balance_repo(counterparty_id);

-- ────────────────────────────────────────────────────────────
-- 12. 份額持有人
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_holder_summary (
    confirm_date          DATE         NOT NULL,
    port_id               VARCHAR(16)  NOT NULL,
    class_id              VARCHAR(32),
    total_holders         INTEGER,
    retail_holders        INTEGER,
    institutional_holders INTEGER,
    total_shares          NUMERIC(24,6),
    retail_shares         NUMERIC(24,6),
    top10_amount          NUMERIC(24,2),
    top10_pct             NUMERIC(8,4),
    PRIMARY KEY (confirm_date, port_id, class_id)
);
COMMENT ON TABLE fsi.balance_holder_summary IS '份額持有人摘要：持有人集中度、散戶/機構結構分析';

CREATE TABLE IF NOT EXISTS fsi.balance_holder_rank (
    confirm_date  DATE         NOT NULL,
    port_id       VARCHAR(16)  NOT NULL,
    class_id      VARCHAR(32),
    rank_no       INTEGER      NOT NULL,
    holder_id     VARCHAR(32)  NOT NULL,
    holder_name   VARCHAR(200),
    shares        NUMERIC(24,6),
    amount        NUMERIC(24,2),
    pct_of_total  NUMERIC(8,4),
    PRIMARY KEY (confirm_date, port_id, rank_no)
);
COMMENT ON TABLE  fsi.balance_holder_rank IS '前N大持有人排名：集中度監控，監管報告常見要求';
COMMENT ON COLUMN fsi.balance_holder_rank.pct_of_total IS '佔總份額比例（%），高集中度觸發流動性風險預警';

-- ────────────────────────────────────────────────────────────
-- 13. 估值資產負債表（Balance Sheet）
--   直接接收估值系統輸出，保持簡潔，與源系統字段一一對應
--   設計原則：欄位對齊估值系統報表，不做二次加工
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_valuation_sheet (
    evaluate_date   DATE           NOT NULL,
    port_id         VARCHAR(16)    NOT NULL,
    subject_code    VARCHAR(32)    NOT NULL,  -- 估值科目代碼
    subject_name    VARCHAR(120)   NOT NULL,  -- 估值科目名稱
    currency        CHAR(3)        NOT NULL,
    quantity        NUMERIC(24,6),            -- 數量/份額
    unit_price      NUMERIC(24,8),            -- 估值單價
    cost            NUMERIC(24,2),            -- 成本
    market_value    NUMERIC(24,2),            -- 估值市值
    weight_pct      NUMERIC(18,8),            -- 佔NAV比例
    data_source     VARCHAR(32),              -- 來源估值系統標識
    memo            VARCHAR(200),
    loaded_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, subject_code)
);
COMMENT ON TABLE  fsi.balance_valuation_sheet IS '估值資產負債表：直接取自估值系統，按科目展示組合資產/負債估值';
COMMENT ON COLUMN fsi.balance_valuation_sheet.subject_code IS '估值系統科目代碼，如「交易性金融資產—債券」對應具體科目編號';
COMMENT ON COLUMN fsi.balance_valuation_sheet.weight_pct   IS '估值系統輸出的佔NAV比例，直接使用不重新計算';

CREATE INDEX IF NOT EXISTS idx_bal_vs_port_date ON fsi.balance_valuation_sheet(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_bal_vs_subject   ON fsi.balance_valuation_sheet(subject_code);

-- ────────────────────────────────────────────────────────────
-- 15. 按銷售渠道持有人份額快照
--   對應 T_Balance_Port_Holder_FundShare_SalesChannel
--   用途：監控各渠道（螞蟻財富/銀行直銷/機構）的每日存量份額
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_holder_by_channel (
    confirm_date    DATE          NOT NULL,
    port_id         VARCHAR(16)   NOT NULL,
    class_id        VARCHAR(32),
    channel_id      VARCHAR(16)   NOT NULL,   -- 渠道代碼（000392=螞蟻財富）
    channel_name    VARCHAR(120),
    shares          NUMERIC(24,6),            -- 持有份額（份）；T_Balance_Port_Holder_FundShare_SalesChannel.Shares
    amount          NUMERIC(24,2),            -- 持有金額（元）
    unit_nav        NUMERIC(16,8),
    PRIMARY KEY (confirm_date, port_id, channel_id)
);
COMMENT ON TABLE fsi.balance_holder_by_channel IS
    '按銷售渠道持有人份額快照：對應 T_Balance_Port_Holder_FundShare_SalesChannel，
     監控各渠道（螞蟻財富/銀行直銷/機構）每日存量份額，SalesChannelId=000392為網商渠道';
