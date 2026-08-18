-- ARISK 规则应用配置
-- 将三类规则绑定到组合/交易/前置/后置场景，支持生效期与优先级。

CREATE TABLE IF NOT EXISTS fsi.para_risk_rule_application (
    application_id BIGSERIAL PRIMARY KEY,
    rule_type VARCHAR(16) NOT NULL,
    rule_id BIGINT NOT NULL,
    apply_scope VARCHAR(24) NOT NULL,
    port_id VARCHAR(16),
    strategy_code VARCHAR(64),
    instrument_type VARCHAR(32),
    trade_side VARCHAR(8),
    priority INTEGER NOT NULL DEFAULT 100,
    effective_date DATE NOT NULL,
    expiry_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    note TEXT,
    created_by VARCHAR(64),
    updated_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_rule_app_type CHECK (rule_type IN ('regulatory', 'contract', 'internal')),
    CONSTRAINT ck_rule_app_scope CHECK (apply_scope IN ('portfolio', 'trade', 'pretrade', 'posttrade')),
    CONSTRAINT ck_rule_app_side CHECK (trade_side IN ('BUY', 'SELL', 'BOTH') OR trade_side IS NULL),
    CONSTRAINT ck_rule_app_date CHECK (expiry_date IS NULL OR expiry_date >= effective_date)
);

CREATE INDEX IF NOT EXISTS idx_rule_app_rule
    ON fsi.para_risk_rule_application(rule_type, rule_id);

CREATE INDEX IF NOT EXISTS idx_rule_app_scope_active
    ON fsi.para_risk_rule_application(apply_scope, is_active, effective_date, expiry_date);

CREATE INDEX IF NOT EXISTS idx_rule_app_port
    ON fsi.para_risk_rule_application(port_id, is_active);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_application_binding
    ON fsi.para_risk_rule_application(
        rule_type,
        rule_id,
        apply_scope,
        COALESCE(port_id, ''),
        COALESCE(strategy_code, ''),
        COALESCE(instrument_type, ''),
        COALESCE(trade_side, ''),
        effective_date
    );

-- 保持既有合规业务连续：现有规则首次迁移时建立默认“组合”绑定。
-- 后续新增规则不会自动生效，必须在“规则应用配置”中显式绑定。
INSERT INTO fsi.para_risk_rule_application
    (rule_type, rule_id, apply_scope, port_id, priority, effective_date,
     expiry_date, is_active, note)
SELECT 'regulatory', r.limit_id, 'portfolio', r.port_id, 100,
       r.effective_date, r.expiry_date, r.is_active, '迁移生成的默认组合绑定'
FROM fsi.para_risk_limit_regulatory r
WHERE NOT EXISTS (
    SELECT 1 FROM fsi.para_risk_rule_application a
    WHERE a.rule_type='regulatory' AND a.rule_id=r.limit_id
      AND a.apply_scope='portfolio' AND a.port_id=r.port_id
      AND a.effective_date=r.effective_date
);

INSERT INTO fsi.para_risk_rule_application
    (rule_type, rule_id, apply_scope, port_id, priority, effective_date,
     expiry_date, is_active, note)
SELECT 'contract', r.limit_id, 'portfolio', r.port_id, 100,
       r.begin_date, r.end_date, r.is_active, '迁移生成的默认组合绑定'
FROM fsi.para_risk_limit_contract r
WHERE NOT EXISTS (
    SELECT 1 FROM fsi.para_risk_rule_application a
    WHERE a.rule_type='contract' AND a.rule_id=r.limit_id
      AND a.apply_scope='portfolio' AND a.port_id=r.port_id
      AND a.effective_date=r.begin_date
);

INSERT INTO fsi.para_risk_rule_application
    (rule_type, rule_id, apply_scope, port_id, priority, effective_date,
     expiry_date, is_active, note)
SELECT 'internal', r.limit_id, 'portfolio', r.port_id, 100,
       r.begin_date, r.end_date, r.is_active, '迁移生成的默认组合绑定'
FROM fsi.para_risk_limit_internal r
WHERE NOT EXISTS (
    SELECT 1 FROM fsi.para_risk_rule_application a
    WHERE a.rule_type='internal' AND a.rule_id=r.limit_id
      AND a.apply_scope='portfolio' AND a.port_id=r.port_id
      AND a.effective_date=r.begin_date
);

COMMENT ON TABLE fsi.para_risk_rule_application IS '规则应用配置：将规则绑定到组合/交易场景';
COMMENT ON COLUMN fsi.para_risk_rule_application.apply_scope IS '应用范围：portfolio/trade/pretrade/posttrade';
COMMENT ON COLUMN fsi.para_risk_rule_application.priority IS '优先级，数值越小优先级越高';

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE fsi.para_risk_rule_application TO fsi_user;
GRANT USAGE, SELECT ON SEQUENCE fsi.para_risk_rule_application_application_id_seq TO fsi_user;
