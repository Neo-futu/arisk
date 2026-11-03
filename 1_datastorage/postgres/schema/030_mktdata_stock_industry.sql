-- ============================================================
-- 030_mktdata_stock_industry.sql
-- 个股行业独立成表：支持多分类标准 + 行业 code；静态表不再作为行业权威源。
-- ============================================================

CREATE TABLE IF NOT EXISTS fsi.mktdata_industry_standard_def (
    standard_code   VARCHAR(16)  PRIMARY KEY,   -- GICS/CSRC/SW/CITIC/WIND
    standard_name   VARCHAR(120) NOT NULL,
    provider        VARCHAR(64),
    description     TEXT,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE fsi.mktdata_industry_standard_def IS '行业分类标准字典：GICS/证监会/申万/中信/Wind 等';

INSERT INTO fsi.mktdata_industry_standard_def (standard_code, standard_name, provider, description) VALUES
    ('GICS',  'Global Industry Classification Standard', 'MSCI/S&P', '全球行业分类'),
    ('CSRC',  '中国证监会行业分类', 'CSRC', '中国上市公司行业分类'),
    ('SW',    '申万行业分类', 'SW', '申万一级至三级行业'),
    ('CITIC', '中信行业分类', 'CITIC', '中信证券行业分类'),
    ('WIND',  'Wind 行业分类', 'WIND', '万得行业分类')
ON CONFLICT (standard_code) DO UPDATE
SET standard_name = EXCLUDED.standard_name,
    provider = EXCLUDED.provider,
    description = EXCLUDED.description,
    is_active = TRUE;

CREATE TABLE IF NOT EXISTS fsi.mktdata_stock_industry (
    security_code   VARCHAR(32)  NOT NULL,
    internal_id     VARCHAR(32),
    standard        VARCHAR(16)  NOT NULL REFERENCES fsi.mktdata_industry_standard_def(standard_code),
    industry_code   VARCHAR(32)  NOT NULL,          -- 叶子或主用行业代码
    industry_name   VARCHAR(120) NOT NULL,
    level1_code     VARCHAR(32),
    level1_name     VARCHAR(120),
    level2_code     VARCHAR(32),
    level2_name     VARCHAR(120),
    level3_code     VARCHAR(32),
    level3_name     VARCHAR(120),
    level4_code     VARCHAR(32),
    level4_name     VARCHAR(120),
    begin_date      DATE         NOT NULL DEFAULT DATE '1900-01-01',
    end_date        DATE,                           -- NULL=仍有效
    is_primary      BOOLEAN      NOT NULL DEFAULT TRUE,
    data_source     VARCHAR(16)  NOT NULL DEFAULT 'WIND',
    loaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (security_code, standard, industry_code, begin_date)
);

COMMENT ON TABLE fsi.mktdata_stock_industry IS '个股行业映射：一券可挂多标准；含行业 code 与层级名称';
COMMENT ON COLUMN fsi.mktdata_stock_industry.industry_code IS '行业代码（该标准下主用/叶子代码）';
COMMENT ON COLUMN fsi.mktdata_stock_industry.standard IS '分类标准：GICS/CSRC/SW/CITIC/WIND';
COMMENT ON COLUMN fsi.mktdata_stock_industry.is_primary IS '同一标准下是否主分类（归因默认取主分类）';

CREATE INDEX IF NOT EXISTS idx_mkt_stock_ind_code
    ON fsi.mktdata_stock_industry (industry_code, standard);
CREATE INDEX IF NOT EXISTS idx_mkt_stock_ind_sec_std
    ON fsi.mktdata_stock_industry (security_code, standard, begin_date DESC);
CREATE INDEX IF NOT EXISTS idx_mkt_stock_ind_primary
    ON fsi.mktdata_stock_industry (security_code, standard)
    WHERE is_primary AND end_date IS NULL;

-- 当前有效主行业（默认 GICS 优先由查询侧排序）
CREATE OR REPLACE VIEW fsi.v_mktdata_stock_industry_current AS
SELECT DISTINCT ON (security_code, standard)
    security_code,
    internal_id,
    standard,
    industry_code,
    industry_name,
    level1_code,
    level1_name,
    level2_code,
    level2_name,
    level3_code,
    level3_name,
    level4_code,
    level4_name,
    begin_date,
    end_date,
    is_primary,
    data_source
FROM fsi.mktdata_stock_industry
WHERE end_date IS NULL
ORDER BY security_code, standard, is_primary DESC, begin_date DESC;

COMMENT ON VIEW fsi.v_mktdata_stock_industry_current IS '个股当前有效行业（按标准）；归因默认再优先 GICS';

-- 从静态表回填（仅名称时生成稳定 code；中文名用 MD5 短码；按 security_code 去重）
INSERT INTO fsi.mktdata_stock_industry (
    security_code, internal_id, standard,
    industry_code, industry_name,
    level1_code, level1_name,
    level2_code, level2_name,
    begin_date, end_date, is_primary, data_source
)
SELECT
    s.security_code,
    s.internal_id,
    s.standard,
    s.industry_code,
    s.industry_name,
    s.level1_code,
    s.level1_name,
    s.level2_code,
    s.level2_name,
    DATE '1900-01-01',
    NULL,
    TRUE,
    s.data_source
FROM (
    SELECT DISTINCT ON (security_code)
        security_code,
        internal_id,
        CASE
            WHEN UPPER(TRIM(COALESCE(industry_standard, ''))) IN ('GICS', 'CSRC', 'SW', 'CITIC', 'WIND')
                THEN UPPER(TRIM(industry_standard))
            ELSE 'GICS'
        END AS standard,
        CASE
            WHEN COALESCE(NULLIF(TRIM(sector_level1), ''), 'UNKNOWN') ~ '[A-Za-z0-9]'
                THEN TRIM(BOTH '-' FROM UPPER(REGEXP_REPLACE(TRIM(sector_level1), '[^A-Za-z0-9]+', '-', 'g')))
            ELSE 'IND-' || UPPER(SUBSTR(MD5(COALESCE(NULLIF(TRIM(sector_level1), ''), 'UNKNOWN')), 1, 10))
        END AS industry_code,
        COALESCE(NULLIF(TRIM(sector_level1), ''), '未分类') AS industry_name,
        CASE
            WHEN COALESCE(NULLIF(TRIM(sector_level1), ''), 'UNKNOWN') ~ '[A-Za-z0-9]'
                THEN TRIM(BOTH '-' FROM UPPER(REGEXP_REPLACE(TRIM(sector_level1), '[^A-Za-z0-9]+', '-', 'g')))
            ELSE 'IND-' || UPPER(SUBSTR(MD5(COALESCE(NULLIF(TRIM(sector_level1), ''), 'UNKNOWN')), 1, 10))
        END AS level1_code,
        NULLIF(TRIM(sector_level1), '') AS level1_name,
        CASE
            WHEN NULLIF(TRIM(sector_level2), '') IS NULL THEN NULL
            WHEN TRIM(sector_level2) ~ '[A-Za-z0-9]'
                THEN TRIM(BOTH '-' FROM UPPER(REGEXP_REPLACE(TRIM(sector_level2), '[^A-Za-z0-9]+', '-', 'g')))
            ELSE 'IND2-' || UPPER(SUBSTR(MD5(TRIM(sector_level2)), 1, 10))
        END AS level2_code,
        NULLIF(TRIM(sector_level2), '') AS level2_name,
        COALESCE(data_source, 'WIND') AS data_source
    FROM fsi.mktdata_stock_static
    WHERE NULLIF(TRIM(sector_level1), '') IS NOT NULL
       OR NULLIF(TRIM(sector_level2), '') IS NOT NULL
    ORDER BY security_code, updated_at DESC NULLS LAST, internal_id
) s
ON CONFLICT (security_code, standard, industry_code, begin_date) DO UPDATE
SET industry_name = EXCLUDED.industry_name,
    level1_code = EXCLUDED.level1_code,
    level1_name = EXCLUDED.level1_name,
    level2_code = COALESCE(EXCLUDED.level2_code, fsi.mktdata_stock_industry.level2_code),
    level2_name = COALESCE(EXCLUDED.level2_name, fsi.mktdata_stock_industry.level2_name),
    internal_id = COALESCE(EXCLUDED.internal_id, fsi.mktdata_stock_industry.internal_id),
    is_primary = TRUE,
    loaded_at = NOW();

-- 静态表行业字段改为由行业表回写（兼容旧查询，权威在 industry 表）
UPDATE fsi.mktdata_stock_static s
SET sector_level1 = i.level1_name,
    sector_level2 = i.level2_name,
    industry_standard = i.standard,
    updated_at = NOW()
FROM fsi.v_mktdata_stock_industry_current i
WHERE i.security_code = s.security_code
  AND i.is_primary
  AND i.standard = COALESCE(NULLIF(UPPER(TRIM(s.industry_standard)), ''), 'GICS');
