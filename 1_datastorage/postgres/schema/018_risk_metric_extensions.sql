-- ============================================================
-- 018_risk_metric_extensions.sql
-- 投资者 sponsor、发行人舆情、关联方。信用定价/停牌/条款/风格/发行人主体见 019。
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 投资者 / sponsor 主数据，关联持有人排名与申赎流水
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.para_sponsor (
    sponsor_id        VARCHAR(32)  PRIMARY KEY,
    sponsor_name      VARCHAR(200) NOT NULL,
    sponsor_type      VARCHAR(16)  NOT NULL,   -- INSTITUTIONAL / RETAIL / RELATED
    country           CHAR(2),
    institution_id    VARCHAR(16),
    is_related_party  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.para_sponsor IS '投资者（sponsor）主数据：机构/零售持有人，关联份额排名与申赎';
COMMENT ON COLUMN fsi.para_sponsor.sponsor_type IS 'INSTITUTIONAL=机构 / RETAIL=零售 / RELATED=关联方';

CREATE INDEX IF NOT EXISTS idx_para_sponsor_type ON fsi.para_sponsor(sponsor_type);
CREATE INDEX IF NOT EXISTS idx_para_sponsor_inst ON fsi.para_sponsor(institution_id);

ALTER TABLE fsi.balance_holder_rank
    ADD COLUMN IF NOT EXISTS sponsor_id VARCHAR(32);

COMMENT ON COLUMN fsi.balance_holder_rank.sponsor_id IS '关联 fsi.para_sponsor.sponsor_id';

-- 由已有持有人排名回填 sponsor，保证外键可建
INSERT INTO fsi.para_sponsor (sponsor_id, sponsor_name, sponsor_type, country, is_related_party)
SELECT holder_id,
       COALESCE(MAX(holder_name), holder_id),
       CASE WHEN MIN(rank_no) <= 8 THEN 'INSTITUTIONAL' ELSE 'RETAIL' END,
       'HK',
       BOOL_OR(holder_id = 'H001')
FROM fsi.balance_holder_rank
WHERE holder_id IS NOT NULL
GROUP BY holder_id
ON CONFLICT (sponsor_id) DO UPDATE
    SET sponsor_name = EXCLUDED.sponsor_name,
        sponsor_type = EXCLUDED.sponsor_type,
        is_related_party = EXCLUDED.is_related_party;

UPDATE fsi.balance_holder_rank
SET sponsor_id = holder_id
WHERE sponsor_id IS NULL
  AND holder_id IN (SELECT sponsor_id FROM fsi.para_sponsor);

DO $$ BEGIN
    ALTER TABLE fsi.balance_holder_rank
        ADD CONSTRAINT fk_holder_rank_sponsor
        FOREIGN KEY (sponsor_id) REFERENCES fsi.para_sponsor(sponsor_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_holder_rank_sponsor ON fsi.balance_holder_rank(sponsor_id);

-- 申赎流水的 investor_id 对齐 sponsor（仅当无孤儿键时加外键）
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM fsi.transact_subscription s
        WHERE s.investor_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM fsi.para_sponsor p WHERE p.sponsor_id = s.investor_id)
    ) THEN
        BEGIN
            ALTER TABLE fsi.transact_subscription
                ADD CONSTRAINT fk_subscription_sponsor
                FOREIGN KEY (investor_id) REFERENCES fsi.para_sponsor(sponsor_id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END;
    END IF;
END $$;

-- ────────────────────────────────────────────────────────────
-- 发行人负面舆情
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.mktdata_issuer_news (
    news_id        BIGSERIAL    PRIMARY KEY,
    issuer_id      VARCHAR(16),
    security_code  VARCHAR(32),
    news_date      DATE         NOT NULL,
    category       VARCHAR(32)  NOT NULL,  -- CREDIT/MARKET/FINANCIAL/GUARANTEE/REGULATORY
    severity       VARCHAR(16)  NOT NULL,  -- INFO/NEGATIVE/SEVERE
    headline       VARCHAR(300) NOT NULL,
    source         VARCHAR(64),
    loaded_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.mktdata_issuer_news IS '发行人舆情：信用、市场、财务、担保、监管等负面信息';

CREATE INDEX IF NOT EXISTS idx_issuer_news_date ON fsi.mktdata_issuer_news(news_date DESC, issuer_id);
CREATE INDEX IF NOT EXISTS idx_issuer_news_sec  ON fsi.mktdata_issuer_news(security_code, news_date DESC);

-- 组合关联方（关联交易持仓限制）
CREATE TABLE IF NOT EXISTS fsi.para_port_related_party (
    port_id          VARCHAR(16) NOT NULL,
    institution_id   VARCHAR(16) NOT NULL,
    relationship     VARCHAR(32) NOT NULL,
    begin_date       DATE        NOT NULL DEFAULT DATE '2000-01-01',
    end_date         DATE,
    PRIMARY KEY (port_id, institution_id, begin_date)
);
COMMENT ON TABLE fsi.para_port_related_party IS '组合关联方清单：用于关联交易持仓限制';

-- ────────────────────────────────────────────────────────────
-- 用现有持仓/行情补齐可计算字段（幂等，不覆盖已有非空值）
-- ────────────────────────────────────────────────────────────
UPDATE fsi.mktdata_quotes
SET pe_ratio = 18.6, pb_ratio = 3.4
WHERE security_code = '0700.HK' AND pe_ratio IS NULL;

UPDATE fsi.mktdata_quotes
SET pe_ratio = 22.4, pb_ratio = 2.1
WHERE security_code = '9988.HK' AND pe_ratio IS NULL;

UPDATE fsi.mktdata_stock_static
SET country = COALESCE(country, 'HK'),
    shares_outstanding = COALESCE(shares_outstanding, 9500000000),
    free_float_shares = COALESCE(free_float_shares, 9100000000)
WHERE security_code = '0700.HK';

INSERT INTO fsi.mktdata_stock_static (
    internal_id, security_code, security_name, market_id, currency, country,
    shares_outstanding, free_float_shares, is_active
) VALUES (
    'STK_9988_HK', '9988.HK', '阿里巴巴', 'HKEX', 'HKD', 'HK',
    2000000000, 1900000000, TRUE
)
ON CONFLICT (internal_id) DO UPDATE
    SET country = COALESCE(fsi.mktdata_stock_static.country, EXCLUDED.country),
        shares_outstanding = COALESCE(fsi.mktdata_stock_static.shares_outstanding, EXCLUDED.shares_outstanding),
        free_float_shares = COALESCE(fsi.mktdata_stock_static.free_float_shares, EXCLUDED.free_float_shares);

UPDATE fsi.balance_stock s
SET country = COALESCE(s.country, st.country, 'HK')
FROM fsi.mktdata_stock_static st
WHERE st.security_code = s.security_code
  AND s.country IS NULL;

UPDATE fsi.balance_bond
SET country = COALESCE(country, CASE currency WHEN 'CNY' THEN 'CN' WHEN 'USD' THEN 'US' ELSE 'HK' END)
WHERE country IS NULL;

INSERT INTO fsi.para_institution (
    institution_id, institution_name, institution_type, country
) VALUES
    ('BOCHK', '中国银行(香港)', 'BANK', 'HK'),
    ('HSBC',  '汇丰银行',       'BANK', 'HK'),
    ('SCB',   '渣打银行',       'BANK', 'HK')
ON CONFLICT (institution_id) DO NOTHING;

INSERT INTO fsi.para_counterparty (
    counterparty_id, counterparty_name, institution_id, country, credit_rating, credit_limit, credit_limit_ccy
) VALUES
    ('BOCHK', '中国银行(香港)', 'BOCHK', 'HK', 'AA-', 200000000, 'HKD'),
    ('HSBC',  '汇丰银行',       'HSBC',  'HK', 'AA-', 250000000, 'HKD'),
    ('SCB',   '渣打银行',       'SCB',   'HK', 'A+',  150000000, 'HKD')
ON CONFLICT (counterparty_id) DO UPDATE
    SET credit_limit = COALESCE(fsi.para_counterparty.credit_limit, EXCLUDED.credit_limit),
        institution_id = COALESCE(fsi.para_counterparty.institution_id, EXCLUDED.institution_id);

INSERT INTO fsi.mktdata_institution_group (group_id, group_name, member_id, member_name, relationship)
VALUES
    ('BOC_GROUP',  '中银集团', 'BOCHK', '中国银行(香港)', 'SUBSIDIARY'),
    ('HSBC_GROUP', '汇丰集团', 'HSBC',  '汇丰银行',       'SUBSIDIARY'),
    ('SCB_GROUP',  '渣打集团', 'SCB',   '渣打银行',       'SUBSIDIARY')
ON CONFLICT (group_id, member_id) DO NOTHING;

UPDATE fsi.balance_bond
SET issuer_id = COALESCE(issuer_id, 'HSBC')
WHERE issuer_id IS NULL;

UPDATE fsi.balance_deposit
SET bank_id = COALESCE(bank_id, 'HSBC')
WHERE bank_id IS NULL;

INSERT INTO fsi.para_port_related_party (port_id, institution_id, relationship)
SELECT p.port_id, 'HSBC', 'CUSTODIAN_AFFILIATE'
FROM fsi.para_portfolio p
WHERE p.port_id IN ('BHMMF001', 'BHMMF002')
ON CONFLICT DO NOTHING;

INSERT INTO fsi.mktdata_issuer_news (issuer_id, security_code, news_date, category, severity, headline, source)
SELECT 'HSBC', NULL, DATE '2026-06-20', 'CREDIT', 'NEGATIVE', '发行人外部评级展望调整为负面', 'MARKET'
WHERE NOT EXISTS (
    SELECT 1 FROM fsi.mktdata_issuer_news
    WHERE issuer_id = 'HSBC' AND news_date = DATE '2026-06-20' AND headline = '发行人外部评级展望调整为负面'
);

INSERT INTO fsi.transact_portfolio_cashflow (
    evaluate_date, port_id, currency, net_asset, profit_loss, purchase, redemption, net_purchase, data_source
)
SELECT DATE '2026-06-25', n.port_id, p.base_currency, n.net_asset, 0,
       8000000, 15000000, -7000000, 'SEED'
FROM fsi.balance_portfolio_nav n
JOIN fsi.para_portfolio p ON p.port_id = n.port_id
WHERE n.port_id IN ('BHMMF001', 'BHMMF002')
  AND n.evaluate_date = DATE '2026-06-25'
ON CONFLICT (evaluate_date, port_id, currency) DO NOTHING;

INSERT INTO fsi.transact_subscription (
    port_id, confirm_date, direction, investor_id, investor_name, currency, amount, net_amount
)
SELECT 'BHMMF001', DATE '2026-06-24', 'SELL', 'H001', s.sponsor_name, 'HKD', 9000000, 9000000
FROM fsi.para_sponsor s
WHERE s.sponsor_id = 'H001'
  AND NOT EXISTS (
      SELECT 1 FROM fsi.transact_subscription
      WHERE port_id = 'BHMMF001' AND confirm_date = DATE '2026-06-24' AND investor_id = 'H001' AND direction = 'SELL'
  );

INSERT INTO fsi.svc_wf_review_request (
    category, status, triggered_by, port_id, as_of_date, title, summary, priority
)
SELECT 'HIGH_RISK', 'PENDING', 'risk-metric', 'BHMMF001', DATE '2026-06-25',
       '存款银行限额预警', '存款集中度接近内部银行限额，待人工确认。', 2
WHERE NOT EXISTS (
    SELECT 1 FROM fsi.svc_wf_review_request
    WHERE port_id = 'BHMMF001' AND title = '存款银行限额预警'
);
