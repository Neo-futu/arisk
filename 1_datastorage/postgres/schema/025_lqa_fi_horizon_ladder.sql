-- ============================================================
-- 025_lqa_fi_horizon_ladder.sql
-- 方案 A：债券/CD Bid-Ask（bp）→ 变现天数（Horizon）可配置阶梯。
-- 权威配置表；改表后产品压力测试 API / refresh_mktdata_lqa 按新档生效。
-- 资产类报价价差本身仍在 fsi.sfc_liquidity_bucket_def.bid_ask_cost_bps。
-- ============================================================

CREATE TABLE IF NOT EXISTS fsi.lqa_fi_horizon_ladder (
    ladder_id         VARCHAR(32)  NOT NULL DEFAULT 'DEFAULT',  -- 方案标识，可并存多套
    band_seq          INTEGER      NOT NULL,                    -- 从小到大匹配顺序
    max_bid_ask_bps   NUMERIC(12,4),                            -- 本档上沿（含）；NULL=开放上沿（>上一档）
    horizon_days      NUMERIC(10,2) NOT NULL,                   -- 映射变现天数（无报价不落本表，引擎记 Not Covered）
    label             VARCHAR(64),
    note              VARCHAR(200),
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ladder_id, band_seq)
);

COMMENT ON TABLE fsi.lqa_fi_horizon_ladder IS
    'LQAP 方案A：债券/CD 相对 Bid-Ask（bp）阶梯 → 指示性变现天数；无报价由引擎判 Not Covered';
COMMENT ON COLUMN fsi.lqa_fi_horizon_ladder.ladder_id IS '阶梯方案 ID，默认 DEFAULT；可增 STRESS_STRICT 等';
COMMENT ON COLUMN fsi.lqa_fi_horizon_ladder.max_bid_ask_bps IS '本档最大 bid-ask（含）；按 band_seq 升序取首个 bps≤上沿的行；末行 NULL 表示 >上一档';
COMMENT ON COLUMN fsi.lqa_fi_horizon_ladder.horizon_days IS '映射变现天数（天）；区间取保守上沿便于落桶';

-- 方案 A 默认档（业务可 UPDATE / 增行后重算）
DELETE FROM fsi.lqa_fi_horizon_ladder WHERE ladder_id = 'DEFAULT';

INSERT INTO fsi.lqa_fi_horizon_ladder
    (ladder_id, band_seq, max_bid_ask_bps, horizon_days, label, note)
VALUES
    ('DEFAULT', 1, 10,    1.0,  '≤10 bps',   '国债/高评级 CD：区间 0.5–1 天，取上沿 1'),
    ('DEFAULT', 2, 50,    3.0,  '10–50 bps', '优质 IG 公司债：区间 2–3 天，取上沿 3'),
    ('DEFAULT', 3, 150,  10.0,  '50–150 bps','高收益债：区间 5–10 天，取上沿 10'),
    ('DEFAULT', 4, NULL, 40.0,  '>150 bps',  '极宽价差或低流动性：>30 天，落 40');
