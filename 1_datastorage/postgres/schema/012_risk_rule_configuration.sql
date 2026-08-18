-- ARISK 統一風控規則配置增量遷移
-- 三類規則沿用既有 FSI 業務表，補齊統一 CRUD、審計和合同規則識別字段。

-- 監管規則
ALTER TABLE fsi.para_risk_limit_regulatory
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(64),
    ADD COLUMN IF NOT EXISTS updated_by VARCHAR(64),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 內部規則
ALTER TABLE fsi.para_risk_limit_internal
    ADD COLUMN IF NOT EXISTS limit_name_en VARCHAR(200),
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(64),
    ADD COLUMN IF NOT EXISTS updated_by VARCHAR(64),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- 合同規則原表沒有統一規則代碼/名稱，先補欄位並兼容已有數據。
ALTER TABLE fsi.para_risk_limit_contract
    ADD COLUMN IF NOT EXISTS rule_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS rule_name VARCHAR(200),
    ADD COLUMN IF NOT EXISTS rule_name_en VARCHAR(200),
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(64),
    ADD COLUMN IF NOT EXISTS updated_by VARCHAR(64),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE fsi.para_risk_limit_contract
SET rule_code = COALESCE(rule_code, 'CONTRACT_' || limit_id::text),
    rule_name = COALESCE(rule_name, mandate_ref || COALESCE(' / ' || clause_ref, ''))
WHERE rule_code IS NULL OR rule_name IS NULL;

ALTER TABLE fsi.para_risk_limit_contract
    ALTER COLUMN rule_code SET NOT NULL,
    ALTER COLUMN rule_name SET NOT NULL;

-- 同一基金、同一规则代碼、同一生效日只允許一條，避免配置重複。
CREATE UNIQUE INDEX IF NOT EXISTS uq_reg_rule_port_code_date
    ON fsi.para_risk_limit_regulatory(port_id, rule_code, effective_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_int_rule_port_code_date
    ON fsi.para_risk_limit_internal(port_id, limit_code, begin_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_contract_rule_port_code_date
    ON fsi.para_risk_limit_contract(port_id, rule_code, begin_date);

CREATE INDEX IF NOT EXISTS idx_reg_rule_active_date
    ON fsi.para_risk_limit_regulatory(is_active, effective_date, expiry_date);
CREATE INDEX IF NOT EXISTS idx_int_rule_active_date
    ON fsi.para_risk_limit_internal(is_active, begin_date, end_date);
CREATE INDEX IF NOT EXISTS idx_contract_rule_active_date
    ON fsi.para_risk_limit_contract(is_active, begin_date, end_date);

-- 为当前在管基金初始化 SFC MMF 基线规则；已有同代码同生效日配置时不覆盖。
INSERT INTO fsi.para_risk_limit_regulatory
    (port_id, regulation_src, rule_code, rule_name, rule_name_en,
     dimension, limit_value, limit_unit, limit_direction,
     clause_ref, effective_date, is_active, description)
SELECT p.port_id, r.regulation_src, r.rule_code, r.rule_name, r.rule_name_en,
       r.dimension, r.limit_value, r.limit_unit, r.limit_direction,
       r.clause_ref, DATE '2024-01-01', TRUE, r.description
FROM fsi.para_portfolio p
CROSS JOIN (
    VALUES
      ('SFC_MMF_CODE', 'MMF_WAM', '加權平均期限', 'Weighted Average Maturity', 'WAM', 60.0, 'DAYS', 'MAX', 'SFC UT Code 8.2', 'WAM 不得超過 60 天'),
      ('SFC_MMF_CODE', 'MMF_WAL', '加權平均有效期', 'Weighted Average Life', 'WAL', 120.0, 'DAYS', 'MAX', 'SFC UT Code 8.2', 'WAL 不得超過 120 天'),
      ('SFC_MMF_CODE', 'MMF_DAILY_LIQUID', '每日流動資產', 'Daily Liquid Assets', 'LIQUIDITY', 7.5, 'PCT', 'MIN', 'SFC UT Code 8.2', '每日流動資產不得低於 7.5% NAV'),
      ('SFC_MMF_CODE', 'MMF_WEEKLY_LIQUID', '每週流動資產', 'Weekly Liquid Assets', 'LIQUIDITY', 15.0, 'PCT', 'MIN', 'SFC UT Code 8.2', '每週流動資產不得低於 15% NAV'),
      ('SFC_MMF_CODE', 'MMF_SINGLE_ISSUER', '單一發行人集中度', 'Single Issuer Concentration', 'ISSUER', 10.0, 'PCT', 'MAX', 'SFC UT Code 8.2', '單一發行人暴露不得超過 10% NAV'),
      ('SFC_MMF_CODE', 'MMF_ISSUER_GROUP', '發行人集團集中度', 'Issuer Group Concentration', 'ISSUER_GROUP', 20.0, 'PCT', 'MAX', 'SFC UT Code 8.2', '同一集團暴露不得超過 20% NAV')
) AS r(regulation_src, rule_code, rule_name, rule_name_en, dimension,
       limit_value, limit_unit, limit_direction, clause_ref, description)
WHERE p.is_active = TRUE
ON CONFLICT (port_id, rule_code, effective_date) DO NOTHING;

COMMENT ON COLUMN fsi.para_risk_limit_contract.rule_code IS '合同規則統一代碼，用於配置、檢查和違規結果關聯';
COMMENT ON COLUMN fsi.para_risk_limit_contract.rule_name IS '合同規則顯示名稱';
COMMENT ON COLUMN fsi.para_risk_limit_regulatory.updated_at IS '規則最後更新時間';
COMMENT ON COLUMN fsi.para_risk_limit_internal.updated_at IS '規則最後更新時間';
COMMENT ON COLUMN fsi.para_risk_limit_contract.updated_at IS '規則最後更新時間';
