-- ============================================================
-- 023a_security_alias_seed.sql  證券代碼別名映射種子（OpenBB/yfinance/Wind）
-- 依賴：import_adtv.py 的 ensure_alias_table（冪等 CREATE TABLE）
-- 用途：fsi.para_security_alias — security_code ↔ 各源 ticker 映射
--
-- v2 更新（2026-10-05）：測試持倉券種真實化後，所有債券均為真實資本市場活躍券
--   （ETF 形式，OpenBB/yfinance 可取得逐日行情），alias = 證券代碼本身。
--   CD/存款/回購為場外品種，無公開行情（由 EXCEL/Wind 源兜底，無 alias）。
-- ============================================================

INSERT INTO fsi.para_security_alias (security_code, source, alias_code, note)
VALUES
    -- 港元債券 ETF（OpenBB yfinance provider 可取）
    ('3141.HK',  'OPENBB',   '3141.HK',  'ABF港元債券指數ETF（港交所掛牌）'),
    ('3141.HK',  'YFINANCE', '3141.HK',  '同上'),
    -- 美元短/中期國庫券 ETF（香港 MMF 實際可持 USD 工具）
    ('SGOV.US',  'OPENBB',   'SGOV',     'iShares 0-3M國庫券ETF'),
    ('SGOV.US',  'YFINANCE', 'SGOV',     '同上'),
    ('BIL.US',   'OPENBB',   'BIL',      'iShares 1-3M國庫券ETF'),
    ('BIL.US',   'YFINANCE', 'BIL',      '同上'),
    ('SHV.US',   'OPENBB',   'SHV',      'iShares Short Treasury Bond ETF'),
    ('SHV.US',   'YFINANCE', 'SHV',      '同上'),
    ('IEF.US',   'OPENBB',   'IEF',      'iShares 7-10Y國債ETF'),
    ('IEF.US',   'YFINANCE', 'IEF',      '同上'),
    ('IEI.US',   'OPENBB',   'IEI',      'iShares 3-7Y國債ETF'),
    ('IEI.US',   'YFINANCE', 'IEI',      '同上'),
    -- 投資級公司債 ETF（信用債代理）
    ('LQD.US',   'OPENBB',   'LQD',      'iShares投資級公司債ETF'),
    ('LQD.US',   'YFINANCE', 'LQD',      '同上'),
    ('VCIT.US',  'OPENBB',   'VCIT',     'Vanguard中期公司債ETF'),
    ('VCIT.US',  'YFINANCE', 'VCIT',     '同上')
ON CONFLICT (security_code, source) DO UPDATE SET
    alias_code = EXCLUDED.alias_code,
    note       = EXCLUDED.note;
