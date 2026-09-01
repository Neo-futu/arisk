-- ============================================================
-- 016_data_management_workbench.sql  數據管理工作台
-- 涵蓋：模擬交易草稿、前置風控結果與可追溯狀態
-- 依賴：001_schema_init.sql · 003_para.sql · 008_workflow.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS fsi.transact_simulated_order (
    order_id          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    port_id           VARCHAR(16)   NOT NULL,
    as_of_date        DATE          NOT NULL,
    trade_date        DATE          NOT NULL,
    trade_side        VARCHAR(4)    NOT NULL CHECK (trade_side IN ('BUY', 'SELL')),
    asset_class       VARCHAR(32)   NOT NULL,
    security_code     VARCHAR(32)   NOT NULL,
    security_name     VARCHAR(200),
    issuer_name       VARCHAR(200),
    currency          CHAR(3)       NOT NULL,
    quantity          NUMERIC(20,4),
    price             NUMERIC(24,8),
    trade_amount      NUMERIC(24,2) NOT NULL CHECK (trade_amount > 0),
    duration_years    NUMERIC(8,4)  NOT NULL DEFAULT 0 CHECK (duration_years >= 0),
    status            VARCHAR(16)   NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'VALIDATED', 'WARNING', 'BLOCKED', 'CANCELLED')),
    decision          VARCHAR(32),
    breach_flags      JSONB         NOT NULL DEFAULT '[]'::jsonb,
    validation_result JSONB,
    notes             TEXT,
    created_by        VARCHAR(128)  NOT NULL,
    updated_by        VARCHAR(128),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE fsi.transact_simulated_order IS
    '模擬交易工作台：僅用於交易前試算，不代表真實委託或成交；驗證結果由確定性風控引擎生成。';
COMMENT ON COLUMN fsi.transact_simulated_order.status IS
    'DRAFT=草稿 / VALIDATED=通過 / WARNING=帶警告通過 / BLOCKED=阻止 / CANCELLED=取消';
COMMENT ON COLUMN fsi.transact_simulated_order.validation_result IS
    '最近一次前置風控完整結果快照，用於解釋、重現與審計。';

CREATE INDEX IF NOT EXISTS idx_sim_order_port_date
    ON fsi.transact_simulated_order(port_id, as_of_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sim_order_status
    ON fsi.transact_simulated_order(status, updated_at DESC);