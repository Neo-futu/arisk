-- ============================================================
-- 005_transact.sql  交易記錄層  (prefix: transact_)
-- FSI Financial Services Intelligence Platform
-- 涵蓋：債券 · 股票 · 存款證 · 定期存款 · 期貨 · 期權
--        回購 · 基金 · 申購贖回 · 損益明細
-- 依賴：001_schema_init.sql · 002_para.sql · 004_mktdata.sql
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 債券交易
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_bond (
    txn_id          BIGSERIAL           PRIMARY KEY,
    source_txn_id   VARCHAR(64),                        -- 原系統流水號（冪等載入）
    port_id         VARCHAR(16)         NOT NULL,
    trade_date      DATE                NOT NULL,
    settle_date     DATE,
    status          fsi.txn_status      NOT NULL DEFAULT 'CONFIRMED',
    security_code   VARCHAR(32)         NOT NULL,
    isin            VARCHAR(12),
    security_name   VARCHAR(200),
    market_id       VARCHAR(16),
    asset_subtype   fsi.asset_class     DEFAULT 'BOND_CORP',
    direction       fsi.trade_direction NOT NULL,
    txn_type        VARCHAR(32),                        -- BUY_SPOT/BUY_IPO/SELL/MATURE/COUPON
    currency        CHAR(3)             NOT NULL,
    quantity        NUMERIC(20,4)       NOT NULL,
    clean_price     NUMERIC(24,8),
    accrued_interest NUMERIC(24,2),
    principal       NUMERIC(24,2),
    gross_amount    NUMERIC(24,2),
    fee             NUMERIC(16,4)       DEFAULT 0,
    net_amount      NUMERIC(24,2),
    amount_base_ccy NUMERIC(24,2),
    ytm             NUMERIC(14,10),
    duration        NUMERIC(12,8),
    counterparty_id VARCHAR(16),
    broker          VARCHAR(128),
    investment_strategy VARCHAR(32),
    notes           TEXT,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.transact_bond IS '債券交易記錄：含利率風險快照（YTM/Duration），用於績效歸因';
COMMENT ON COLUMN fsi.transact_bond.clean_price IS '成交淨價（不含應計利息），債券二級市場報價基準';
COMMENT ON COLUMN fsi.transact_bond.source_txn_id IS '原系統流水號，UNIQUE保證冪等寫入';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_bond_src      ON fsi.transact_bond(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_bond_port_date  ON fsi.transact_bond(port_id, trade_date DESC);
CREATE INDEX        IF NOT EXISTS idx_txn_bond_security   ON fsi.transact_bond(security_code, trade_date DESC);
CREATE INDEX        IF NOT EXISTS idx_txn_bond_settle     ON fsi.transact_bond(settle_date) WHERE status = 'CONFIRMED';

-- ────────────────────────────────────────────────────────────
-- 2. 股票交易
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_stock (
    txn_id          BIGSERIAL           PRIMARY KEY,
    source_txn_id   VARCHAR(64),
    port_id         VARCHAR(16)         NOT NULL,
    trade_date      DATE                NOT NULL,
    settle_date     DATE,
    status          fsi.txn_status      NOT NULL DEFAULT 'CONFIRMED',
    security_code   VARCHAR(32)         NOT NULL,
    isin            VARCHAR(12),
    security_name   VARCHAR(200),
    market_id       VARCHAR(16)         NOT NULL,
    currency        CHAR(3)             NOT NULL,
    direction       fsi.trade_direction NOT NULL,
    txn_type        VARCHAR(32),                        -- BUY/SELL/IPO/RIGHTS/DIVIDEND_STOCK
    quantity        NUMERIC(20,4)       NOT NULL,
    price           NUMERIC(24,8)       NOT NULL,
    gross_amount    NUMERIC(24,2)       NOT NULL,
    stamp_duty      NUMERIC(16,4)       DEFAULT 0,      -- 印花稅
    commission      NUMERIC(16,4)       DEFAULT 0,      -- 傭金
    levy            NUMERIC(16,4)       DEFAULT 0,      -- SFC/HKEX 監管徵費
    other_fee       NUMERIC(16,4)       DEFAULT 0,
    net_amount      NUMERIC(24,2)       NOT NULL,
    amount_base_ccy NUMERIC(24,2),
    fx_rate         NUMERIC(16,8),
    counterparty_id VARCHAR(16),
    broker          VARCHAR(128),
    investment_strategy VARCHAR(32),
    notes           TEXT,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.transact_stock IS '股票交易記錄：細分印花稅/傭金/監管徵費，支持全成本計算';
COMMENT ON COLUMN fsi.transact_stock.levy IS 'SFC Levy + HKEX Levy，香港監管交易徵費';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_stock_src     ON fsi.transact_stock(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_stock_port_date ON fsi.transact_stock(port_id, trade_date DESC);
CREATE INDEX        IF NOT EXISTS idx_txn_stock_security  ON fsi.transact_stock(security_code, trade_date DESC);

-- ────────────────────────────────────────────────────────────
-- 3. 存款證（CD）交易
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_cd (
    txn_id          BIGSERIAL           PRIMARY KEY,
    source_txn_id   VARCHAR(64),
    port_id         VARCHAR(16)         NOT NULL,
    trade_date      DATE                NOT NULL,
    settle_date     DATE,
    status          fsi.txn_status      NOT NULL DEFAULT 'CONFIRMED',
    security_code   VARCHAR(32)         NOT NULL,
    security_name   VARCHAR(120),
    direction       fsi.trade_direction NOT NULL,
    txn_type        VARCHAR(32),                        -- BUY/SELL/MATURE
    issuer_id       VARCHAR(16),
    issuer_name     VARCHAR(200),
    currency        CHAR(3)             NOT NULL,
    value_date      DATE,
    maturity_date   DATE,
    issue_yield     NUMERIC(12,8),
    price           NUMERIC(24,8),
    quantity        NUMERIC(20,4)       NOT NULL,
    principal       NUMERIC(24,2),
    gross_amount    NUMERIC(24,2),
    fee             NUMERIC(16,4)       DEFAULT 0,
    net_amount      NUMERIC(24,2),
    ytm             NUMERIC(14,10),
    duration        NUMERIC(12,8),
    notes           TEXT,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.transact_cd IS '存款證交易：一級市場認購和二級市場買賣';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_cd_src     ON fsi.transact_cd(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_cd_port_date ON fsi.transact_cd(port_id, trade_date DESC);

-- ────────────────────────────────────────────────────────────
-- 4. 定期存款交易
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_deposit (
    txn_id         BIGSERIAL       PRIMARY KEY,
    source_txn_id  VARCHAR(64),
    port_id        VARCHAR(16)     NOT NULL,
    trade_date     DATE            NOT NULL,
    status         fsi.txn_status  NOT NULL DEFAULT 'CONFIRMED',
    deposit_id     VARCHAR(48)     NOT NULL,
    txn_type       VARCHAR(16)     NOT NULL,   -- PLACE=新存 / MATURE=到期 / EARLY_BREAK=提前支取
    bank_id        VARCHAR(16),
    bank_name      VARCHAR(200),
    currency       CHAR(3)         NOT NULL,
    value_date     DATE            NOT NULL,
    maturity_date  DATE            NOT NULL,
    principal      NUMERIC(24,2)   NOT NULL,
    interest_rate  NUMERIC(12,8)   NOT NULL,
    interest_amount NUMERIC(24,2),
    penalty_amount NUMERIC(24,2)   DEFAULT 0,
    net_proceeds   NUMERIC(24,2),
    notes          TEXT,
    created_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.transact_deposit IS '定期存款交易：新存/到期/提前支取，罰息單獨列示';
COMMENT ON COLUMN fsi.transact_deposit.txn_type IS 'PLACE=新增定存 / MATURE=正常到期 / EARLY_BREAK=提前支取（含罰息）';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_dep_src     ON fsi.transact_deposit(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_dep_port_date ON fsi.transact_deposit(port_id, trade_date DESC);

-- ────────────────────────────────────────────────────────────
-- 5. 期貨交易
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_futures (
    txn_id         BIGSERIAL           PRIMARY KEY,
    source_txn_id  VARCHAR(64),
    port_id        VARCHAR(16)         NOT NULL,
    trade_date     DATE                NOT NULL,
    status         fsi.txn_status      NOT NULL DEFAULT 'CONFIRMED',
    contract_code  VARCHAR(32)         NOT NULL,
    contract_name  VARCHAR(120),
    long_short     fsi.long_short_flag NOT NULL,
    txn_type       VARCHAR(16)         NOT NULL,   -- OPEN=開倉 / CLOSE=平倉 / SETTLE=交割
    currency       CHAR(3)             NOT NULL,
    quantity       INTEGER             NOT NULL,
    price          NUMERIC(24,8)       NOT NULL,
    notional_amount NUMERIC(24,2),
    commission     NUMERIC(16,4)       DEFAULT 0,
    margin_change  NUMERIC(24,2),
    realized_pnl   NUMERIC(24,2),                  -- 平倉實現盈虧
    broker         VARCHAR(128),
    notes          TEXT,
    created_at     TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.transact_futures IS '期貨交易：開/平倉，含名義金額和實現盈虧';
COMMENT ON COLUMN fsi.transact_futures.realized_pnl IS '平倉時計算的實現盈虧，開倉時為NULL';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_fut_src      ON fsi.transact_futures(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_fut_port_date  ON fsi.transact_futures(port_id, trade_date DESC);
CREATE INDEX        IF NOT EXISTS idx_txn_fut_contract   ON fsi.transact_futures(contract_code, trade_date DESC);

-- ────────────────────────────────────────────────────────────
-- 6. 期權交易
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_options (
    txn_id          BIGSERIAL           PRIMARY KEY,
    source_txn_id   VARCHAR(64),
    port_id         VARCHAR(16)         NOT NULL,
    trade_date      DATE                NOT NULL,
    status          fsi.txn_status      NOT NULL DEFAULT 'CONFIRMED',
    contract_code   VARCHAR(48)         NOT NULL,
    underlying_code VARCHAR(32),
    option_type     VARCHAR(4)          NOT NULL,  -- CALL/PUT
    long_short      fsi.long_short_flag NOT NULL,
    exercise_style  VARCHAR(4)          DEFAULT 'EU',
    strike_price    NUMERIC(24,8)       NOT NULL,
    expiry_date     DATE                NOT NULL,
    currency        CHAR(3)             NOT NULL,
    txn_type        VARCHAR(16)         NOT NULL,  -- BUY/SELL/EXERCISE/EXPIRE
    quantity        INTEGER             NOT NULL,
    premium         NUMERIC(24,8)       NOT NULL,
    gross_amount    NUMERIC(24,2),
    commission      NUMERIC(16,4)       DEFAULT 0,
    net_amount      NUMERIC(24,2),
    delta_at_trade  NUMERIC(12,8),
    implied_vol     NUMERIC(10,6),
    realized_pnl    NUMERIC(24,2),
    broker          VARCHAR(128),
    notes           TEXT,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.transact_options IS '期權交易：記錄期權金、Greeks快照和行權/到期處理';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_opt_src     ON fsi.transact_options(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_opt_port_date ON fsi.transact_options(port_id, trade_date DESC);

-- ────────────────────────────────────────────────────────────
-- 7. 回購交易
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_repo (
    txn_id               BIGSERIAL       PRIMARY KEY,
    source_txn_id        VARCHAR(64),
    port_id              VARCHAR(16)     NOT NULL,
    trade_date           DATE            NOT NULL,
    settle_date          DATE,
    maturity_date        DATE            NOT NULL,
    status               fsi.txn_status  NOT NULL DEFAULT 'CONFIRMED',
    repo_type            VARCHAR(8)      NOT NULL,   -- REPO / REV_REPO
    market_id            VARCHAR(16),
    counterparty_id      VARCHAR(16),
    counterparty_name    VARCHAR(200),
    currency             CHAR(3)         NOT NULL,
    principal            NUMERIC(24,2)   NOT NULL,
    interest_rate        NUMERIC(12,8)   NOT NULL,
    interest_days        INTEGER,
    interest_amount      NUMERIC(24,2),
    pledged_security_code VARCHAR(32),
    pledged_security_name VARCHAR(200),
    discount_rate        NUMERIC(8,6),
    pledged_face_value    NUMERIC(24,2),
    actual_maturity_date  DATE,                    -- 實際到期日（提前終止）；T_Transact_Repo.ActualMaturityDate
    notes                 TEXT,
    created_at            TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.transact_repo IS '回購交易：正回購/逆回購，短期流動性管理';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_repo_src     ON fsi.transact_repo(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_repo_port_date ON fsi.transact_repo(port_id, trade_date DESC);
CREATE INDEX        IF NOT EXISTS idx_txn_repo_maturity  ON fsi.transact_repo(maturity_date) WHERE status = 'CONFIRMED';

-- ────────────────────────────────────────────────────────────
-- 8. 基金交易（申購/贖回/轉換）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_fund (
    txn_id           BIGSERIAL           PRIMARY KEY,
    source_txn_id    VARCHAR(64),
    port_id          VARCHAR(16)         NOT NULL,
    trade_date       DATE                NOT NULL,
    confirm_date     DATE,                                   -- NAV確認日
    settle_date      DATE,
    status           fsi.txn_status      NOT NULL DEFAULT 'CONFIRMED',
    security_code    VARCHAR(32)         NOT NULL,
    security_name    VARCHAR(200),
    currency         CHAR(3)             NOT NULL,
    direction        fsi.trade_direction NOT NULL,
    txn_type         VARCHAR(16),                            -- SUBSCRIBE/REDEEM/SWITCH_IN/SWITCH_OUT
    quantity         NUMERIC(20,4),
    unit_nav         NUMERIC(16,8),
    gross_amount     NUMERIC(24,2)       NOT NULL,
    subscription_fee NUMERIC(16,4)       DEFAULT 0,
    redemption_fee   NUMERIC(16,4)       DEFAULT 0,
    net_amount       NUMERIC(24,2),
    notes            TEXT,
    created_at       TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.transact_fund IS '基金申購/贖回/轉換：含NAV確認日（T+1或T+2確認）';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_fund_src     ON fsi.transact_fund(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_fund_port_date ON fsi.transact_fund(port_id, trade_date DESC);

-- ────────────────────────────────────────────────────────────
-- 9. 組合層申購贖回（投資者進出基金）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_subscription (
    txn_id           BIGSERIAL           PRIMARY KEY,
    source_txn_id    VARCHAR(64),
    port_id          VARCHAR(16)         NOT NULL,
    class_id         VARCHAR(32),
    confirm_date     DATE                NOT NULL,
    settle_date      DATE,
    direction        fsi.trade_direction NOT NULL,   -- BUY=申購 / SELL=贖回
    investor_id      VARCHAR(32),
    investor_name    VARCHAR(200),
    currency         CHAR(3)             NOT NULL,
    amount           NUMERIC(24,2),
    shares           NUMERIC(24,6),
    unit_nav         NUMERIC(16,8),
    front_load_fee   NUMERIC(16,4)       DEFAULT 0,
    back_load_fee    NUMERIC(16,4)       DEFAULT 0,
    net_amount       NUMERIC(24,2),
    sales_channel_id VARCHAR(16),
    notes            TEXT,
    created_at       TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.transact_subscription IS '投資者申購/贖回記錄：組合現金流管理和份額登記基礎';
COMMENT ON COLUMN fsi.transact_subscription.confirm_date IS '以此日NAV計算份額，依基金章程通常申購T+1';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_sub_src      ON fsi.transact_subscription(source_txn_id) WHERE source_txn_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_sub_port_date  ON fsi.transact_subscription(port_id, confirm_date DESC);

-- ────────────────────────────────────────────────────────────
-- 10. 損益明細（每日由計算引擎生成）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_pnl_item (
    pnl_id          BIGSERIAL        PRIMARY KEY,
    evaluate_date   DATE             NOT NULL,
    port_id         VARCHAR(16)      NOT NULL,
    security_code   VARCHAR(32),
    asset_class     fsi.asset_class,
    asset_subtype   VARCHAR(32),
    mtm_delta       NUMERIC(24,4),   -- 盯市損益（價格變動）
    interest_income NUMERIC(24,4),   -- 利息/股息收入
    realized_gain   NUMERIC(24,4),   -- 實現收益
    fx_pnl          NUMERIC(24,4),   -- 外匯損益
    fee_expense     NUMERIC(24,4),   -- 費用支出
    net_pnl         NUMERIC(24,4),   -- 淨損益合計
    net_pnl_base    NUMERIC(24,4),   -- 折算基幣
    currency        CHAR(3),
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.transact_pnl_item IS '損益明細：按證券/資產類別拆分損益來源，多維度業績歸因';
COMMENT ON COLUMN fsi.transact_pnl_item.mtm_delta IS 'Mark-to-Market變動：市場價格變動產生的浮盈虧變化';
COMMENT ON COLUMN fsi.transact_pnl_item.fx_pnl IS '外匯損益：匯率變動對非基幣持倉的影響';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_pnl_port_date_sec ON fsi.transact_pnl_item(evaluate_date, port_id, security_code);
CREATE INDEX        IF NOT EXISTS idx_txn_pnl_port_date   ON fsi.transact_pnl_item(port_id, evaluate_date DESC);
CREATE INDEX        IF NOT EXISTS idx_txn_pnl_asset       ON fsi.transact_pnl_item(asset_class, evaluate_date DESC);

-- ────────────────────────────────────────────────────────────
-- 11. 組合損益表（Fund P&L Statement）
--   參考：T_Transact_ProfitLoss_Item（源表為個券明細）
--   本表為組合層面匯總損益，用於：
--   · 基金會計核對（損益 + 申購贖回 = NAV變動）
--   · 估值系統出具的每日損益科目報告
--   · 與 balance_portfolio_delta 互相驗算
--
--   分類說明：
--   一級資產類別（asset_class_l1）匯總後得到組合整體損益
--   二級細分（asset_class_l2）支持更精細的損益溯源
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_portfolio_pnl (
    evaluate_date       DATE          NOT NULL,
    port_id             VARCHAR(16)   NOT NULL,
    asset_class_l1      VARCHAR(16)   NOT NULL,    -- 一級資產類別：BOND/STOCK/CD/DEPOSIT/REPO/CASH/FX/FEE
    asset_class_l2      VARCHAR(32),               -- 二級細分：BOND_GOVT/BOND_CORP/STOCK_A/STOCK_HK 等

    -- 損益來源拆分（對齊 T_Transact_ProfitLoss_Item）
    net_pnl             NUMERIC(24,4),             -- 當日淨損益合計
    mtm_delta           NUMERIC(24,4),             -- 盯市損益（持倉估值變動）
    interest_income     NUMERIC(24,4),             -- 利息/股息收入（應計+到期）
    realized_return     NUMERIC(24,4),             -- 已實現損益（賣出/到期/回購收益）
    fx_pnl              NUMERIC(24,4),             -- 外匯損益
    fees                NUMERIC(24,4),             -- 費用支出（管理費/托管費/交易費）

    currency            CHAR(3),
    data_source         VARCHAR(32)   NOT NULL DEFAULT 'VALUATION',
    loaded_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    PRIMARY KEY (evaluate_date, port_id, asset_class_l1, asset_class_l2)
);

COMMENT ON TABLE  fsi.transact_portfolio_pnl IS '組合每日損益表：按資產類別匯總各損益來源，基金會計核對和淨值驗算的依據';
COMMENT ON COLUMN fsi.transact_portfolio_pnl.asset_class_l1 IS '一級分類：BOND/STOCK/CD/DEPOSIT/REPO/CASH/FX/FEE，與資產負債表科目對應';
COMMENT ON COLUMN fsi.transact_portfolio_pnl.mtm_delta IS '盯市損益（Mark-to-Market）：持倉估值變動，未實現部分';
COMMENT ON COLUMN fsi.transact_portfolio_pnl.interest_income IS '利息收入/股息收入：應計利息到期確認 + 票息到賬';
COMMENT ON COLUMN fsi.transact_portfolio_pnl.realized_return IS '已實現損益：賣出價 - 成本，以及回購/存款到期利息';
COMMENT ON COLUMN fsi.transact_portfolio_pnl.fees IS '費用支出（負數）：管理費/托管費/交易傭金/印花稅等';

CREATE INDEX IF NOT EXISTS idx_txn_ppnl_port_date  ON fsi.transact_portfolio_pnl(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_txn_ppnl_asset_date ON fsi.transact_portfolio_pnl(asset_class_l1, evaluate_date DESC);
