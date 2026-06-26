-- ============================================================
-- 007_workflow.sql  人工審核工作流層  (prefix: svc_wf_)
-- FSI Financial Services Intelligence Platform
-- 涵蓋：審核請求 · 審核決策 · 審計日誌 · Agent 阻塞點
-- 依賴：001_schema_init.sql
-- ============================================================

-- ── 工作流 ENUM 類型 ─────────────────────────────────────────

DO $$ BEGIN
  CREATE TYPE fsi.review_status AS ENUM (
    'PENDING',    -- 等待審核
    'IN_REVIEW',  -- 審核員已認領
    'APPROVED',   -- 已批准
    'REJECTED',   -- 已拒絕
    'EXPIRED',    -- 超時未處理
    'CANCELLED'   -- 觸發方主動撤回
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE fsi.review_category AS ENUM (
    'COMPLIANCE_BREACH', -- SFC守則違規（強制審核）
    'HIGH_RISK',         -- VaR/暴露超閾值
    'REPORT_PUBLISH',    -- 報告對外發布前
    'DATA_WRITE',        -- 批量寫入DB前
    'DATA_LOAD',         -- 新持倉文件載入
    'AGENT_HANDOFF',     -- Agent交接到下一步驟
    'MANUAL'             -- 人工手動提交
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ────────────────────────────────────────────────────────────
-- 1. 審核請求主表
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_wf_review_request (
    review_id       UUID                 PRIMARY KEY DEFAULT gen_random_uuid(),
    category        fsi.review_category  NOT NULL,
    status          fsi.review_status    NOT NULL DEFAULT 'PENDING',

    triggered_by    VARCHAR(128)         NOT NULL,  -- agent_id / user_id / task_id
    task_id         VARCHAR(128),
    port_id         VARCHAR(16),
    as_of_date      DATE,

    title           VARCHAR(512)         NOT NULL,
    summary         TEXT                 NOT NULL,
    payload         JSONB                NOT NULL DEFAULT '{}',
    artefact_path   VARCHAR(1024),
    artefact_url    VARCHAR(1024),

    priority        SMALLINT             NOT NULL DEFAULT 2,  -- 1=緊急 2=正常 3=低
    sla_minutes     INTEGER              DEFAULT 60,
    expires_at      TIMESTAMPTZ,

    created_at      TIMESTAMPTZ          NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ          NOT NULL DEFAULT NOW(),

    assigned_to     VARCHAR(128),
    assigned_at     TIMESTAMPTZ,

    -- AI 審核（小富）
    ai_reviewer         VARCHAR(64),
    ai_review_at        TIMESTAMPTZ,
    ai_recommendation   VARCHAR(32),                -- APPROVE/REJECT/ESCALATE/REQUIRE_HUMAN
    ai_risk_level       VARCHAR(16),                -- LOW/MEDIUM/HIGH/CRITICAL
    ai_review_result    JSONB,
    ai_auto_approved    BOOLEAN DEFAULT FALSE
);
COMMENT ON TABLE  fsi.svc_wf_review_request IS '審核請求主表：合規違規/高風險/報告發布等場景的人工審核入口';
COMMENT ON COLUMN fsi.svc_wf_review_request.priority IS '1=緊急（SFC違規）/ 2=正常 / 3=低';
COMMENT ON COLUMN fsi.svc_wf_review_request.ai_auto_approved IS 'AI（小富）自動批准標誌，無人工介入';

CREATE INDEX IF NOT EXISTS idx_svc_wf_req_status   ON fsi.svc_wf_review_request(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_svc_wf_req_port     ON fsi.svc_wf_review_request(port_id, as_of_date);
CREATE INDEX IF NOT EXISTS idx_svc_wf_req_category ON fsi.svc_wf_review_request(category, status);

-- ────────────────────────────────────────────────────────────
-- 2. 審核決策記錄
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_wf_review_decision (
    decision_id     BIGSERIAL    PRIMARY KEY,
    review_id       UUID         NOT NULL,
    reviewer        VARCHAR(128) NOT NULL,
    action          VARCHAR(32)  NOT NULL,  -- APPROVE/REJECT/REQUEST_CHANGES/ESCALATE
    notes           TEXT,
    override_reason TEXT,
    decided_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE fsi.svc_wf_review_decision IS '審核決策記錄：支持多輪 back-and-forth，每次決策獨立記錄';

CREATE INDEX IF NOT EXISTS idx_svc_wf_dec_review ON fsi.svc_wf_review_decision(review_id);

-- ────────────────────────────────────────────────────────────
-- 3. 不可篡改審計日誌（Append-Only）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_wf_audit_log (
    log_id      BIGSERIAL    PRIMARY KEY,
    event_time  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    event_type  VARCHAR(64)  NOT NULL,   -- REVIEW_CREATED/APPROVED/REJECTED/AGENT_BLOCKED
    actor       VARCHAR(128) NOT NULL,
    review_id   UUID,
    port_id     VARCHAR(16),
    task_id     VARCHAR(128),
    details     JSONB        NOT NULL DEFAULT '{}',
    ip_address  VARCHAR(64),
    session_id  VARCHAR(128)
);
COMMENT ON TABLE  fsi.svc_wf_audit_log IS '不可篡改審計日誌：append-only，合規存檔用，禁止UPDATE/DELETE';
COMMENT ON COLUMN fsi.svc_wf_audit_log.event_type IS 'REVIEW_CREATED/APPROVED/REJECTED/AGENT_BLOCKED 等事件類型';

CREATE INDEX IF NOT EXISTS idx_svc_wf_audit_time  ON fsi.svc_wf_audit_log(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_svc_wf_audit_port  ON fsi.svc_wf_audit_log(port_id, event_time DESC);

-- ────────────────────────────────────────────────────────────
-- 4. Agent 阻塞點記錄
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fsi.svc_wf_agent_checkpoint (
    checkpoint_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id       UUID         NOT NULL,
    agent_name      VARCHAR(128) NOT NULL,
    task_id         VARCHAR(128) NOT NULL,
    checkpoint_name VARCHAR(256) NOT NULL,   -- pre_db_write / pre_report_publish
    blocked_action  TEXT         NOT NULL,
    context_snapshot JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    unblocked_at    TIMESTAMPTZ,
    unblock_action  VARCHAR(32)              -- APPROVED/REJECTED
);
COMMENT ON TABLE  fsi.svc_wf_agent_checkpoint IS 'Agent阻塞點：Agent在此暫停等待人工審核，審核後繼續或中止';
COMMENT ON COLUMN fsi.svc_wf_agent_checkpoint.checkpoint_name IS '如 pre_db_write / pre_report_publish / pre_position_load';

CREATE INDEX IF NOT EXISTS idx_svc_wf_ckpt_task ON fsi.svc_wf_agent_checkpoint(task_id, review_id);

-- 超時掃描（由 Celery beat 定期調用）
CREATE OR REPLACE FUNCTION fsi.expire_stale_reviews()
RETURNS INTEGER AS $$
DECLARE affected INTEGER;
BEGIN
    UPDATE fsi.svc_wf_review_request
    SET status = 'EXPIRED'
    WHERE status IN ('PENDING', 'IN_REVIEW')
      AND expires_at IS NOT NULL
      AND expires_at < NOW();
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql;
