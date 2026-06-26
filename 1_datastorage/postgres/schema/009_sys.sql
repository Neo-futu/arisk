-- ============================================================
-- 008_sys.sql  系統日誌層  (prefix: svc_sys_)
-- FSI Financial Services Intelligence Platform
-- 涵蓋：操作日誌（全平台六層關鍵操作記錄）
-- 依賴：001_schema_init.sql
-- ============================================================

DO $$ BEGIN
  CREATE TYPE fsi.log_level AS ENUM (
    'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE fsi.log_category AS ENUM (
    'API_ACCESS',    -- HTTP請求/響應
    'AGENT_ACTION',  -- Agent執行步驟
    'REVIEW_EVENT',  -- 審核流程事件
    'ETL_JOB',       -- 數據載入/ETL
    'RISK_CALC',     -- 風控計算
    'PERF_CALC',     -- 業績計算
    'MCP_CALL',      -- MCP工具調用
    'AUTH',          -- 認證/授權
    'SYSTEM',        -- 系統事件
    'DATA_WRITE',    -- 數據庫寫入
    'SCHEDULER'      -- Celery定時任務
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS fsi.svc_sys_op_log (
    log_id      BIGSERIAL           PRIMARY KEY,
    log_time    TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    level       fsi.log_level       NOT NULL DEFAULT 'INFO',
    category    fsi.log_category    NOT NULL,
    actor       VARCHAR(128)        NOT NULL,   -- user_id / agent_name / system
    actor_type  VARCHAR(32)         NOT NULL DEFAULT 'system',  -- human/agent/system/scheduler
    action      VARCHAR(256)        NOT NULL,
    port_id     VARCHAR(16),
    task_id     VARCHAR(128),
    review_id   UUID,
    session_id  VARCHAR(128),
    http_method VARCHAR(8),
    http_path   VARCHAR(512),
    http_status SMALLINT,
    duration_ms INTEGER,
    status      VARCHAR(32)         NOT NULL DEFAULT 'ok',  -- ok/error/timeout/blocked
    detail      TEXT,
    extra       JSONB               NOT NULL DEFAULT '{}',
    service     VARCHAR(64)         NOT NULL DEFAULT 'fsi-risk-platform',
    host        VARCHAR(128),
    version     VARCHAR(32)
);

COMMENT ON TABLE  fsi.svc_sys_op_log IS '操作日誌：全平台六層關鍵操作記錄，審計/排障/監控用';
COMMENT ON COLUMN fsi.svc_sys_op_log.actor_type IS 'human=人工 / agent=AI agent / system=系統 / scheduler=定時任務';
COMMENT ON COLUMN fsi.svc_sys_op_log.status IS 'ok=成功 / error=失敗 / timeout=超時 / blocked=被審核攔截';

CREATE INDEX IF NOT EXISTS idx_svc_sys_log_time     ON fsi.svc_sys_op_log(log_time DESC);
CREATE INDEX IF NOT EXISTS idx_svc_sys_log_category ON fsi.svc_sys_op_log(category, log_time DESC);
CREATE INDEX IF NOT EXISTS idx_svc_sys_log_actor    ON fsi.svc_sys_op_log(actor, log_time DESC);
CREATE INDEX IF NOT EXISTS idx_svc_sys_log_port     ON fsi.svc_sys_op_log(port_id, log_time DESC) WHERE port_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_svc_sys_log_level    ON fsi.svc_sys_op_log(level) WHERE level IN ('WARNING','ERROR','CRITICAL');
CREATE INDEX IF NOT EXISTS idx_svc_sys_log_task     ON fsi.svc_sys_op_log(task_id) WHERE task_id IS NOT NULL;
