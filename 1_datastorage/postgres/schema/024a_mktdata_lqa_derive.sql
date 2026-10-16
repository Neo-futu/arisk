-- ============================================================
-- 024a_mktdata_lqa_derive.sql
-- mktdata_lqa 改为由资管持仓与流动性压测推导，不依赖外部行情供应商文件。
-- 来源：sfc_liquidity_stress / sfc_liquidity_bucket_def / mktdata_adtv / balance_bond
-- ============================================================

ALTER TABLE fsi.mktdata_lqa ADD COLUMN IF NOT EXISTS asset_category VARCHAR(32);
ALTER TABLE fsi.mktdata_lqa ADD COLUMN IF NOT EXISTS duration_years NUMERIC(12,8);
ALTER TABLE fsi.mktdata_lqa ADD COLUMN IF NOT EXISTS spread_bps NUMERIC(10,4);

COMMENT ON TABLE fsi.mktdata_lqa IS '证券流动性评估：由持仓、SFC 流动性压测、ADTV 与资产类别买卖价差推导，供 LQAP 使用';
COMMENT ON COLUMN fsi.mktdata_lqa.price_volatility IS '年化价格波动（小数）。优先无行情时用有效久期 × 1% 收益率波动';
COMMENT ON COLUMN fsi.mktdata_lqa.expected_daily_volume IS '预期日成交额：ADTV>0 取其值；现金/存款/逆回购取市值（当日可全额变现）';
COMMENT ON COLUMN fsi.mktdata_lqa.bid_ask_spread IS '买卖价差（价格分数）= 资产类别 NORMAL 场景 bid_ask_cost_bps / 10000';
COMMENT ON COLUMN fsi.mktdata_lqa.sector_score IS '流动性板块得分 1–100：资产类别基准分减去变现天数惩罚';
COMMENT ON COLUMN fsi.mktdata_lqa.liquidity_sector IS '债券板块；无板块时用资产类别';
COMMENT ON COLUMN fsi.mktdata_lqa.hk_sfc_port_lqdty_class IS '由完全变现天数 / liquidation_bucket 归入的流动性分类';
COMMENT ON COLUMN fsi.mktdata_lqa.unif_mkt_imp_cost IS '统一市场冲击成本（价格分数）= 压测买卖价差成本 / 市值，否则同 bid_ask_spread';
COMMENT ON COLUMN fsi.mktdata_lqa.empirical_trade_count IS 'ADTV 样本天数。成交明细未入库时用回看窗口天数';
COMMENT ON COLUMN fsi.mktdata_lqa.empirical_total_trade_volume IS '日均成交额 × 回看天数';
COMMENT ON COLUMN fsi.mktdata_lqa.data_source IS 'DERIVED=由平台资管与流动性表刷新';

CREATE OR REPLACE FUNCTION fsi.refresh_mktdata_lqa()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    inserted integer;
BEGIN
    DELETE FROM fsi.mktdata_lqa WHERE data_source IN ('DERIVED', 'PROXY', 'BBG', 'COMPUTED');

    INSERT INTO fsi.mktdata_lqa (
        as_of_date, security_code, asset_category, duration_years,
        price_volatility, expected_daily_volume, bid_ask_spread, spread_bps,
        sector_score, liquidity_sector, hk_sfc_port_lqdty_class, liq_horizon_days,
        unif_mkt_imp_cost,
        empirical_trade_count, empirical_evaluation_date, empirical_min_trade_volume,
        empirical_source_date, empirical_days_since_last_trade, empirical_avg_trade_volume,
        empirical_max_trade_volume, empirical_lookback_period, empirical_total_trade_volume,
        data_source
    )
    SELECT
        s.evaluate_date,
        s.security_code,
        s.asset_category,
        s.duration,
        CASE
            WHEN COALESCE(s.duration, 0) <= 0 THEN 0
            ELSE s.duration * 0.01
        END,
        CASE
            WHEN COALESCE(a.adtv_30d, 0) > 0 THEN a.adtv_30d
            WHEN COALESCE(s.adtv_30d, 0) > 0 THEN s.adtv_30d
            WHEN s.asset_category IN ('CASH', 'DEPOSIT', 'REV_REPO') THEN s.market_value
            WHEN COALESCE(s.tradable_size, 0) > 0 THEN s.tradable_size / 0.10
            ELSE s.market_value
        END,
        COALESCE(d.bid_ask_cost_bps, 0) / 10000.0,
        COALESCE(d.bid_ask_cost_bps, 0),
        GREATEST(1, LEAST(100,
            CASE s.asset_category
                WHEN 'CASH' THEN 98
                WHEN 'DEPOSIT' THEN 92
                WHEN 'REV_REPO' THEN 88
                WHEN 'BOND_GOVT' THEN 80
                WHEN 'CD' THEN 70
                WHEN 'BOND_FLOAT' THEN 62
                WHEN 'BOND_CORP' THEN 48
                ELSE 40
            END - COALESCE(s.liquidation_days, 0) * 0.15
        )),
        COALESCE(NULLIF(b.sector, ''), CASE s.asset_category
            WHEN 'CASH' THEN 'Cash'
            WHEN 'DEPOSIT' THEN 'Deposit'
            WHEN 'REV_REPO' THEN 'Reverse Repo'
            WHEN 'REPO' THEN 'Repo'
            WHEN 'CD' THEN 'Certificate of Deposit'
            WHEN 'BOND_GOVT' THEN 'Government'
            WHEN 'BOND_CORP' THEN 'Corporate'
            WHEN 'BOND_FLOAT' THEN 'Floating Rate'
            ELSE s.asset_category
        END),
        CASE
            WHEN COALESCE(s.liquidation_days, 0) <= 1 THEN '1 day or less'
            WHEN s.liquidation_days <= 7 THEN '2-7 days'
            WHEN s.liquidation_days <= 30 THEN '8-30 days'
            WHEN s.liquidation_days <= 90 THEN '31-90 days'
            WHEN s.liquidation_days <= 365 THEN '91-365 days'
            ELSE 'Longer than 365 days'
        END,
        s.liquidation_days,
        CASE
            WHEN s.market_value > 0 AND s.bid_ask_cost IS NOT NULL THEN s.bid_ask_cost / s.market_value
            ELSE COALESCE(d.bid_ask_cost_bps, 0) / 10000.0
        END,
        COALESCE(a.sample_days, 30),
        s.evaluate_date,
        CASE
            WHEN COALESCE(a.adtv_30d, 0) > 0 THEN a.adtv_30d
            WHEN COALESCE(s.adtv_30d, 0) > 0 THEN s.adtv_30d
            WHEN s.asset_category IN ('CASH', 'DEPOSIT', 'REV_REPO') THEN s.market_value
            ELSE NULLIF(s.tradable_size, 0)
        END,
        COALESCE(a.adtv_date, s.evaluate_date),
        0,
        CASE
            WHEN COALESCE(a.adtv_30d, 0) > 0 THEN a.adtv_30d
            WHEN COALESCE(s.adtv_30d, 0) > 0 THEN s.adtv_30d
            WHEN s.asset_category IN ('CASH', 'DEPOSIT', 'REV_REPO') THEN s.market_value
            ELSE NULLIF(s.tradable_size, 0)
        END,
        CASE
            WHEN COALESCE(a.adtv_30d, 0) > 0 THEN a.adtv_30d
            WHEN COALESCE(s.adtv_30d, 0) > 0 THEN s.adtv_30d
            WHEN s.asset_category IN ('CASH', 'DEPOSIT', 'REV_REPO') THEN s.market_value
            ELSE NULLIF(s.tradable_size, 0)
        END,
        COALESCE(a.sample_days, 30),
        (
            CASE
                WHEN COALESCE(a.adtv_30d, 0) > 0 THEN a.adtv_30d
                WHEN COALESCE(s.adtv_30d, 0) > 0 THEN s.adtv_30d
                WHEN s.asset_category IN ('CASH', 'DEPOSIT', 'REV_REPO') THEN s.market_value
                WHEN COALESCE(s.tradable_size, 0) > 0 THEN s.tradable_size / 0.10
                ELSE s.market_value
            END
        ) * COALESCE(a.sample_days, 30),
        'DERIVED'
    FROM (
        SELECT DISTINCT ON (evaluate_date, security_code)
            evaluate_date, security_code, asset_category, market_value, duration,
            adtv_30d, tradable_size, bid_ask_cost, liquidation_days, liquidation_bucket
        FROM fsi.sfc_liquidity_stress
        WHERE scenario = 'NORMAL'
          AND NULLIF(btrim(security_code), '') IS NOT NULL
        ORDER BY evaluate_date, security_code, market_value DESC
    ) s
    LEFT JOIN fsi.sfc_liquidity_bucket_def d
        ON d.asset_category = s.asset_category AND d.scenario = 'NORMAL'
    LEFT JOIN LATERAL (
        SELECT adtv_30d, sample_days, adtv_date
        FROM fsi.mktdata_adtv
        WHERE security_code = s.security_code
          AND adtv_date <= s.evaluate_date
        ORDER BY adtv_date DESC
        LIMIT 1
    ) a ON TRUE
    LEFT JOIN LATERAL (
        SELECT sector
        FROM fsi.balance_bond
        WHERE security_code = s.security_code
          AND sector IS NOT NULL
          AND btrim(sector) <> ''
        ORDER BY evaluate_date DESC
        LIMIT 1
    ) b ON TRUE
    ON CONFLICT (as_of_date, security_code) DO UPDATE SET
        asset_category = EXCLUDED.asset_category,
        duration_years = EXCLUDED.duration_years,
        price_volatility = EXCLUDED.price_volatility,
        expected_daily_volume = EXCLUDED.expected_daily_volume,
        bid_ask_spread = EXCLUDED.bid_ask_spread,
        spread_bps = EXCLUDED.spread_bps,
        sector_score = EXCLUDED.sector_score,
        liquidity_sector = EXCLUDED.liquidity_sector,
        hk_sfc_port_lqdty_class = EXCLUDED.hk_sfc_port_lqdty_class,
        liq_horizon_days = EXCLUDED.liq_horizon_days,
        unif_mkt_imp_cost = EXCLUDED.unif_mkt_imp_cost,
        data_source = EXCLUDED.data_source,
        loaded_at = NOW();

    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN inserted;
END;
$$;

-- 不在此强制全量刷新；024b 会 REPLACE 本函数并改为按持仓计算。
