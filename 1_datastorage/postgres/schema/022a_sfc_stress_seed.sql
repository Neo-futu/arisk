-- ============================================================
-- 022a_sfc_stress_seed.sql  SFC 壓力測試參數與 ADTV 種子數據
-- 依賴：022_sfc_liquidity_stress.sql
-- 執行方式：冪等，可重跑（DELETE + INSERT 或 ON CONFLICT）
--
-- 1. sfc_liquidity_bucket_def — 按資產類別 × 場景配置 SFC 壓力測試參數
-- 2. mktdata_adtv             — 2026-06-25 估值日 ADTV（PROXY 代理值，Wind 入庫後覆蓋）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. SFC 變現係數配置（資產類別 × 場景）
--   口徑依據 lmt-mmf-test-sfc.docx：
--     §2(a) 二級市場變現：最大 10% ADTV 參與率（Normal 與 Stressed 一致）
--     §1(iv) Stressed：ADTV 50% haircut、定期存款零早破、價差擴大
--     §1(ii) DLA ≥7.5% / WLA ≥15%（UT Code §8.2(n)）
--   proxy_turnover_pct：品種典型日均換手率（成交額/流通盤），無行情時代理 ADTV = 持倉市值 × proxy_turnover_pct
-- ============================================================
DELETE FROM fsi.sfc_liquidity_bucket_def;

INSERT INTO fsi.sfc_liquidity_bucket_def
    (asset_category, scenario, market_participation_pct, adtv_haircut_pct,
     early_break_pct, bid_ask_cost_bps, proxy_turnover_pct, liq_ratio_static, note)
VALUES
    -- 現金：即時可用（0 天），無市場變現概念
    ('CASH',       'NORMAL',   0.000000, 0.000000, 0.000000,   0.0, 0.000000, 1.00,
     '現金即時可用 T+0'),
    ('CASH',       'STRESSED', 0.000000, 0.000000, 0.000000,   0.0, 0.000000, 1.00,
     '現金即時可用 T+0（壓力下不變）'),

    -- 逆回購：融出資金到期收回，1 天內
    ('REV_REPO',   'NORMAL',   0.000000, 0.000000, 0.000000,   0.0, 0.000000, 1.00,
     '逆回購到期收回 T+1 內'),
    ('REV_REPO',   'STRESSED', 0.000000, 0.000000, 0.000000,   0.0, 0.000000, 1.00,
     '逆回購到期收回 T+1 內（壓力下按到期日，若遇結算延遲歸入更長桶）'),

    -- 存款：Normal 可提前支取（100%），Stressed 零早破（SFC §1(iv)）
    ('DEPOSIT',    'NORMAL',   0.000000, 0.000000, 1.000000,   0.0, 0.000000, 1.00,
     '定存 Normal 全額可提前支取（計入 DLA 需 is_overnight 或 T+1 到期）'),
    ('DEPOSIT',    'STRESSED', 0.000000, 0.000000, 0.000000,   0.0, 0.000000, 1.00,
     '定存 Stressed 零早破：僅按合約到期日變現（SFC §1(iv)）'),

    -- CD：二級市場 10% ADTV 參與率；Stressed ADTV 50% haircut
    ('CD',         'NORMAL',   0.100000, 0.000000, 0.000000,   2.0, 0.300000, 0.20,
     '存款證：10% ADTV 參與率，無折扣；代理換手率 30%'),
    ('CD',         'STRESSED', 0.100000, 0.500000, 0.000000,   8.0, 0.150000, 0.20,
     '存款證 Stressed：ADTV 50% haircut + 價差 8bp'),

    -- 政府/公共債券：流動性最好（T+1 可計入 DLA）
    ('BOND_GOVT',  'NORMAL',   0.100000, 0.000000, 0.000000,   1.0, 1.000000, 0.20,
     '政府/公共債：10% ADTV，代理換手率 100%（面值代理）'),
    ('BOND_GOVT',  'STRESSED', 0.100000, 0.500000, 0.000000,   5.0, 0.500000, 0.20,
     '政府/公共債 Stressed：ADTV 50% haircut + 價差 5bp'),

    -- 信用債：壓力下流動性顯著下降
    ('BOND_CORP',  'NORMAL',   0.100000, 0.000000, 0.000000,   3.0, 0.200000, 0.80,
     '信用債：10% ADTV，代理換手率 20%（壓力下更低）'),
    ('BOND_CORP',  'STRESSED', 0.100000, 0.500000, 0.000000,  15.0, 0.100000, 0.80,
     '信用債 Stressed：ADTV 50% haircut + 價差 15bp'),

    -- 浮息債：利率敏感度極低，接近 CD 流動性
    ('BOND_FLOAT', 'NORMAL',   0.100000, 0.000000, 0.000000,   3.0, 0.200000, 0.05,
     '浮息債：10% ADTV，代理換手率 20%'),
    ('BOND_FLOAT', 'STRESSED', 0.100000, 0.500000, 0.000000,  12.0, 0.100000, 0.05,
     '浮息債 Stressed：ADTV 0.5 折扣 + 價差 12bp'),

    -- 正回購（融入）：到期還款為流動性流出，非變現資產
    ('REPO',       'NORMAL',   0.000000, 0.000000, 0.000000,   0.0, 0.000000, 0.00,
     '正回購（融入還款）：流動性負項，不在分層中作為變現來源');

-- ────────────────────────────────────────────────────────────
-- 2. mktdata_adtv 種子（2026-06-25 估值日）
--   數據來源：data_source='PROXY'（用品種典型換手率 × 持倉市值代理）
--   後續 Wind/MCP 行情入庫後，data_source='WIND' 的記錄覆蓋代理值
--   ADTV = market_value × proxy_turnover_pct（代理口徑）
--   注：真實行情入庫後改為 30 日 turnover 算術平均
-- ============================================================
DELETE FROM fsi.mktdata_adtv WHERE adtv_date = '2026-06-25'::DATE;

WITH bonds_dedup AS (
    -- 債券（按 asset_subtype 分類，浮息債單列）— 證券級去重（ADTV 與組合無關）
    SELECT DISTINCT ON (b.security_code)
           b.security_code,
           b.market_value,
           CASE WHEN COALESCE(b.coupon_type,'FIXED') = 'FLOAT' THEN 'BOND_FLOAT'
                ELSE b.asset_subtype::TEXT END AS asset_category
    FROM fsi.balance_bond b
    JOIN fsi.para_portfolio p ON p.port_id = b.port_id
    WHERE b.evaluate_date = '2026-06-25'::DATE AND b.quantity > 0
      AND p.is_mmf = TRUE AND p.is_active = TRUE
    ORDER BY b.security_code, b.market_value DESC
),
cds_dedup AS (
    -- CD（證券級去重）
    SELECT DISTINCT ON (c.security_code)
           c.security_code, c.market_value, 'CD'::TEXT AS asset_category
    FROM fsi.balance_cd c
    JOIN fsi.para_portfolio p ON p.port_id = c.port_id
    WHERE c.evaluate_date = '2026-06-25'::DATE
      AND p.is_mmf = TRUE AND p.is_active = TRUE
    ORDER BY c.security_code, c.market_value DESC
),
securities AS (
    SELECT * FROM bonds_dedup
    UNION ALL
    SELECT * FROM cds_dedup
)
INSERT INTO fsi.mktdata_adtv (adtv_date, security_code, market_id, adtv_30d, sample_days, turnover_pct, data_source)
SELECT
    '2026-06-25'::DATE,
    t.security_code,
    'HKEX',  -- 證券市場（債券 CMU/港交所，CD 銀行間）
    ROUND(t.market_value * d.proxy_turnover_pct, 2) AS adtv_30d,
    30,
    d.proxy_turnover_pct,
    'PROXY'
FROM securities t
JOIN fsi.sfc_liquidity_bucket_def d
  ON d.asset_category = t.asset_category
 AND d.scenario = 'NORMAL'
WHERE d.proxy_turnover_pct > 0
ON CONFLICT (adtv_date, security_code) DO UPDATE SET
    market_id      = EXCLUDED.market_id,
    adtv_30d       = EXCLUDED.adtv_30d,
    sample_days    = EXCLUDED.sample_days,
    turnover_pct   = EXCLUDED.turnover_pct,
    data_source    = EXCLUDED.data_source;
