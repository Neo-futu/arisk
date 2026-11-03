-- ============================================================
-- 029_treasury_curve_campisi.sql
-- Campisi 国债效应所需政府债曲线：美国国债 / 中国国债 / 香港政府债。
-- 报价由 seed_treasury_curves.py 写入 mktdata_yield_curve_quotes。
-- ============================================================

INSERT INTO fsi.mktdata_yield_curve_def (
    curve_id, curve_name, currency, curve_type, country, data_source, source_id, description, is_active
) VALUES
    ('US_TREAS', 'US Treasury Yield Curve', 'USD', 'GOVERNMENT', 'US', 'YFINANCE',
     '^TNX', '美债曲线：3M/2Y/5Y/10Y/30Y（yfinance）', TRUE),
    ('CN_TREAS', '中国国债收益率曲线', 'CNY', 'GOVERNMENT', 'CN', 'YFINANCE',
     '^TNX', '中国国债曲线：由美债期限结构平移生成（无中债接口时的可用代理）', TRUE),
    ('HKGOV', '香港政府债券收益率曲线', 'HKD', 'GOVERNMENT', 'HK', 'YFINANCE',
     '^TNX', '港府债曲线：美债期限结构加息差代理', TRUE)
ON CONFLICT (curve_id) DO UPDATE
SET curve_name = EXCLUDED.curve_name,
    currency = EXCLUDED.currency,
    curve_type = EXCLUDED.curve_type,
    country = EXCLUDED.country,
    data_source = EXCLUDED.data_source,
    source_id = EXCLUDED.source_id,
    description = EXCLUDED.description,
    is_active = TRUE;
