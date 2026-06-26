-- ============================================================
-- 001_schema_init.sql  Schema 初始化
-- FSI Financial Services Intelligence Platform
-- 職責：創建 fsi schema 及全平台共用的基礎 ENUM 類型
-- 後續文件依賴此文件先執行
-- ============================================================

CREATE SCHEMA IF NOT EXISTS fsi;

-- ── 前綴命名規範 ─────────────────────────────────────────────
-- para_     參數/主數據表   Master / reference data
-- balance_  持倉數據表     Position snapshots (daily)
-- mktdata_  市場數據表     Market data (prices, rates, FX)
-- transact_ 交易記錄表     Transaction records
-- risk_     風控結果表     Risk & performance results
-- wf_       工作流表       Review / approval workflow
-- sys_      系統日誌表     Operational logs & audit trail

-- ── 全局 ENUM：資產類別 ──────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE fsi.asset_class AS ENUM (
    'CASH',         -- 現金及活期存款
    'DEPOSIT',      -- 定期存款
    'CD',           -- 存款證 Certificate of Deposit
    'CP',           -- 商業票據 Commercial Paper
    'BOND_GOVT',    -- 政府債券
    'BOND_CORP',    -- 企業債券
    'BOND_CONVERT', -- 可轉換債券
    'BOND_ABS',     -- 資產支持證券
    'STOCK',        -- 上市股票
    'FUND_PUBLIC',  -- 公募基金
    'FUND_ETF',     -- ETF
    'FUND_PRIVATE', -- 私募/對沖基金
    'FUTURES',      -- 期貨
    'OPTIONS',      -- 期權
    'REPO',         -- 正回購
    'REV_REPO',     -- 逆回購
    'FX_FORWARD',   -- 外匯遠期
    'SWAP',         -- 利率/信用互換
    'OTHER'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 全局 ENUM：組合類型 ──────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE fsi.portfolio_type AS ENUM (
    'MMF',       -- 貨幣市場基金
    'BOND',      -- 債券基金
    'EQUITY',    -- 股票基金
    'BALANCED',  -- 混合基金
    'INDEX',     -- 指數基金
    'ETF',       -- 交易所買賣基金
    'HEDGE',     -- 對沖基金
    'PRIVATE',   -- 私募基金
    'PENSION',   -- 退休金組合
    'MANDATE',   -- 全權委托
    'SMA',       -- 獨立管理賬戶
    'OTHER'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 全局 ENUM：交易方向 ──────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE fsi.trade_direction AS ENUM (
    'BUY', 'SELL', 'LONG', 'SHORT', 'COVER_LONG', 'COVER_SHORT'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 全局 ENUM：多/空標誌 ─────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE fsi.long_short_flag AS ENUM ('LONG', 'SHORT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 全局 ENUM：評級機構 ──────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE fsi.rating_agency AS ENUM (
    'SP', 'MOODY', 'FITCH', 'CSCI', 'CCX', 'LIANHE', 'INTERNAL', 'NR'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 全局 ENUM：人員職能 ──────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE fsi.person_role AS ENUM (
    'FUND_MANAGER', 'DEPUTY_MANAGER', 'RISK_OFFICER',
    'COMPLIANCE_OFFICER', 'PORTFOLIO_ANALYST', 'TRADER', 'ADMIN'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── 全局 ENUM：交易狀態 ──────────────────────────────────────
DO $$ BEGIN
  CREATE TYPE fsi.txn_status AS ENUM (
    'PENDING', 'CONFIRMED', 'SETTLED', 'CANCELLED', 'FAILED'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

