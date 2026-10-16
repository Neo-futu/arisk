-- ============================================================
-- 024_mktdata_lqa.sql  彭博 LQA 证券流动性字段
-- 对应「其他风控字段」LQA* 与 LQAP 画面用到的分类 / 冲击成本。
-- 组合层期限分布、赎回成本由 3_riskengine.liquidity.lqap 计算，不在此落第二套结果主数据。
-- ============================================================

CREATE TABLE IF NOT EXISTS fsi.mktdata_lqa (
    as_of_date                      DATE         NOT NULL,
    security_code                   VARCHAR(48)  NOT NULL,
    price_volatility                NUMERIC(12,8),          -- LQA_PRICE_VOLATILITY，3% 记为 0.03
    expected_daily_volume           NUMERIC(24,2),          -- LQA_EXPECTED_DAILY_VOLUME
    bid_ask_spread                  NUMERIC(12,8),          -- LQA_BID_ASK_SPREAD，价格分数（1bp = 0.0001）
    sector_score                    NUMERIC(12,4),          -- LQA_SECTOR_SCORE
    liquidity_sector                VARCHAR(64),            -- LQA_LIQUIDITY_SECTOR
    hk_sfc_port_lqdty_class         VARCHAR(48),            -- LQA_HK_SFC_PORT_LQDTY_CLASS
    liq_horizon_days                NUMERIC(10,2),          -- LQAP 流动性期限（天）
    unif_mkt_imp_cost               NUMERIC(12,8),          -- UNIF_MKT_IMP_COST
    empirical_trade_count           INTEGER,                -- LQA_EMPIRICAL_TRADE_COUNT
    empirical_evaluation_date       DATE,                   -- LQA_EMPIRICAL_EVALUATION_DATE
    empirical_min_trade_volume      NUMERIC(24,2),          -- LQA_EMPIRICAL_MIN_TRADE_VOLUME
    empirical_source_date           DATE,                   -- LQA_EMPIRICAL_SOURCE_DATE
    empirical_days_since_last_trade INTEGER,                -- LQA_EMPIRICAL_DAYS_SINCE_LST_TRD
    empirical_avg_trade_volume      NUMERIC(24,2),          -- LQA_EMPIRICAL_AVG_TRADE_VOLUME
    empirical_max_trade_volume      NUMERIC(24,2),          -- LQA_EMPIRICAL_MAX_TRADE_VOLUME
    empirical_lookback_period       INTEGER,                -- LQA_EMPIRICAL_LOOKBACK_PERIOD
    empirical_total_trade_volume    NUMERIC(24,2),          -- LQA_EMPIRICAL_TOTAL_TRADE_VOLUME
    data_source                     VARCHAR(16)  NOT NULL DEFAULT 'BBG', -- BBG / PROXY
    loaded_at                       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, security_code)
);

COMMENT ON TABLE fsi.mktdata_lqa IS '彭博 LQA 证券流动性评估：LQAP 组合流动性分析的输入，不是持仓主数据';
COMMENT ON COLUMN fsi.mktdata_lqa.price_volatility IS 'LQA_PRICE_VOLATILITY：3% 记为 0.03';
COMMENT ON COLUMN fsi.mktdata_lqa.expected_daily_volume IS 'LQA_EXPECTED_DAILY_VOLUME：预期日成交额';
COMMENT ON COLUMN fsi.mktdata_lqa.bid_ask_spread IS 'LQA_BID_ASK_SPREAD：实际买卖价差，按价格分数存储';
COMMENT ON COLUMN fsi.mktdata_lqa.hk_sfc_port_lqdty_class IS 'LQA_HK_SFC_PORT_LQDTY_CLASS：如 1 day or less / 2-7 days / 8-30 days / Longer than 365 days';
COMMENT ON COLUMN fsi.mktdata_lqa.liq_horizon_days IS 'LQAP Liquidity Horizon（天）。有值时优先于分类和 EDV 推算';
COMMENT ON COLUMN fsi.mktdata_lqa.data_source IS 'BBG=彭博入库；PROXY=由 SFC 流动性压测字段回填，待彭博覆盖';

CREATE INDEX IF NOT EXISTS idx_mktdata_lqa_security
    ON fsi.mktdata_lqa (security_code, as_of_date DESC);

-- 尚无彭博 LQA 文件时，用已有 SFC 压测的期限 / ADTV / 价差成本回填，标记 PROXY。
INSERT INTO fsi.mktdata_lqa (
    as_of_date, security_code, expected_daily_volume, bid_ask_spread,
    hk_sfc_port_lqdty_class, liq_horizon_days, unif_mkt_imp_cost, data_source
)
SELECT DISTINCT ON (security_code)
    evaluate_date,
    security_code,
    NULLIF(adtv_30d, 0),
    CASE WHEN market_value > 0 AND bid_ask_cost IS NOT NULL
         THEN bid_ask_cost / market_value END,
    CASE liquidation_bucket
        WHEN '1D' THEN '1 day or less'
        WHEN '2-7D' THEN '2-7 days'
        WHEN '8-30D' THEN '8-30 days'
        WHEN '31-90D' THEN '31-90 days'
        ELSE 'Longer than 365 days'
    END,
    liquidation_days,
    CASE WHEN market_value > 0 AND bid_ask_cost IS NOT NULL
         THEN bid_ask_cost / market_value END,
    'PROXY'
FROM fsi.sfc_liquidity_stress
WHERE scenario = 'NORMAL'
ORDER BY security_code, evaluate_date DESC
ON CONFLICT (as_of_date, security_code) DO NOTHING;
