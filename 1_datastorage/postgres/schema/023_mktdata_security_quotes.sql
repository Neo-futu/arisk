-- ============================================================
-- 023_mktdata_security_quotes.sql  證券日級行情原始表 + ADTV 聚合鏈路
-- 依賴：005_mktdata.sql（mktdata_quotes 等）、022_sfc_liquidity_stress.sql（mktdata_adtv）
--
-- 設計：
--   1. fsi.mktdata_security_quotes — 證券日級行情原始表（統一收 yfinance/OpenBB/Wind/Excel）
--      存成交價/成交量/成交額/換手率，按 (quote_date, security_code, source) 唯一
--   2. fsi.mktdata_adtv_import_log  — 導入審計日誌（每次導入留痕，可回溯）
--   3. fsi.fn_compute_adtv_30d(d DATE) — 聚合函數：從原始表算過去 30 日平均成交額，
--      upsert 到 mktdata_adtv（data_source='MARKET'），覆蓋 PROXY 代理值
--
-- 三源入庫策略：
--   EXCEL  — 手工維護模板（證券代碼/日成交額/換手率），data_source='EXCEL'
--   YFINANCE / OPENBB — 公開行情（港股/ETF/部分 CD），data_source='YFINANCE'/'OPENBB'
--   WIND — Wind API/MCP（債券/CD/回購，專業付費源），data_source='WIND'
--   無原始行情的證券仍由 022a 種子提供 PROXY 代理值（data_source='PROXY'）
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 1. 證券日級行情原始表
--   存儲每日收盤成交量/成交額/換手率，ADTV = 過去 30 個交易日成交額的算術平均
--   一個證券可有多來源（source 不同），聚合時取優先級最高的源（WIND>YFINANCE>OPENBB>EXCEL）
-- ============================================================
CREATE TABLE IF NOT EXISTS fsi.mktdata_security_quotes (
    quote_date       DATE         NOT NULL,
    security_code    VARCHAR(32)  NOT NULL,
    market_id        VARCHAR(16),                -- HKEX/IB/CIBM/OTC 等
    close_price      NUMERIC(24,8),              -- 收盤價（本幣）
    volume           NUMERIC(24,4),              -- 成交量（手/份）
    turnover         NUMERIC(24,2),              -- 成交額（元，本幣）= close × volume
    free_float       NUMERIC(24,2),              -- 流通盤（元，可選）— 用於精確換手率
    turnover_pct     NUMERIC(10,6),              -- 換手率 = turnover / free_float（可選）
    source           VARCHAR(16)  NOT NULL,      -- WIND / YFINANCE / OPENBB / EXCEL
    currency         CHAR(3)      NOT NULL DEFAULT 'HKD',
    loaded_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (quote_date, security_code, source)
);
COMMENT ON TABLE fsi.mktdata_security_quotes IS '證券日級行情原始表：統一收 yfinance/OpenBB/Wind/Excel，ADTV 計算源';
COMMENT ON COLUMN fsi.mktdata_security_quotes.turnover IS '日成交額（元，本幣）；ADTV = 過去 30 日 turnover 算術平均';
COMMENT ON COLUMN fsi.mktdata_security_quotes.source IS 'WIND/YFINANCE/OPENBB/EXCEL；同日同證券多源時聚合取優先級最高';

CREATE INDEX IF NOT EXISTS idx_msq_code_date ON fsi.mktdata_security_quotes(security_code, quote_date DESC);
CREATE INDEX IF NOT EXISTS idx_msq_date       ON fsi.mktdata_security_quotes(quote_date DESC);
CREATE INDEX IF NOT EXISTS idx_msq_source    ON fsi.mktdata_security_quotes(source);

-- ────────────────────────────────────────────────────────────
-- 2. 導入審計日誌
-- ============================================================
CREATE TABLE IF NOT EXISTS fsi.mktdata_adtv_import_log (
    import_id       BIGSERIAL    PRIMARY KEY,
    import_ts       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    source          VARCHAR(16)  NOT NULL,       -- WIND/YFINANCE/OPENBB/EXCEL
    as_of_date      DATE         NOT NULL,        -- 估值日（ADTV 計算截止日）
    rows_upserted   INTEGER      NOT NULL DEFAULT 0,
    securities_cnt  INTEGER      NOT NULL DEFAULT 0,
    adtv_total      NUMERIC(24,2),                -- 入庫證券 ADTV 合計（元，審計用）
    file_name       VARCHAR(255),                 -- Excel 導入時的文件名
    status          VARCHAR(16)  NOT NULL DEFAULT 'OK',  -- OK/WARN/ERROR
    message         TEXT
);
COMMENT ON TABLE fsi.mktdata_adtv_import_log IS 'ADTV 行情導入審計日誌：每次導入留痕，可回溯';

-- ────────────────────────────────────────────────────────────
-- 3. fn_compute_adtv_30d(d DATE, days INT DEFAULT 30) — 聚合函數
--   只聚合「逐日報價」市場源（WIND > YFINANCE > OPENBB），算過去 N 日（默認 30）
--   平均成交額，要求 ≥5 個交易日樣本；upsert 到 mktdata_adtv（data_source='MARKET'）。
--   EXCEL 手工錄入為「已平均的 ADTV 估計值」，由 import_adtv.py 直接入庫
--   （data_source='EXCEL'）；MARKET 真實行情覆蓋 EXCEL 估計值。
--   PROXY 代理值由 022a 種子維護，僅在前兩者都缺失時生效。
--   優先級：MARKET > EXCEL > PROXY
--   返回：聚合的證券數
-- ============================================================
CREATE OR REPLACE FUNCTION fsi.fn_compute_adtv_30d(
    d DATE,
    days INT DEFAULT 30
) RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    cnt INTEGER;
BEGIN
    -- 聚合：每證券取過去 days 日、按源優先級最高的成交額算術平均
    INSERT INTO fsi.mktdata_adtv (adtv_date, security_code, market_id, adtv_30d, adtv_30d_volume, sample_days, turnover_pct, data_source)
    WITH ranked AS (
        SELECT
            q.security_code,
            q.market_id,
            q.turnover,
            q.volume,
            q.free_float,
            q.source,
            ROW_NUMBER() OVER (
                PARTITION BY q.security_code, q.quote_date
                ORDER BY CASE q.source
                    WHEN 'WIND' THEN 1
                    WHEN 'YFINANCE' THEN 2
                    WHEN 'OPENBB' THEN 3
                    WHEN 'EXCEL' THEN 4   -- EXCEL 逐日行情（Bloomberg/FINRA 導出）優先級最低但仍為真實逐日數據
                    ELSE 9
                END
            ) AS rn
        FROM fsi.mktdata_security_quotes q
        WHERE q.quote_date > d - (days + 7)  -- 多取 7 天緩衝以應對節假日
          AND q.quote_date <= d
          AND q.turnover IS NOT NULL
          AND q.source IN ('WIND','YFINANCE','OPENBB','EXCEL')  -- EXCEL 逐日行情（Bloomberg 導出）納入日均聚合
    ),
    dedup AS (  -- 同日多源取優先級最高
        SELECT * FROM ranked WHERE rn = 1
    ),
    agg AS (
        SELECT
            security_code,
            MAX(market_id) AS market_id,
            AVG(turnover) AS adtv_30d,
            AVG(volume) AS adtv_30d_volume,
            COUNT(*) AS sample_days,
            MAX(free_float) AS free_float
        FROM dedup
        GROUP BY security_code
        HAVING COUNT(*) >= 5  -- 至少 5 個交易日樣本（防止單日噪聲）
    )
    SELECT
        d,
        a.security_code,
        a.market_id,
        ROUND(a.adtv_30d, 2),
        ROUND(a.adtv_30d_volume, 4),
        a.sample_days,
        CASE WHEN a.free_float > 0
             THEN ROUND(a.adtv_30d / a.free_float, 6)
             ELSE NULL END,
        'MARKET'
    FROM agg a
    ON CONFLICT (adtv_date, security_code) DO UPDATE SET
        market_id      = EXCLUDED.market_id,
        adtv_30d       = EXCLUDED.adtv_30d,
        adtv_30d_volume = EXCLUDED.adtv_30d_volume,
        sample_days    = EXCLUDED.sample_days,
        turnover_pct   = EXCLUDED.turnover_pct,
        data_source    = 'MARKET',
        loaded_at      = NOW();

    GET DIAGNOSTICS cnt = ROW_COUNT;

    -- MARKET 真實行情覆蓋同證券的 EXCEL 手工估計值
    DELETE FROM fsi.mktdata_adtv a
    WHERE a.adtv_date = d
      AND a.data_source = 'EXCEL'
      AND EXISTS (
          SELECT 1 FROM fsi.mktdata_adtv m
          WHERE m.adtv_date = a.adtv_date
            AND m.security_code = a.security_code
            AND m.data_source = 'MARKET'
      );

    RETURN cnt;
END;
$$;
COMMENT ON FUNCTION fsi.fn_compute_adtv_30d(DATE, INT) IS
    '從 mktdata_security_quotes 聚合市場源（WIND/YFINANCE/OPENBB）過去 30 日平均成交額到 mktdata_adtv（data_source=MARKET，≥5 日樣本），並覆蓋同證券 EXCEL 手工估計值；EXCEL 與 PROXY 由其他管道維護';
