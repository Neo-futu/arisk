-- ============================================================
-- 010_index_counterparty.sql  指數與對手方擴展表
-- FSI Financial Services Intelligence Platform
-- 涵蓋：可比組 · 交易對手 · 戰略配置指引 · 指數成分
--        養老金持倉 · 銀行間交易 · 風控預警 · 業績監控
-- 已移除（二期）：port_subunit / balance_insurance
--               mktdata_stock_factor / transact_voucher
-- ============================================================

-- ============================================================
-- PART A: para_ 補充（參數層）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- A1. 組合多維分類
--   源：T_Para_PortCategoryId
--   說明：同一組合可有多個維度的分類標籤（監管類型/投資風格/
--         客戶類型等），比 port_type ENUM 更靈活
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_port_category (
    port_id         VARCHAR(16)  NOT NULL,
    category_dim    VARCHAR(16)  NOT NULL,   -- 分類維度：REGULATORY/STYLE/CLIENT/RISK_LEVEL
    category_id     VARCHAR(16)  NOT NULL,   -- 分類代碼
    category_name   VARCHAR(60),
    begin_date      DATE         NOT NULL,
    end_date        DATE,
    PRIMARY KEY (port_id, category_dim, begin_date)
);
COMMENT ON TABLE  fsi.para_port_category IS '組合多維分類：同一組合可在監管/投資風格/客戶類型等多個維度打標籤';
COMMENT ON COLUMN fsi.para_port_category.category_dim IS 'REGULATORY=監管類型 / STYLE=投資風格 / CLIENT=客戶類型 / RISK_LEVEL=風險等級';

CREATE INDEX IF NOT EXISTS idx_para_pc_port ON fsi.para_port_category(port_id);

-- ────────────────────────────────────────────────────────────
-- A2. 基金可比組（Peer Group）
--   業績報告標準需求：SFC Fact Sheet 要求展示同類排名和分位數
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_peer_group (
    group_id      SERIAL       PRIMARY KEY,
    group_name    VARCHAR(100) NOT NULL,
    group_name_en VARCHAR(100),
    base_date     DATE,
    description   TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.para_peer_group IS '基金可比組：如「香港股票基金」/「香港貨幣市場基金」，業績排名和分位數分析基礎';

CREATE TABLE IF NOT EXISTS fsi.para_peer_group_member (
    group_id      INTEGER      NOT NULL,
    fund_code     VARCHAR(32)  NOT NULL,   -- SFC 認可代碼（如 AGW600）
    fund_name     VARCHAR(200),            -- 基金名稱（中文）
    fund_name_en  VARCHAR(200),            -- 基金名稱（英文）
    wind_code     VARCHAR(32),             -- Wind 行情代碼（如 BOC000014.OF / 3421.OF）
    begin_date    DATE         NOT NULL,
    end_date      DATE,
    memo          TEXT,                    -- 備注（如類別確認、Wind 暫無等）
    PRIMARY KEY (group_id, fund_code, begin_date)
);
COMMENT ON TABLE fsi.para_peer_group_member IS '可比組成員：同類公募基金列表，定期更新，計算組合業績分位排名';
COMMENT ON COLUMN fsi.para_peer_group_member.fund_code    IS 'SFC 認可代碼，香港監管機構授予的唯一識別碼';
COMMENT ON COLUMN fsi.para_peer_group_member.wind_code    IS 'Wind 行情代碼，用於從 Wind 拉取 NAV/收益率數據；ETF用股票代碼（如3421.OF）';

CREATE TABLE IF NOT EXISTS fsi.para_port_peer_mapping (
    port_id     VARCHAR(16)  NOT NULL,
    group_id    INTEGER      NOT NULL,
    begin_date  DATE         NOT NULL,
    end_date    DATE,
    PRIMARY KEY (port_id, group_id, begin_date)
);
COMMENT ON TABLE  fsi.para_port_peer_mapping IS '組合與可比組映射：一個組合可同時參與多個可比組排名';
COMMENT ON COLUMN fsi.para_port_peer_mapping.group_id IS '對應 para_peer_group.group_id';

CREATE INDEX IF NOT EXISTS idx_para_ppg_port ON fsi.para_port_peer_mapping(port_id);

-- ────────────────────────────────────────────────────────────
-- A3. 按組合分類的戰略資產配置指引
--   源：T_Para_AssetAllocationDirective
--   說明：針對某一類別組合（如所有MMF）的資產配置上下限，
--         比逐個組合設置更高效
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_asset_alloc_directive (
    category_dim    VARCHAR(16)  NOT NULL,
    category_id     VARCHAR(16)  NOT NULL,
    asset_class     VARCHAR(32)  NOT NULL,   -- 資產類別（與 fsi.asset_class ENUM 對應）
    lower_limit_pct NUMERIC(9,4),
    upper_limit_pct NUMERIC(9,4),
    centroid_pct    NUMERIC(9,4),            -- 中樞配置比例
    begin_date      DATE         NOT NULL,
    end_date        DATE,
    PRIMARY KEY (category_dim, category_id, asset_class, begin_date)
);
COMMENT ON TABLE  fsi.para_asset_alloc_directive IS '戰略資產配置指引：按組合類別設置資產配置區間，風格漂移監控依據';
COMMENT ON COLUMN fsi.para_asset_alloc_directive.centroid_pct IS '中樞配置比例（戰略中心倉位），實際偏離此值即觸發戰術調整評估';

-- ────────────────────────────────────────────────────────────
-- A4. 交易對手信用風險檔案
--   源：T_Para_CreditRisk_CounterParty
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_counterparty (
    counterparty_id   VARCHAR(16)  PRIMARY KEY,
    counterparty_name VARCHAR(200) NOT NULL,
    institution_id    VARCHAR(16),           -- 關聯 para_institution
    country           CHAR(2),
    credit_rating     VARCHAR(8),
    rating_agency     VARCHAR(8),
    is_blacklisted    BOOLEAN      NOT NULL DEFAULT FALSE,
    blacklist_reason  VARCHAR(200),
    blacklist_date    DATE,
    credit_limit      NUMERIC(24,2),         -- 授信額度
    credit_limit_ccy  CHAR(3),
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.para_counterparty IS '交易對手信用風險檔案：交易對手授信管理，含黑名單和額度管理';
COMMENT ON COLUMN fsi.para_counterparty.credit_limit IS '對該交易對手的授信敞口上限，超限需風控審批';

-- ────────────────────────────────────────────────────────────
-- A6. 業績回報調整記錄
--   源：T_Para_Port_AdjustReturn
--   說明：因企業行動/數據錯誤等原因需對歷史業績做人工調整
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_port_return_adjust (
    port_id         VARCHAR(16)  NOT NULL,
    begin_date      DATE         NOT NULL,
    end_date        DATE         NOT NULL,
    adj_return      NUMERIC(15,9) NOT NULL,  -- 調整後的期間收益率
    reason          VARCHAR(200),
    approved_by     VARCHAR(64),
    PRIMARY KEY (port_id, begin_date, end_date)
);
COMMENT ON TABLE  fsi.para_port_return_adjust IS '業績回報調整：因數據修正/企業行動等原因對歷史業績做人工調整，審計追蹤用';

-- ============================================================
-- PART B: balance_ 補充（持倉層）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- B1. 國內養老金持倉
--   源：T_Balance_Pension
--   說明：社保基金/企業年金/職業年金等國內養老金計劃持倉，
--         受《企業年金辦法》《職業年金辦法》規管，單獨維護
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_pension (
    evaluate_date   DATE         NOT NULL,
    port_id         VARCHAR(16)  NOT NULL,
    security_code   VARCHAR(32)  NOT NULL,
    security_name   VARCHAR(200),
    pension_type    VARCHAR(16),             -- SSF=社保基金 / EAP=企業年金 / OAP=職業年金 / OTHER
    currency        CHAR(3)      NOT NULL,
    quantity        NUMERIC(20,4) NOT NULL,
    cost            NUMERIC(24,2),
    unit_cost       NUMERIC(24,8),
    price           NUMERIC(24,8),
    market_value    NUMERIC(24,2) NOT NULL,
    market_value_base NUMERIC(24,2),
    weight_pct      NUMERIC(10,6),
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, security_code)
);
COMMENT ON TABLE  fsi.balance_pension IS '國內養老金持倉：社保基金/企業年金/職業年金，受《企業年金辦法》《職業年金辦法》規管';
COMMENT ON COLUMN fsi.balance_pension.pension_type IS 'SSF=社保基金 / EAP=企業年金 / OAP=職業年金 / OTHER=其他養老金計劃';

CREATE INDEX IF NOT EXISTS idx_bal_pen_port_date ON fsi.balance_pension(port_id, evaluate_date DESC);

-- ────────────────────────────────────────────────────────────
-- B2. 組合每日NAV變動明細
--   源：T_Transact_Portfolio_Delta
--   說明：解釋每日NAV變化的來源：損益/申購贖回/費用等
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.balance_portfolio_delta (
    evaluate_date       DATE         NOT NULL,
    port_id             VARCHAR(16)  NOT NULL,
    prev_evaluate_date  DATE,
    net_asset           NUMERIC(24,2) NOT NULL,  -- 當日NAV
    prev_net_asset      NUMERIC(24,2),            -- 前日NAV
    profit_loss         NUMERIC(24,2),            -- 當日損益
    net_purchase        NUMERIC(24,2),            -- 當日淨申購（申購-贖回）
    delta_net_asset     NUMERIC(24,2),            -- NAV變動 = 損益 + 淨申購
    scale_factor        DOUBLE PRECISION,         -- 份額調整係數（分紅/拆分）
    day_return          DOUBLE PRECISION,         -- 當日收益率
    PRIMARY KEY (evaluate_date, port_id)
);
COMMENT ON TABLE  fsi.balance_portfolio_delta IS '組合NAV日變動：拆解NAV變化來源（損益/申購贖回），業績歸因起點';
COMMENT ON COLUMN fsi.balance_portfolio_delta.scale_factor IS '份額調整係數，分紅再投資或拆分合並時≠1';

CREATE INDEX IF NOT EXISTS idx_bal_delta_port_date ON fsi.balance_portfolio_delta(port_id, evaluate_date DESC);

-- ============================================================
-- PART C: mktdata_ 補充（市場數據層）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- C1. 公募基金靜態數據
--   源：TMP.T_MarketData_Fund
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_fund_static (
    fund_code           VARCHAR(32)  PRIMARY KEY,
    fund_name           VARCHAR(200) NOT NULL,
    fund_name_en        VARCHAR(200),
    fund_type           VARCHAR(16),             -- EQUITY/BOND/BALANCED/MMF/ETF/FOF
    fund_style          VARCHAR(32),             -- GROWTH/VALUE/BLEND/INDEX
    currency            CHAR(3)      NOT NULL,
    market_id           VARCHAR(16),             -- HKEX/SSE/SZSE/OTC
    fund_company_code   VARCHAR(16),
    opened_date         DATE,
    closed_date         DATE,
    mgmt_fee_rate       NUMERIC(8,4),
    trustee_fee_rate    NUMERIC(8,4),
    sales_fee_rate      NUMERIC(8,4),
    track_index_code    VARCHAR(32),             -- 追蹤指數（指數基金）
    linked_fund_code    VARCHAR(32),             -- 關聯基金（ETF聯接基金）
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    data_source         VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.mktdata_fund_static IS '公募基金靜態數據：含ETF/指數基金追蹤標的，基金持倉估值和同類分析基礎';
COMMENT ON COLUMN fsi.mktdata_fund_static.linked_fund_code IS 'ETF聯接基金對應的ETF代碼，計算申購贖回時需要';

CREATE INDEX IF NOT EXISTS idx_mkt_fund_s_type ON fsi.mktdata_fund_static(fund_type);

-- ────────────────────────────────────────────────────────────
-- C2. 股票指數成分股（日度）
--   源：T_MarketData_Index_Component
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_index_component (
    rebal_date      DATE         NOT NULL,
    index_code      VARCHAR(32)  NOT NULL,
    security_code   VARCHAR(32)  NOT NULL,
    weight_pct      NUMERIC(10,8),           -- 成分股權重（%）
    data_source     VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rebal_date, index_code, security_code)
);
COMMENT ON TABLE  fsi.mktdata_index_component IS '股票指數成分股：每次調倉日的成分股及權重，用於指數追蹤誤差和歸因分析';

CREATE INDEX IF NOT EXISTS idx_mkt_idx_comp_date ON fsi.mktdata_index_component(rebal_date DESC, index_code);
CREATE INDEX IF NOT EXISTS idx_mkt_idx_comp_sec  ON fsi.mktdata_index_component(security_code);

-- ────────────────────────────────────────────────────────────
-- C3. 債券指數成分券（日度）
--   源：T_MarketData_IndexBond_Component + T_MarketData_IndexBond_Reconstitution
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_index_bond_component (
    rebal_date          DATE         NOT NULL,
    index_code          VARCHAR(32)  NOT NULL,
    security_code       VARCHAR(32)  NOT NULL,
    isin                VARCHAR(12),
    notional_amount     NUMERIC(24,2),           -- 指數成分面值
    clean_price         NUMERIC(24,8),
    accrued_interest    NUMERIC(16,10),
    coupon_payment      NUMERIC(16,10),
    redemption_factor   NUMERIC(16,10),          -- 提前還款因子（ABS用）
    xd_factor           NUMERIC(16,10),          -- 除息因子
    weight_pct          NUMERIC(10,8),
    data_source         VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rebal_date, index_code, security_code)
);
COMMENT ON TABLE  fsi.mktdata_index_bond_component IS '債券指數成分券：含面值/全價/應計利息，用於債券指數追蹤和業績歸因';

CREATE INDEX IF NOT EXISTS idx_mkt_ibc_date ON fsi.mktdata_index_bond_component(rebal_date DESC, index_code);

-- ────────────────────────────────────────────────────────────
-- C4. 基金分紅記錄
--   源：T_MarketData_Fund_ProfitDistribution
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_fund_dividend (
    record_date             DATE         NOT NULL,
    fund_code               VARCHAR(32)  NOT NULL,
    pretax_cash_dividend    NUMERIC(12,8),   -- 每份稅前現金分紅
    split_ratio             NUMERIC(14,8),   -- 拆分/合並比例（1=不拆）
    data_source             VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    PRIMARY KEY (record_date, fund_code)
);
COMMENT ON TABLE  fsi.mktdata_fund_dividend IS '基金分紅記錄：現金分紅和份額拆分，計算累計淨值和真實收益率必需';
COMMENT ON COLUMN fsi.mktdata_fund_dividend.split_ratio IS '份額拆分比例，如1拆2則值為2，用於調整歷史NAV序列';

-- ────────────────────────────────────────────────────────────
-- C5. 股票分紅派息記錄
--   源：T_MarketData_Stock_ProfitDistribution
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_stock_dividend (
    announce_date       DATE         NOT NULL,
    security_code       VARCHAR(32)  NOT NULL,
    record_date         DATE,
    ex_dividend_date    DATE,
    dividend_type       VARCHAR(16),             -- CASH/STOCK/SCRIP
    pretax_cash_div     NUMERIC(12,8),           -- 稅前現金股息
    aftertax_cash_div   NUMERIC(12,8),           -- 稅後現金股息
    stock_dividend      NUMERIC(10,6),           -- 送股比例
    capital_reserve_xfr NUMERIC(10,6),           -- 資本公積轉增比例
    data_source         VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    PRIMARY KEY (announce_date, security_code)
);
COMMENT ON TABLE  fsi.mktdata_stock_dividend IS '股票分紅派息：現金股息/送股/資本公積轉增，股票持倉損益計算和複權價格計算必需';

CREATE INDEX IF NOT EXISTS idx_mkt_stk_div_sec ON fsi.mktdata_stock_dividend(security_code, ex_dividend_date DESC);

-- ────────────────────────────────────────────────────────────
-- C6. 隱含/基準利率定義
--   源：T_MarketData_ImpliedInterestRate
--   說明：銀行間市場的同業拆借利率、質押式回購利率等
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_rate_def (
    rate_code       VARCHAR(16)  PRIMARY KEY,
    rate_name       VARCHAR(80)  NOT NULL,
    currency        CHAR(3)      NOT NULL,
    annual_day_count INTEGER,                -- 計息基礎天數（360/365）
    rate_category   VARCHAR(16),             -- REPO=質押回購 / IBOR=同業拆借 / POLICY=政策利率
    data_source     VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    source_id       VARCHAR(32),
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE  fsi.mktdata_rate_def IS '基準利率定義：HIBOR/SHIBOR/質押回購利率等，用於浮息券定價和回購利率比較';

CREATE TABLE IF NOT EXISTS fsi.mktdata_rate_quotes (
    rate_date       DATE         NOT NULL,
    rate_code       VARCHAR(16)  NOT NULL,
    rate            NUMERIC(12,8) NOT NULL,  -- 年化利率（小數）
    data_source     VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (rate_date, rate_code)
);
COMMENT ON TABLE fsi.mktdata_rate_quotes IS '基準利率每日報價：HIBOR/SHIBOR/回購利率，浮息債定價和流動性管理參考';

CREATE INDEX IF NOT EXISTS idx_mkt_rate_q_date ON fsi.mktdata_rate_quotes(rate_date DESC, rate_code);

-- ────────────────────────────────────────────────────────────
-- C7. 機構集團關係（主從關係）
--   源：T_MarketData_Institution_Master_Slave
--   說明：集團下各子公司，用於集團敞口集中度計算
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_institution_group (
    group_id        VARCHAR(16)  NOT NULL,   -- 集團ID（母公司ID）
    group_name      VARCHAR(200) NOT NULL,
    member_id       VARCHAR(16)  NOT NULL,   -- 成員機構ID
    member_name     VARCHAR(200),
    relationship    VARCHAR(32),             -- SUBSIDIARY=子公司 / BRANCH=分支機構 / AFFILIATE=聯營
    effective_date  DATE         NOT NULL DEFAULT '2000-01-01',
    expiry_date     DATE         DEFAULT '9999-12-31',
    PRIMARY KEY (group_id, member_id)
);
COMMENT ON TABLE  fsi.mktdata_institution_group IS '機構集團關係：集團母公司與各子公司，計算SFC規定的集團敞口上限（≤20% NAV）';
COMMENT ON COLUMN fsi.mktdata_institution_group.group_id IS '集團頂層母公司ID，計算集團敞口時以此為聚合鍵';

CREATE INDEX IF NOT EXISTS idx_mkt_inst_grp_member ON fsi.mktdata_institution_group(member_id);

-- ============================================================
-- PART D: transact_ 補充（交易層）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- D1. 銀行間債券交易
--   源：T_Transact_Bond_Interbank
--   說明：銀行間市場債券買賣，帶交易商ID和報告ID，
--         監管報告（PBOC/SAFE）需要
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_bond_interbank (
    txn_id              BIGSERIAL    PRIMARY KEY,
    source_txn_id       VARCHAR(64),                  -- 銀行間原始成交ID（ExecID）
    port_id             VARCHAR(16)  NOT NULL,
    trade_date          DATE         NOT NULL,
    interbank_member_id VARCHAR(16),                  -- 銀行間市場成員代碼
    security_code       VARCHAR(32)  NOT NULL,
    security_name       VARCHAR(200),
    asset_type          VARCHAR(16),                  -- BOND/CD/CP/ABS
    direction           fsi.trade_direction NOT NULL,
    txn_type            VARCHAR(16),                  -- OUTRIGHT=現券 / PLEDGED=質押式
    counterparty_id     VARCHAR(16),
    counterparty_ib_id  VARCHAR(16),                  -- 對手方銀行間成員代碼
    counterparty_name   VARCHAR(200),
    currency            CHAR(3)      NOT NULL,
    price               NUMERIC(24,8),
    quantity            NUMERIC(20,4) NOT NULL,
    accrued_interest    NUMERIC(24,2),
    amount              NUMERIC(24,2),
    yield               NUMERIC(12,8),                -- 成交收益率
    exec_id             VARCHAR(64),                  -- 銀行間成交確認號
    status              fsi.txn_status NOT NULL DEFAULT 'CONFIRMED',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  fsi.transact_bond_interbank IS '銀行間債券交易：含銀行間成員代碼和執行ID，PBOC/CFETS監管報送必需字段';
COMMENT ON COLUMN fsi.transact_bond_interbank.exec_id IS '銀行間市場（CFETS）成交確認號，監管核查和對賬使用';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_ib_bond_src ON fsi.transact_bond_interbank(exec_id) WHERE exec_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_ib_bond_date  ON fsi.transact_bond_interbank(port_id, trade_date DESC);

-- ────────────────────────────────────────────────────────────
-- D2. 銀行間回購交易
--   源：T_Transact_Repo_Interbank
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_repo_interbank (
    txn_id              BIGSERIAL    PRIMARY KEY,
    source_txn_id       VARCHAR(64),
    port_id             VARCHAR(16)  NOT NULL,
    trade_date          DATE         NOT NULL,
    interbank_member_id VARCHAR(16),
    repo_type           VARCHAR(8)   NOT NULL,  -- REPO=正回購 / REV_REPO=逆回購
    pledged_bond_code   VARCHAR(32),             -- 質押券代碼
    counterparty_id     VARCHAR(16),
    counterparty_ib_id  VARCHAR(16),
    counterparty_name   VARCHAR(200),
    currency            CHAR(3)      NOT NULL,
    value_date          DATE         NOT NULL,
    maturity_date       DATE         NOT NULL,
    interest_days       INTEGER,
    actual_maturity_date DATE,                   -- 提前終止時實際到期日
    amount              NUMERIC(24,2) NOT NULL,
    yield               NUMERIC(12,8),
    interest            NUMERIC(24,2),
    exec_id             VARCHAR(64),
    status              fsi.txn_status NOT NULL DEFAULT 'CONFIRMED',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.transact_repo_interbank IS '銀行間回購交易：含質押券代碼和執行ID，CFETS/PBOC監管報送字段';

CREATE UNIQUE INDEX IF NOT EXISTS uidx_txn_ib_repo_src ON fsi.transact_repo_interbank(exec_id) WHERE exec_id IS NOT NULL;
CREATE INDEX        IF NOT EXISTS idx_txn_ib_repo_date  ON fsi.transact_repo_interbank(port_id, trade_date DESC);
CREATE INDEX        IF NOT EXISTS idx_txn_ib_repo_mat   ON fsi.transact_repo_interbank(maturity_date) WHERE status='CONFIRMED';

-- ────────────────────────────────────────────────────────────
-- D4. 組合每日NAV變動流水
--   源：TRN.T_Transact_Portfolio_Asset
--   說明：比 balance_portfolio_delta 更細，含申購/贖回/股息等各項
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.transact_portfolio_cashflow (
    evaluate_date   DATE         NOT NULL,
    port_id         VARCHAR(16)  NOT NULL,
    currency        CHAR(3)      NOT NULL,
    net_asset       NUMERIC(24,2),           -- 當日NAV
    profit_loss     NUMERIC(24,2),           -- 當日損益
    purchase        NUMERIC(24,2),           -- 申購金額
    redemption      NUMERIC(24,2),           -- 贖回金額
    net_purchase    NUMERIC(24,2),           -- 淨申購
    dividend        NUMERIC(24,2),           -- 分紅支出
    adj_amount      NUMERIC(24,2),           -- 其他調整
    prev_net_asset  NUMERIC(24,2),
    delta_net_asset NUMERIC(24,2),           -- 當日NAV變動
    data_source     VARCHAR(32)  NOT NULL DEFAULT 'VALUATION',
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, currency)
);
COMMENT ON TABLE  fsi.transact_portfolio_cashflow IS '組合現金流水：每日申購/贖回/損益/分紅明細，NAV驗算和份額登記的數據基礎';

CREATE INDEX IF NOT EXISTS idx_txn_pcf_port_date ON fsi.transact_portfolio_cashflow(port_id, evaluate_date DESC);

-- ============================================================
-- PART E: svc_ 補充（服務層）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- E1. 風控預警事件記錄
--   源：T_Para_RiskAlert（配置） → 此為事件日誌
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_risk_alert_event (
    event_id        BIGSERIAL    PRIMARY KEY,
    event_time      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    port_id         VARCHAR(16)  NOT NULL,
    as_of_date      DATE         NOT NULL,
    alert_type      VARCHAR(32)  NOT NULL,   -- WAM_BREACH/SINGLE_ISSUER/VAR_LIMIT/DRAWDOWN
    alert_level     VARCHAR(8)   NOT NULL,   -- INFO/WARNING/CRITICAL
    dimension       VARCHAR(64),             -- 觸發維度（發行人名稱/資產類別等）
    actual_value    NUMERIC(16,6),           -- 實際值
    limit_value     NUMERIC(16,6),           -- 限制值
    limit_source    VARCHAR(16),             -- REGULATORY/INTERNAL/CONTRACT
    description     TEXT,
    is_resolved     BOOLEAN      NOT NULL DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    resolved_by     VARCHAR(64),
    review_id       UUID                     -- 關聯審核請求（如已觸發審核）
);
COMMENT ON TABLE  fsi.svc_risk_alert_event IS '[Layer3] 風控預警事件：計算引擎觸發的所有風控預警記錄，與審核工作流聯動';
COMMENT ON COLUMN fsi.svc_risk_alert_event.limit_source IS 'REGULATORY=監管限制 / INTERNAL=內部限制 / CONTRACT=合同限制';

CREATE INDEX IF NOT EXISTS idx_svc_alert_port_date ON fsi.svc_risk_alert_event(port_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_svc_alert_unresolved ON fsi.svc_risk_alert_event(is_resolved, alert_level) WHERE NOT is_resolved;

-- ────────────────────────────────────────────────────────────
-- E2. 個券超額收益監控
--   源：T_Monitor_Security_ExcessReturn
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_monitor_excess_return (
    evaluate_date       DATE         NOT NULL,
    port_id             VARCHAR(16)  NOT NULL,
    security_code       VARCHAR(32)  NOT NULL,
    base_market_value   NUMERIC(24,2),           -- 期初市值（計算貢獻的基礎）
    security_pnl        NUMERIC(24,2),           -- 個券實際損益
    benchmark_id        VARCHAR(32),             -- 對比基準ID
    benchmark_return    NUMERIC(16,8),           -- 基準同期收益率
    excess_return       NUMERIC(16,8),           -- 超額收益 = 個券收益率 - 基準收益率
    contribution        NUMERIC(16,8),           -- 對組合超額收益的貢獻
    PRIMARY KEY (evaluate_date, port_id, security_code, benchmark_id)
);
COMMENT ON TABLE  fsi.svc_monitor_excess_return IS '[Layer3] 個券超額收益：每只持倉相對基準的超額收益貢獻，股票組合業績歸因核心數據';
COMMENT ON COLUMN fsi.svc_monitor_excess_return.contribution IS '個券對組合整體超額收益的貢獻 = 個券超額收益 × 倉位權重';

CREATE INDEX IF NOT EXISTS idx_svc_exc_ret_port_date ON fsi.svc_monitor_excess_return(port_id, evaluate_date DESC);
CREATE INDEX IF NOT EXISTS idx_svc_exc_ret_security  ON fsi.svc_monitor_excess_return(security_code, evaluate_date DESC);
