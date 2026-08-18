-- ARISK 风控规则附件能力
-- 支持监管/合同/内部规则上传 Word/PDF 等证明材料。

CREATE TABLE IF NOT EXISTS fsi.para_risk_rule_attachment (
    attachment_id BIGSERIAL PRIMARY KEY,
    rule_type VARCHAR(16) NOT NULL,
    rule_id BIGINT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    file_size BIGINT NOT NULL CHECK (file_size > 0),
    file_data BYTEA NOT NULL,
    note TEXT,
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_risk_rule_attachment_type CHECK (rule_type IN ('regulatory', 'contract', 'internal'))
);

CREATE INDEX IF NOT EXISTS idx_risk_rule_attachment_rule
    ON fsi.para_risk_rule_attachment(rule_type, rule_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_risk_rule_attachment_created_at
    ON fsi.para_risk_rule_attachment(created_at DESC);

COMMENT ON TABLE fsi.para_risk_rule_attachment IS '风控规则附件（监管/合同/内部）';
COMMENT ON COLUMN fsi.para_risk_rule_attachment.rule_type IS '规则类型：regulatory/contract/internal';
COMMENT ON COLUMN fsi.para_risk_rule_attachment.rule_id IS '对应规则ID（按 rule_type 路由到对应表）';
COMMENT ON COLUMN fsi.para_risk_rule_attachment.file_data IS '附件二进制内容';

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE fsi.para_risk_rule_attachment TO fsi_user;
GRANT USAGE, SELECT ON SEQUENCE fsi.para_risk_rule_attachment_attachment_id_seq TO fsi_user;
