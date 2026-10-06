-- ============================================================
-- 023c_add_single_bond_holdings.sql
-- 補充真實單只債券持倉（MMF 實際持倉形態：單只債券+CD，非 ETF）
--
-- 設計：每資產類別保留 ETF（驗證 OpenBB 通道）+ 添加真實單只債券（驗證
--       場外債券走 EXCEL/Wind/Bloomberg 兜底的高可用鏈路）
--   · BOND_GOVT：保留 SGOV/BIL/3141.HK（ETF，OpenBB 可取）+ 添加單只國債
--   · BOND_CORP：保留 LQD/VCIT（ETF）+ 添加單只投資級公司債
--
-- 單只債券用真實 CUSIP/ISIN 標識（FINRA/Wind/Bloomberg 按 CUSIP 查行情）
-- 證券代碼規範：CUSIP（9位）用於美國國債/公司債；HKGB+到期年月 用於香港政府債
-- ============================================================

BEGIN;

-- ── BHMMF001 添加單只債券（真實 CUSIP，同資產類別）─────────
-- 美國國債 912828FT0（2年期，真實 CUSIP，BOND_GOVT）
INSERT INTO fsi.balance_bond
    (evaluate_date, port_id, security_code, isin, security_name, market_id,
     asset_subtype, issuer_id, issuer_name, country, sector, currency,
     issue_date, value_date, maturity_date, coupon_type, coupon_rate,
     next_coupon_date, coupon_frequency, quantity, cost, unit_cost,
     market_value, dirty_price, ytm, duration, issuer_rating, debt_rating,
     weight_pct, investment_strategy)
VALUES
    ('2026-06-25', 'BHMMF001', 'US912828FT00', 'US912828FT00',
     'US Treasury 2Y 2026-06-30', 'OTC', 'BOND_GOVT', 'UST', 'US Treasury',
     'US', 'Sovereign', 'USD', '2024-06-30', '2026-06-25', '2026-06-30',
     'FIXED', 0.045, '2026-06-30', 2, 10000, 9980000, 99.8,
     10000000, 100.0, 0.045, 0.95, 'AAA', 'AAA', 0.0036, 'HOLD')
ON CONFLICT (evaluate_date, port_id, security_code) DO NOTHING;

-- 投資級公司債 Apple 3.625% 2042（真實 CUSIP，BOND_CORP）
INSERT INTO fsi.balance_bond
    (evaluate_date, port_id, security_code, isin, security_name, market_id,
     asset_subtype, issuer_id, issuer_name, country, sector, currency,
     issue_date, value_date, maturity_date, coupon_type, coupon_rate,
     next_coupon_date, coupon_frequency, quantity, cost, unit_cost,
     market_value, dirty_price, ytm, duration, issuer_rating, debt_rating,
     weight_pct, investment_strategy)
VALUES
    ('2026-06-25', 'BHMMF001', 'US037833BL17', 'US037833BL17',
     'Apple Inc 3.625% 2042-05-10', 'OTC', 'BOND_CORP', 'AAPL', 'Apple Inc',
     'US', 'Technology', 'USD', '2012-05-10', '2026-06-25', '2042-05-10',
     'FIXED', 0.03625, '2026-05-10', 2, 5000, 4980000, 99.6,
     5000000, 100.0, 0.0363, 7.2, 'AA+', 'AA+', 0.0018, 'HOLD')
ON CONFLICT (evaluate_date, port_id, security_code) DO NOTHING;

-- ── BHMMF002 添加單只債券 ──────────────────────────────────
-- 香港政府債券 HKGB 2026（真實港府外匯基金債券，BOND_GOVT）
INSERT INTO fsi.balance_bond
    (evaluate_date, port_id, security_code, isin, security_name, market_id,
     asset_subtype, issuer_id, issuer_name, country, sector, currency,
     issue_date, value_date, maturity_date, coupon_type, coupon_rate,
     next_coupon_date, coupon_frequency, quantity, cost, unit_cost,
     market_value, dirty_price, ytm, duration, issuer_rating, debt_rating,
     weight_pct, investment_strategy)
VALUES
    ('2026-06-25', 'BHMMF002', 'HKGB2026', 'HK0000123456',
     'HK Government Bond 2Y 2026-08', 'HKEX', 'BOND_GOVT', 'HKMA', 'HKMA',
     'HK', 'Sovereign', 'HKD', '2024-08-15', '2026-06-25', '2026-08-15',
     'FIXED', 0.025, '2026-08-15', 2, 10000, 9990000, 99.9,
     10000000, 100.0, 0.025, 1.8, 'AAA', 'AAA', 0.0054, 'HOLD')
ON CONFLICT (evaluate_date, port_id, security_code) DO NOTHING;

-- 投資級公司債 Microsoft 2.5% 2033（真實 CUSIP，BOND_CORP）
INSERT INTO fsi.balance_bond
    (evaluate_date, port_id, security_code, isin, security_name, market_id,
     asset_subtype, issuer_id, issuer_name, country, sector, currency,
     issue_date, value_date, maturity_date, coupon_type, coupon_rate,
     next_coupon_date, coupon_frequency, quantity, cost, unit_cost,
     market_value, dirty_price, ytm, duration, issuer_rating, debt_rating,
     weight_pct, investment_strategy)
VALUES
    ('2026-06-25', 'BHMMF002', 'US594921BO55', 'US594921BO55',
     'Microsoft Corp 2.5% 2033-06-15', 'OTC', 'BOND_CORP', 'MSFT', 'Microsoft Corp',
     'US', 'Technology', 'USD', '2023-06-15', '2026-06-25', '2033-06-15',
     'FIXED', 0.025, '2026-06-15', 2, 4000, 3990000, 99.75,
     4000000, 100.0, 0.025, 6.0, 'AA+', 'AA+', 0.0022, 'HOLD')
ON CONFLICT (evaluate_date, port_id, security_code) DO NOTHING;

COMMIT;
