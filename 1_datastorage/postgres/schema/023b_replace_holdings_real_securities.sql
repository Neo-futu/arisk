-- ============================================================
-- 023b_replace_holdings_real_securities.sql
-- 測試持倉券種真實化替換（2026-10-05）
--
-- 背景：原測試數據中的 CMU 場外債券/編造代碼在公開行情源（OpenBB/yfinance）
--       無逐日行情（場外品種本質），無法驗證 OpenBB 高可用行情管道。
-- 替換原則：保持組合結構與市值不變，按【同資產類別】替換為真實資本市場活躍券
--       （真實代碼+真實發行人），公開行情源可取得逐日行情。
-- CD/存款/回購保留：銀行間 OTC 品種本就無公開行情，由 EXCEL/Wind 源兜底
--       —— 這正是三源高可用管道的設計場景。
--
-- 替換映射（同資產類別，UPDATE 原行改寫 security_code/名稱/發行人）：
--   4701.HK          機場局票據(編造) → 3141.HK  ABF港元債券ETF      BOND_GOVT HKD
--   CN0002001234     26國債(編造)     → SGOV.US  0-3M國庫券ETF       BOND_GOVT USD
--   DBANFN25034.CMU  SCENTRE(編造)    → BIL.US   1-3M國庫券ETF       BOND_GOVT USD
--   40032.HK         港燈債(編造)     → LQD.US   投資級公司債ETF     BOND_CORP USD
--   BNYHFN26213.CMU  HKU債(編造)      → VCIT.US  中期公司債ETF       BOND_CORP USD
--   40198.HK         IFCDCN(編造)     → IEF.US   7-10Y國債ETF        BOND_GOVT USD
--   DBANFN25028.CMU  LinkREIT債(編造) → IEI.US   3-7Y國債ETF         BOND_GOVT USD
-- ============================================================

BEGIN;

-- ── BHMMF001 ────────────────────────────────────────────────
UPDATE fsi.balance_bond SET
    security_code = '3141.HK',
    security_name = 'ABF HK Bond Index ETF',
    issuer_name   = 'ABF Hong Kong Bond Index Fund',
    issuer_rating = 'AAA', debt_rating = 'AAA',
    asset_subtype = 'BOND_GOVT', currency = 'HKD',
    maturity_date = '2026-08-05', duration = 0.11
WHERE evaluate_date = '2026-06-25' AND port_id = 'BHMMF001' AND security_code = '4701.HK';

UPDATE fsi.balance_bond SET
    security_code = 'SGOV.US',
    security_name = 'iShares 0-3 Month Treasury Bond ETF',
    issuer_name   = 'iShares (BlackRock)',
    issuer_rating = 'AAA', debt_rating = 'AAA',
    asset_subtype = 'BOND_GOVT', currency = 'USD',
    maturity_date = '2026-07-25', duration = 0.08
WHERE evaluate_date = '2026-06-25' AND port_id = 'BHMMF001' AND security_code = 'CN0002001234';

UPDATE fsi.balance_bond SET
    security_code = 'BIL.US',
    security_name = 'iShares 1-3 Month Treasury Bond ETF',
    issuer_name   = 'iShares (BlackRock)',
    issuer_rating = 'AAA', debt_rating = 'AAA',
    asset_subtype = 'BOND_GOVT', currency = 'USD',
    maturity_date = '2026-08-19', duration = 0.15
WHERE evaluate_date = '2026-06-25' AND port_id = 'BHMMF001' AND security_code = 'DBANFN25034.CMU';

UPDATE fsi.balance_bond SET
    security_code = 'LQD.US',
    security_name = 'iShares iBoxx $ Inv Grade Corp Bond ETF',
    issuer_name   = 'iShares (BlackRock)',
    issuer_rating = 'AA+', debt_rating = 'AA+',
    asset_subtype = 'BOND_CORP', currency = 'USD',
    maturity_date = '2031-01-11', duration = 3.95
WHERE evaluate_date = '2026-06-25' AND port_id = 'BHMMF001' AND security_code = '40032.HK';

UPDATE fsi.balance_bond SET
    security_code = 'VCIT.US',
    security_name = 'Vanguard Interm-Term Corp Bond ETF',
    issuer_name   = 'Vanguard',
    issuer_rating = 'AA+', debt_rating = 'AA+',
    asset_subtype = 'BOND_CORP', currency = 'USD',
    maturity_date = '2031-06-18', duration = 4.8
WHERE evaluate_date = '2026-06-25' AND port_id = 'BHMMF001' AND security_code = 'BNYHFN26213.CMU';

-- ── BHMMF002 ────────────────────────────────────────────────
UPDATE fsi.balance_bond SET
    security_code = 'IEF.US',
    security_name = 'iShares 7-10 Year Treasury Bond ETF',
    issuer_name   = 'iShares (BlackRock)',
    issuer_rating = 'AAA', debt_rating = 'AAA',
    asset_subtype = 'BOND_GOVT', currency = 'USD',
    maturity_date = '2030-04-08', duration = 3.2
WHERE evaluate_date = '2026-06-25' AND port_id = 'BHMMF002' AND security_code = '40198.HK';

UPDATE fsi.balance_bond SET
    security_code = 'IEI.US',
    security_name = 'iShares 3-7 Year Treasury Bond ETF',
    issuer_name   = 'iShares (BlackRock)',
    issuer_rating = 'AAA', debt_rating = 'AAA',
    asset_subtype = 'BOND_GOVT', currency = 'USD',
    maturity_date = '2035-05-07', duration = 6.5
WHERE evaluate_date = '2026-06-25' AND port_id = 'BHMMF002' AND security_code = 'DBANFN25028.CMU';

COMMIT;
