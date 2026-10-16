-- ============================================================
-- 024b_mktdata_lqa_from_holdings.sql
-- mktdata_lqa 由持仓 + ADTV + 资产类别价差参数计算写入，不再从 sfc_liquidity_stress 回填。
-- 日常路径：产品压力测试 API 在计算时调用 Python 同一口径并落库 data_source=COMPUTED。
-- 本函数仅供离线全量重算。
-- ============================================================

COMMENT ON TABLE fsi.mktdata_lqa IS '证券流动性评估：由 balance_* 持仓、mktdata_adtv、sfc_liquidity_bucket_def 计算；COMPUTED=接口计算写入';
COMMENT ON COLUMN fsi.mktdata_lqa.data_source IS 'COMPUTED=接口按持仓计算；DERIVED=历史兼容';
COMMENT ON COLUMN fsi.mktdata_lqa.liq_horizon_days IS '变现天数：现金/隔夜存款=0；回购=剩余期限；债券/CD=fsi.lqa_fi_horizon_ladder 方案A；股票类=市值/(ADTV×10%)';
COMMENT ON COLUMN fsi.mktdata_lqa.unif_mkt_imp_cost IS '统一市场冲击成本=资产类别 NORMAL bid_ask_cost_bps/10000';

CREATE OR REPLACE FUNCTION fsi.refresh_mktdata_lqa()
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    inserted integer;
BEGIN
    DELETE FROM fsi.mktdata_lqa WHERE data_source IN ('DERIVED', 'PROXY', 'COMPUTED');

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
    WITH holdings AS (
        SELECT DISTINCT ON (security_code)
            evaluate_date, security_code, security_name, asset_category,
            market_value, duration, remaining_days, sector, is_overnight
        FROM (
            SELECT evaluate_date, security_code, COALESCE(security_name, security_code) AS security_name,
                   asset_subtype::text AS asset_category,
                   COALESCE(market_value_base, market_value, 0) AS market_value,
                   duration, remaining_days, sector, FALSE AS is_overnight
            FROM fsi.balance_bond
            UNION ALL
            SELECT evaluate_date, security_code, COALESCE(security_name, security_code),
                   'CD', COALESCE(market_value_base, market_value, principal, 0),
                   duration, remaining_days, NULL, FALSE
            FROM fsi.balance_cd
            UNION ALL
            SELECT evaluate_date, deposit_id, COALESCE(deposit_name, deposit_id),
                   'DEPOSIT', COALESCE(total_value_base, total_value, principal, 0),
                   NULL, remaining_days, NULL, COALESCE(is_overnight, FALSE)
            FROM fsi.balance_deposit
            UNION ALL
            SELECT evaluate_date, cash_account_id, COALESCE(account_name, cash_account_id),
                   'CASH', COALESCE(amount_base_ccy, amount, 0),
                   NULL, 0, NULL, TRUE
            FROM fsi.balance_cash
            UNION ALL
            SELECT evaluate_date, repo_id, COALESCE(pledged_security_name, repo_id),
                   CASE WHEN UPPER(repo_type) IN ('REV', 'REV_REPO', 'REVERSE') THEN 'REV_REPO' ELSE 'REPO' END,
                   COALESCE(total_value, principal, 0),
                   NULL, remaining_days, NULL, FALSE
            FROM fsi.balance_repo
        ) x
        WHERE market_value <> 0
        ORDER BY security_code, evaluate_date DESC
    ),
    enriched AS (
        SELECT
            h.evaluate_date AS as_of_date,
            h.security_code,
            h.asset_category,
            h.duration AS duration_years,
            CASE WHEN COALESCE(h.duration, 0) <= 0 THEN 0 ELSE h.duration * 0.01 END AS price_volatility,
            CASE
                WHEN COALESCE(a.adtv_30d, 0) > 0 THEN a.adtv_30d
                WHEN h.asset_category IN ('CASH', 'DEPOSIT', 'REV_REPO') THEN h.market_value
                ELSE NULL
            END AS expected_daily_volume,
            COALESCE(d.bid_ask_cost_bps, 0) / 10000.0 AS bid_ask_spread,
            COALESCE(d.bid_ask_cost_bps, 0) AS spread_bps,
            COALESCE(NULLIF(h.sector, ''), CASE h.asset_category
                WHEN 'CASH' THEN 'Cash'
                WHEN 'DEPOSIT' THEN 'Deposit'
                WHEN 'REV_REPO' THEN 'Reverse Repo'
                WHEN 'REPO' THEN 'Repo'
                WHEN 'CD' THEN 'Certificate of Deposit'
                WHEN 'BOND_GOVT' THEN 'Government'
                WHEN 'BOND_CORP' THEN 'Corporate'
                ELSE h.asset_category END) AS liquidity_sector,
            CASE
                WHEN h.asset_category = 'CASH' THEN 0
                WHEN h.asset_category = 'DEPOSIT' AND h.is_overnight THEN 0
                WHEN h.asset_category = 'DEPOSIT' THEN GREATEST(COALESCE(h.remaining_days, 0), 0)
                WHEN h.asset_category IN ('REV_REPO', 'REPO') THEN GREATEST(COALESCE(h.remaining_days, 1), 0)
                -- 债券/CD：方案 A，读 fsi.lqa_fi_horizon_ladder（不用 ADTV×参与率）
                WHEN h.asset_category IN ('BOND_GOVT', 'BOND_CORP', 'BOND_FLOAT', 'CD') THEN (
                    SELECT l.horizon_days
                    FROM fsi.lqa_fi_horizon_ladder l
                    WHERE l.ladder_id = 'DEFAULT'
                      AND l.is_active = TRUE
                      AND (l.max_bid_ask_bps IS NULL OR COALESCE(d.bid_ask_cost_bps, 0) <= l.max_bid_ask_bps)
                    ORDER BY l.band_seq
                    LIMIT 1
                )
                -- 股票类：参与率 × ADTV
                WHEN h.asset_category IN ('EQUITY', 'STOCK', 'ETF', 'FUND', 'REIT')
                     AND COALESCE(a.adtv_30d, 0) > 0 AND h.market_value > 0
                    THEN GREATEST(h.market_value / (a.adtv_30d * 0.10), 1)
                WHEN h.remaining_days IS NOT NULL THEN GREATEST(h.remaining_days, 0)
                ELSE NULL
            END AS liq_horizon_days,
            COALESCE(a.sample_days, 30) AS sample_days,
            COALESCE(a.adtv_date, h.evaluate_date) AS adtv_date
        FROM holdings h
        LEFT JOIN fsi.sfc_liquidity_bucket_def d
          ON d.asset_category = h.asset_category AND d.scenario = 'NORMAL'
        LEFT JOIN LATERAL (
            SELECT adtv_30d, sample_days, adtv_date
            FROM fsi.mktdata_adtv
            WHERE security_code = h.security_code
              AND adtv_date <= h.evaluate_date
            ORDER BY adtv_date DESC
            LIMIT 1
        ) a ON TRUE
    )
    SELECT
        as_of_date,
        security_code,
        asset_category,
        duration_years,
        price_volatility,
        expected_daily_volume,
        bid_ask_spread,
        spread_bps,
        GREATEST(1, LEAST(100,
            CASE asset_category
                WHEN 'CASH' THEN 98
                WHEN 'DEPOSIT' THEN 92
                WHEN 'REV_REPO' THEN 88
                WHEN 'BOND_GOVT' THEN 80
                WHEN 'CD' THEN 70
                WHEN 'BOND_FLOAT' THEN 62
                WHEN 'BOND_CORP' THEN 48
                ELSE 40
            END - COALESCE(liq_horizon_days, 0) * 0.15
        )),
        liquidity_sector,
        CASE
            WHEN liq_horizon_days IS NULL THEN NULL
            WHEN liq_horizon_days <= 1 THEN '1 day or less'
            WHEN liq_horizon_days <= 7 THEN '2-7 days'
            WHEN liq_horizon_days <= 30 THEN '8-30 days'
            WHEN liq_horizon_days <= 90 THEN '31-90 days'
            WHEN liq_horizon_days <= 365 THEN '91-365 days'
            ELSE 'Longer than 365 days'
        END,
        liq_horizon_days,
        bid_ask_spread,
        CASE WHEN expected_daily_volume IS NULL THEN NULL ELSE sample_days END,
        as_of_date,
        expected_daily_volume,
        adtv_date,
        CASE WHEN expected_daily_volume IS NULL THEN NULL ELSE 0 END,
        expected_daily_volume,
        expected_daily_volume,
        CASE WHEN expected_daily_volume IS NULL THEN NULL ELSE sample_days END,
        CASE WHEN expected_daily_volume IS NULL THEN NULL ELSE expected_daily_volume * sample_days END,
        'COMPUTED'
    FROM enriched;

    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN inserted;
END;
$$;
