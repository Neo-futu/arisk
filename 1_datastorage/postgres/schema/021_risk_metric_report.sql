-- ============================================================
-- 021_risk_metric_report.sql
-- 六大类风控指标报表层：按组合 + 区间落库
-- 当日区间重算并覆盖；历史区间直接读取
-- ============================================================

CREATE TABLE IF NOT EXISTS fsi.svc_risk_metric_report (
    port_id                VARCHAR(16)  NOT NULL,
    period_start           DATE         NOT NULL,
    period_end             DATE         NOT NULL,
    resolved_period_start  DATE,
    resolved_period_end    DATE,
    data_as_of             DATE,
    benchmark_id           VARCHAR(32),
    message                TEXT,
    calc_ts                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (port_id, period_start, period_end)
);
COMMENT ON TABLE fsi.svc_risk_metric_report IS '[Layer3 服务表] 六大类风控指标看板头：组合与区间';

CREATE TABLE IF NOT EXISTS fsi.svc_risk_metric (
    port_id           VARCHAR(16)   NOT NULL,
    period_start      DATE          NOT NULL,
    period_end        DATE          NOT NULL,
    category_id       VARCHAR(32)   NOT NULL,
    category_name     VARCHAR(64)   NOT NULL,
    category_name_en  VARCHAR(64),
    group_name        VARCHAR(64)   NOT NULL,
    metric_id         VARCHAR(64)   NOT NULL,
    metric_name       VARCHAR(200)  NOT NULL,
    metric_value      NUMERIC(24,8),
    value_text        VARCHAR(200),
    unit              VARCHAR(16),
    status            VARCHAR(16),
    note              TEXT,
    detail            TEXT,
    sort_no           INTEGER       NOT NULL DEFAULT 0,
    PRIMARY KEY (port_id, period_start, period_end, metric_id)
);
COMMENT ON TABLE fsi.svc_risk_metric IS '[Layer3 服务表] 六大类风控指标明细：小类与指标值';

CREATE INDEX IF NOT EXISTS idx_svc_risk_metric_port
    ON fsi.svc_risk_metric(port_id, period_end DESC, category_id, sort_no);
