-- ============================================================
-- 007_risk.sql  服務/計算結果層 — 風控業績  (prefix: svc_risk_)
-- FSI Financial Services Intelligence Platform
-- Layer 3 of 3: Service / Computed Results
--
-- 職責：存儲由 2_processing 計算引擎輸出的風控與業績指標
-- 只讀查詢層；寫入方為 Celery worker / 風控計算服務
-- ============================================================

CREATE TABLE IF NOT EXISTS fsi.svc_risk_snapshot (
    snapshot_id           BIGSERIAL    PRIMARY KEY,
    port_id               VARCHAR(16)  NOT NULL,
    as_of_date            DATE         NOT NULL,
    calc_ts               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    total_nav_base        NUMERIC(24,6),
    wam_days              NUMERIC(8,2),               -- 加權平均期限（SFC MMF ≤60天）
    wal_days              NUMERIC(8,2),               -- 加權平均有效期（SFC MMF ≤120天）
    daily_liquid_pct      NUMERIC(8,4),               -- 每日流動資產（SFC MMF ≥7.5%）
    weekly_liquid_pct     NUMERIC(8,4),               -- 每週流動資產（SFC MMF ≥15%）
    top1_issuer_pct       NUMERIC(8,4),
    top5_issuer_pct       NUMERIC(8,4),
    max_single_entity_pct NUMERIC(8,4),               -- 單一發行人上限（SFC ≤10%）
    max_group_pct         NUMERIC(8,4),               -- 集團敞口上限（SFC ≤20%）
    investment_grade_pct  NUMERIC(8,4),
    unrated_pct           NUMERIC(8,4),
    var_1d_95             NUMERIC(12,6),
    var_1d_99             NUMERIC(12,6),
    var_10d_99            NUMERIC(12,6),
    cvar_1d_99            NUMERIC(12,6),
    portfolio_duration    NUMERIC(10,6),
    portfolio_dv01_base   NUMERIC(16,4),
    ir_sensitivity_100bp  NUMERIC(16,4),
    max_ccy_exposure_pct  NUMERIC(8,4),
    fx_hedge_ratio        NUMERIC(8,4),
    is_compliant          BOOLEAN,
    breach_flags          JSONB,                      -- {"WAM_BREACH": true, ...}
    breach_details        JSONB,                      -- [{rule_code, actual, limit, dimension}]
    UNIQUE (port_id, as_of_date)
);
COMMENT ON TABLE  fsi.svc_risk_snapshot IS '[Layer3 服務表] 組合風控快照：計算引擎每日輸出';
COMMENT ON COLUMN fsi.svc_risk_snapshot.breach_details IS '違規明細：[{rule_code, actual_value, limit_value, dimension}]';

CREATE INDEX IF NOT EXISTS idx_svc_risk_snap_port   ON fsi.svc_risk_snapshot(port_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_svc_risk_snap_breach ON fsi.svc_risk_snapshot(is_compliant) WHERE is_compliant = FALSE;

-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_risk_exposure (
    exposure_id       BIGSERIAL    PRIMARY KEY,
    port_id           VARCHAR(16)  NOT NULL,
    as_of_date        DATE         NOT NULL,
    dimension         VARCHAR(64)  NOT NULL,   -- ASSET_CLASS/ISSUER/CURRENCY/COUNTRY/SECTOR/MATURITY_BUCKET/RATING
    category          VARCHAR(256) NOT NULL,
    currency          CHAR(3),
    market_value      NUMERIC(24,2),
    market_value_base NUMERIC(24,2),
    weight_pct        NUMERIC(10,6),
    item_count        INTEGER,
    UNIQUE (port_id, as_of_date, dimension, category)
);
COMMENT ON TABLE fsi.svc_risk_exposure IS '[Layer3 服務表] 暴露明細：多維度持倉拆解，支持可視化報表';

CREATE INDEX IF NOT EXISTS idx_svc_risk_exp_port ON fsi.svc_risk_exposure(port_id, as_of_date DESC, dimension);

-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_risk_perf (
    perf_id          BIGSERIAL    PRIMARY KEY,
    port_id          VARCHAR(16)  NOT NULL,
    class_id         VARCHAR(64),
    as_of_date       DATE         NOT NULL,
    period_type      VARCHAR(16)  NOT NULL,    -- 1D/1W/1M/3M/6M/YTD/1Y/3Y/5Y/SI
    fund_return      NUMERIC(12,8),
    benchmark_return NUMERIC(12,8),
    active_return    NUMERIC(12,8),
    tracking_error   NUMERIC(12,8),
    sharpe_ratio     NUMERIC(12,8),
    info_ratio       NUMERIC(12,8),
    max_drawdown     NUMERIC(12,8),
    calmar_ratio     NUMERIC(12,8),
    sortino_ratio    NUMERIC(12,8),
    UNIQUE (port_id, class_id, as_of_date, period_type)
);
COMMENT ON TABLE  fsi.svc_risk_perf IS '[Layer3 服務表] 業績指標：多時間段回報/風險調整指標';
COMMENT ON COLUMN fsi.svc_risk_perf.info_ratio IS '信息比率 = 超額收益 / 追蹤誤差';
COMMENT ON COLUMN fsi.svc_risk_perf.max_drawdown IS '最大回撤：峰值到谷值最大跌幅';

CREATE INDEX IF NOT EXISTS idx_svc_risk_perf_port ON fsi.svc_risk_perf(port_id, as_of_date DESC);
