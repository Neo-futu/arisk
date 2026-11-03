-- ============================================================
-- 027_balance_bond_agency_rating.sql
-- 按券多家评级机构（主体 / 债项）统一列示：每券可挂国内三大、国际三大与内评。
-- 符号体系：国内/标普/惠誉/内评用 AAA·AA+；穆迪用 Aaa·Aa1（粗映射，非官方换算）。
-- 幂等：表可重跑；种子按持仓派生，ON CONFLICT 覆盖并校正符号。
-- ============================================================

CREATE TABLE IF NOT EXISTS fsi.balance_bond_agency_rating (
    evaluate_date   DATE               NOT NULL,
    port_id         VARCHAR(16)        NOT NULL,
    security_code   VARCHAR(32)        NOT NULL,
    rating_agency   fsi.rating_agency  NOT NULL,
    issuer_rating   VARCHAR(8),
    debt_rating     VARCHAR(8),
    loaded_at       TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    PRIMARY KEY (evaluate_date, port_id, security_code, rating_agency)
);

COMMENT ON TABLE fsi.balance_bond_agency_rating IS
  '债券持仓多家评级：按券×机构存储主体/债项评级；穆迪用 Aaa/Aa1，其余用 AAA/AA+';

CREATE INDEX IF NOT EXISTS idx_bond_agency_rating_port_date
  ON fsi.balance_bond_agency_rating (port_id, evaluate_date DESC);

-- SP/内地符号 → 穆迪展示符号（粗映射）
CREATE OR REPLACE FUNCTION fsi._rating_to_moody(p_rating text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE upper(replace(btrim(COALESCE(p_rating, '')), ' ', ''))
    WHEN 'AAA'  THEN 'Aaa'
    WHEN 'AA+'  THEN 'Aa1'
    WHEN 'AA'   THEN 'Aa2'
    WHEN 'AA-'  THEN 'Aa3'
    WHEN 'A+'   THEN 'A1'
    WHEN 'A'    THEN 'A2'
    WHEN 'A-'   THEN 'A3'
    WHEN 'BBB+' THEN 'Baa1'
    WHEN 'BBB'  THEN 'Baa2'
    WHEN 'BBB-' THEN 'Baa3'
    WHEN 'BB+'  THEN 'Ba1'
    WHEN 'BB'   THEN 'Ba2'
    WHEN 'BB-'  THEN 'Ba3'
    WHEN 'B+'   THEN 'B1'
    WHEN 'B'    THEN 'B2'
    WHEN 'B-'   THEN 'B3'
    WHEN 'CCC+' THEN 'Caa1'
    WHEN 'CCC'  THEN 'Caa2'
    WHEN 'CCC-' THEN 'Caa3'
    WHEN 'CC'   THEN 'Ca'
    WHEN 'C'    THEN 'C'
    WHEN 'D'    THEN 'C'
    WHEN 'AAA'  THEN 'Aaa'
    WHEN 'AA1'  THEN 'Aa1'
    WHEN 'AA2'  THEN 'Aa2'
    WHEN 'AA3'  THEN 'Aa3'
    WHEN 'A1'   THEN 'A1'
    WHEN 'A2'   THEN 'A2'
    WHEN 'A3'   THEN 'A3'
    WHEN 'BAA1' THEN 'Baa1'
    WHEN 'BAA2' THEN 'Baa2'
    WHEN 'BAA3' THEN 'Baa3'
    WHEN 'BA1'  THEN 'Ba1'
    WHEN 'BA2'  THEN 'Ba2'
    WHEN 'BA3'  THEN 'Ba3'
    WHEN ''     THEN NULL
    ELSE NULLIF(btrim(p_rating), '')
  END;
$$;

-- 穆迪符号 → SP/内地展示符号
CREATE OR REPLACE FUNCTION fsi._rating_to_sp(p_rating text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE upper(replace(btrim(COALESCE(p_rating, '')), ' ', ''))
    WHEN 'AAA'  THEN 'AAA'
    WHEN 'AA1'  THEN 'AA+'
    WHEN 'AA2'  THEN 'AA'
    WHEN 'AA3'  THEN 'AA-'
    WHEN 'A1'   THEN 'A+'
    WHEN 'A2'   THEN 'A'
    WHEN 'A3'   THEN 'A-'
    WHEN 'BAA1' THEN 'BBB+'
    WHEN 'BAA2' THEN 'BBB'
    WHEN 'BAA3' THEN 'BBB-'
    WHEN 'BA1'  THEN 'BB+'
    WHEN 'BA2'  THEN 'BB'
    WHEN 'BA3'  THEN 'BB-'
    WHEN 'B1'   THEN 'B+'
    WHEN 'B2'   THEN 'B'
    WHEN 'B3'   THEN 'B-'
    WHEN 'CAA1' THEN 'CCC+'
    WHEN 'CAA2' THEN 'CCC'
    WHEN 'CAA3' THEN 'CCC-'
    WHEN 'CA'   THEN 'CC'
    WHEN 'AA+'  THEN 'AA+'
    WHEN 'AA'   THEN 'AA'
    WHEN 'AA-'  THEN 'AA-'
    WHEN 'A+'   THEN 'A+'
    WHEN 'A'    THEN 'A'
    WHEN 'A-'   THEN 'A-'
    WHEN 'BBB+' THEN 'BBB+'
    WHEN 'BBB'  THEN 'BBB'
    WHEN 'BBB-' THEN 'BBB-'
    WHEN ''     THEN NULL
    ELSE NULLIF(btrim(p_rating), '')
  END;
$$;

-- 主档派生：按机构体系写入符号（穆迪强制 Aaa/Aa1）
INSERT INTO fsi.balance_bond_agency_rating (
    evaluate_date, port_id, security_code, rating_agency, issuer_rating, debt_rating
)
SELECT
    b.evaluate_date,
    b.port_id,
    b.security_code,
    COALESCE(b.rating_agency, 'NR'::fsi.rating_agency),
    CASE COALESCE(b.rating_agency, 'NR'::fsi.rating_agency)
        WHEN 'MOODY'::fsi.rating_agency THEN fsi._rating_to_moody(b.issuer_rating)
        ELSE fsi._rating_to_sp(b.issuer_rating)
    END,
    CASE COALESCE(b.rating_agency, 'NR'::fsi.rating_agency)
        WHEN 'MOODY'::fsi.rating_agency THEN fsi._rating_to_moody(b.debt_rating)
        ELSE fsi._rating_to_sp(b.debt_rating)
    END
FROM fsi.balance_bond b
WHERE COALESCE(b.rating_agency, 'NR'::fsi.rating_agency) <> 'NR'::fsi.rating_agency
ON CONFLICT (evaluate_date, port_id, security_code, rating_agency) DO UPDATE
SET issuer_rating = EXCLUDED.issuer_rating,
    debt_rating   = EXCLUDED.debt_rating,
    loaded_at     = NOW();

-- 内评：SP/内地符号
INSERT INTO fsi.balance_bond_agency_rating (
    evaluate_date, port_id, security_code, rating_agency, issuer_rating, debt_rating
)
SELECT
    b.evaluate_date,
    b.port_id,
    b.security_code,
    'INTERNAL'::fsi.rating_agency,
    fsi._rating_to_sp(COALESCE(NULLIF(btrim(b.internal_rating), ''), b.issuer_rating)),
    fsi._rating_to_sp(COALESCE(NULLIF(btrim(b.internal_rating), ''), b.debt_rating))
FROM fsi.balance_bond b
WHERE NULLIF(btrim(COALESCE(b.internal_rating, '')), '') IS NOT NULL
   OR b.rating_agency = 'INTERNAL'::fsi.rating_agency
ON CONFLICT (evaluate_date, port_id, security_code, rating_agency) DO UPDATE
SET issuer_rating = EXCLUDED.issuer_rating,
    debt_rating   = EXCLUDED.debt_rating,
    loaded_at     = NOW();

-- 国内两家（中诚信 / 联合）：AAA/AA+ 体系；联合略低一档示意差异（不含中债资信）
INSERT INTO fsi.balance_bond_agency_rating (
    evaluate_date, port_id, security_code, rating_agency, issuer_rating, debt_rating
)
SELECT
    b.evaluate_date,
    b.port_id,
    b.security_code,
    a.agency,
    CASE
        WHEN a.agency = 'LIANHE'::fsi.rating_agency THEN
            CASE fsi._rating_to_sp(COALESCE(b.issuer_rating, 'AAA'))
                WHEN 'AAA' THEN 'AA+'
                WHEN 'AA+' THEN 'AA'
                ELSE COALESCE(fsi._rating_to_sp(b.issuer_rating), 'AA+')
            END
        ELSE COALESCE(fsi._rating_to_sp(b.issuer_rating), 'AAA')
    END,
    CASE
        WHEN a.agency = 'LIANHE'::fsi.rating_agency THEN
            CASE fsi._rating_to_sp(COALESCE(b.debt_rating, 'AAA'))
                WHEN 'AAA' THEN 'AA+'
                WHEN 'AA+' THEN 'AA'
                ELSE COALESCE(fsi._rating_to_sp(b.debt_rating), 'AA+')
            END
        ELSE COALESCE(fsi._rating_to_sp(b.debt_rating), 'AAA')
    END
FROM fsi.balance_bond b
CROSS JOIN (
    VALUES
        ('CSCI'::fsi.rating_agency),
        ('LIANHE'::fsi.rating_agency)
) AS a(agency)
ON CONFLICT (evaluate_date, port_id, security_code, rating_agency) DO UPDATE
SET issuer_rating = EXCLUDED.issuer_rating,
    debt_rating   = EXCLUDED.debt_rating,
    loaded_at     = NOW();

-- 不再列示中债资信：清理历史演示行
DELETE FROM fsi.balance_bond_agency_rating
WHERE rating_agency = 'CCX'::fsi.rating_agency;

-- 国际三大：标普/惠誉 = AAA 体系；穆迪 = Aaa/Aa1
INSERT INTO fsi.balance_bond_agency_rating (
    evaluate_date, port_id, security_code, rating_agency, issuer_rating, debt_rating
)
SELECT
    b.evaluate_date,
    b.port_id,
    b.security_code,
    a.agency,
    CASE a.agency
        WHEN 'MOODY'::fsi.rating_agency THEN
            fsi._rating_to_moody(COALESCE(b.issuer_rating, 'AAA'))
        ELSE
            COALESCE(fsi._rating_to_sp(b.issuer_rating), 'AAA')
    END,
    CASE a.agency
        WHEN 'MOODY'::fsi.rating_agency THEN
            fsi._rating_to_moody(COALESCE(b.debt_rating, 'AAA'))
        ELSE
            COALESCE(fsi._rating_to_sp(b.debt_rating), 'AAA')
    END
FROM fsi.balance_bond b
CROSS JOIN (
    VALUES
        ('SP'::fsi.rating_agency),
        ('MOODY'::fsi.rating_agency),
        ('FITCH'::fsi.rating_agency)
) AS a(agency)
ON CONFLICT (evaluate_date, port_id, security_code, rating_agency) DO UPDATE
SET issuer_rating = EXCLUDED.issuer_rating,
    debt_rating   = EXCLUDED.debt_rating,
    loaded_at     = NOW();

-- 内评兜底
INSERT INTO fsi.balance_bond_agency_rating (
    evaluate_date, port_id, security_code, rating_agency, issuer_rating, debt_rating
)
SELECT
    b.evaluate_date,
    b.port_id,
    b.security_code,
    'INTERNAL'::fsi.rating_agency,
    COALESCE(
        fsi._rating_to_sp(b.internal_rating),
        fsi._rating_to_sp(b.issuer_rating),
        'A'
    ),
    COALESCE(
        fsi._rating_to_sp(b.internal_rating),
        fsi._rating_to_sp(b.debt_rating),
        'A'
    )
FROM fsi.balance_bond b
ON CONFLICT (evaluate_date, port_id, security_code, rating_agency) DO UPDATE
SET issuer_rating = COALESCE(fsi.balance_bond_agency_rating.issuer_rating, EXCLUDED.issuer_rating),
    debt_rating   = COALESCE(fsi.balance_bond_agency_rating.debt_rating, EXCLUDED.debt_rating),
    loaded_at     = NOW();

-- 校正：凡穆迪列仍为 AAA/AA+ 等形式的，强制改为 Aaa/Aa1
UPDATE fsi.balance_bond_agency_rating
SET issuer_rating = fsi._rating_to_moody(issuer_rating),
    debt_rating   = fsi._rating_to_moody(debt_rating),
    loaded_at     = NOW()
WHERE rating_agency = 'MOODY'::fsi.rating_agency;

-- 校正：非穆迪列若误存 Aa1/Aaa，改回 SP/内地符号
UPDATE fsi.balance_bond_agency_rating
SET issuer_rating = fsi._rating_to_sp(issuer_rating),
    debt_rating   = fsi._rating_to_sp(debt_rating),
    loaded_at     = NOW()
WHERE rating_agency <> 'MOODY'::fsi.rating_agency;
