-- ============================================================
-- 026_balance_bond_rating_agency_seed.sql
-- 为演示「国内 / 国际三大 / 内评」切换，补齐 balance_bond.rating_agency 与 internal_rating。
-- 幂等：按证券代码模式更新，可重跑。
-- ============================================================

-- 国内机构：中诚信 / 中债资信 / 联合（示例映射到国债与信用债）
UPDATE fsi.balance_bond
SET rating_agency = 'CSCI'::fsi.rating_agency
WHERE security_code IN ('3141.HK', 'BIL.US', 'SGOV.US', 'HKGB2026', 'CN0002001234', 'HK0002005678');

UPDATE fsi.balance_bond
SET rating_agency = 'LIANHE'::fsi.rating_agency
WHERE security_code IN ('VCIT.US', 'LQD.US', 'US037833BL17', 'US594921BO55');

-- 国际三大（落在常见演示持仓上，便于切换验证）
UPDATE fsi.balance_bond
SET rating_agency = 'SP'::fsi.rating_agency,
    issuer_rating = COALESCE(issuer_rating, 'AA'),
    debt_rating = COALESCE(debt_rating, 'AA')
WHERE security_code IN ('IEF.US', 'IEI.US', 'BIL.US');

UPDATE fsi.balance_bond
SET rating_agency = 'MOODY'::fsi.rating_agency,
    issuer_rating = COALESCE(issuer_rating, 'Aa2'),
    debt_rating = COALESCE(debt_rating, 'Aa2')
WHERE security_code IN ('SHV.US', 'SGOV.US');

UPDATE fsi.balance_bond
SET rating_agency = 'FITCH'::fsi.rating_agency,
    issuer_rating = COALESCE(issuer_rating, 'AA'),
    debt_rating = COALESCE(debt_rating, 'AA')
WHERE security_code IN ('US912828FT00');

-- 内评：写入 internal_rating，机构标记 INTERNAL
UPDATE fsi.balance_bond
SET rating_agency = 'INTERNAL'::fsi.rating_agency,
    internal_rating = COALESCE(NULLIF(btrim(internal_rating), ''), COALESCE(debt_rating, issuer_rating, 'A'))
WHERE security_code IN ('CD_BOCHK_01', 'CD_HSBC_01', 'CD_HKMA_01', 'CD_SCB_01', 'VCIT.US');
