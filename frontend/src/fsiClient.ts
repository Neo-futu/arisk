/**
 * ARISK — API 客戶端
 *
 * 封裝對 /api/v1/fsi/* 路由的請求（Bearer JWT 認證）。
 * 這些路由由 backend/ 代理到 2_processing FastAPI 服務。
 *
 * 使用方式（React Query）：
 *   const { data } = useQuery({
 *     queryKey: ["exposure", fundId, date],
 *     queryFn: () => fsiApi.getExposure(fundId, date).then(r => r.data),
 *   })
 */
import axios from "axios"

const BASE = (import.meta.env.VITE_API_URL as string) || ""

function authHeaders() {
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── 請求類型 ──────────────────────────────────────────────────────

export interface ExposureResult {
  fund_id: string
  as_of_date: string
  total_nav_hkd: number
  wam_days: number
  wal_days: number
  daily_liquid_pct: number
  weekly_liquid_pct: number
  is_compliant: boolean
  breach_flags: string[]
  effective_limits?: Record<string, number>
  compliance_details?: Array<{
    rule_code: string
    breach_code: string
    rule_name: string
    current_value: number
    limit_value: number
    operator: "<=" | ">="
    unit: string
    is_breached: boolean
  }>
  rule_trace?: Record<string, {
    regulatory: number
    contract: number
    internal: number
    total: number
    used_default: boolean
    direction: "MIN" | "MAX"
  }>
  by_asset_type: Record<string, { mv_hkd: number; pct: number }>
  by_currency: Record<string, { mv_hkd: number; pct: number }>
  by_maturity_bucket: Record<string, { mv_hkd: number; pct: number }>
  top_issuers: Array<{ issuer: string; mv_hkd: number; pct: number }>
}

export interface ExposureLatestDateResult {
  fund_id: string
  requested_as_of_date: string
  effective_date: string | null
}

export type PortfolioAccessLevel = "VIEW" | "MANAGE"

export interface AuthorizedPortfolio {
  port_id: string
  port_name: string
  port_name_en?: string | null
  port_type: string
  base_currency: string
  access_level: PortfolioAccessLevel
  /** Business fund manager(s) from FSI master data (para_person). */
  manager_name?: string | null
  /** Platform login accounts (iam.user) granted MANAGE access. */
  manage_users?: string | null
}

export interface AccessRoleSummary {
  id: string
  code: string
  name: string
}

export interface MyAccessContext {
  user_id: string
  is_superuser: boolean
  roles: AccessRoleSummary[]
  permission_codes: string[]
  menu_codes: string[]
  menu_paths: string[]
  portfolios: AuthorizedPortfolio[]
  can_manage_access: boolean
}

export interface AccessRole extends AccessRoleSummary {
  description?: string | null
  is_active: boolean
  permission_ids: string[]
  menu_ids: string[]
}

export interface AccessPermission {
  id: string
  name: string
  code: string
  description?: string | null
}

export interface AccessMenu {
  id: string
  name: string
  code: string
  path?: string | null
  sort_order: number
  is_active: boolean
}

export interface PortfolioCatalogItem extends Omit<AuthorizedPortfolio, "access_level"> {
  is_active: boolean
}

export interface AccessCatalog {
  roles: AccessRole[]
  permissions: AccessPermission[]
  menus: AccessMenu[]
  portfolios: PortfolioCatalogItem[]
}

export interface UserAccessConfiguration {
  user_id: string
  role_ids: string[]
  portfolios: Array<{ port_id: string; access_level: PortfolioAccessLevel }>
}

export interface UserAccessGrant {
  user_id: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  roles: AccessRoleSummary[]
  portfolios: Array<{ port_id: string; port_name: string | null; access_level: PortfolioAccessLevel }>
}

export interface PortfolioDashboardItem extends AuthorizedPortfolio {
  status: "ok" | "no_data" | "error"
  effective_date?: string | null
  total_nav_hkd?: number
  wam_days?: number
  wal_days?: number
  is_compliant?: boolean
  breach_count?: number
  breach_flags?: string[]
  error?: string
}

export interface PortfolioDashboardOverview {
  requested_as_of_date: string
  total: number
  with_data: number
  compliant: number
  breached: number
  portfolios: PortfolioDashboardItem[]
}

export interface VarResult {
  fund_id: string
  as_of_date: string
  confidence: number
  horizon_days: number
  var_hkd: number
  var_pct_nav: number
  cvar_hkd: number
  method: string
  sample_size: number
  method_requested?: string
}

export interface VarCompareResult {
  fund_id: string
  as_of_date: string
  confidence: number
  horizon_days: number
  results: VarResult[]
  max_var_pct_nav: number
}

export interface IndicatorSql {
  id: string
  title: string
  sql: string
}

export interface PortfolioBasicInfo {
  fund_id: string
  as_of_date: string
  data_date: string | null
  portfolio: {
    port_id: string
    port_name: string
    port_name_en?: string | null
    port_type?: string | null
    fund_category: "MONEY_MARKET" | "BOND" | "EQUITY" | "MIXED" | "OTHER"
    base_currency?: string | null
    inception_date?: string | null
    close_date?: string | null
    is_active?: boolean | null
    is_mmf?: boolean | null
    mmf_wam_limit_days?: number | null
    mmf_wal_limit_days?: number | null
    asset_mgr_id?: string | null
    trustee_id?: string | null
    custodian_id?: string | null
  }
  managers: Array<{
    person_id: string
    person_name: string
    person_name_en?: string | null
    role: string
    is_lead: boolean
    begin_date: string | null
    end_date: string | null
    email?: string | null
    sfc_licence_no?: string | null
    is_current: boolean
  }>
}

export interface PortfolioOverviewResult {
  fund_id: string
  as_of_date: string
  portfolio: {
    fund_id: string
    port_name: string
    portfolio_type?: string | null
    base_currency?: string | null
    inception_date?: string | null
    data_date?: string | null
    net_asset?: number | null
    shares_outstanding?: number | null
    unit_nav?: number | null
    acc_unit_nav?: number | null
    day_return?: number | null
  }
  performance: Array<{
    period: string
    start_date: string
    end_date: string
    return_pct: number
  }>
  asset_allocation: Array<{
    asset_class: string
    market_value_base: number
    weight_pct: number
  }>
  top_stocks: Array<{
    security_code: string
    security_name: string
    market_id: string
    sector: string
    currency: string
    market_value_base: number
    weight_pct: number
    unrealized_pnl: number | null
  }>
  top_bonds: Array<{
    security_code: string
    security_name: string
    market_id: string | null
    issuer_name: string
    sector: string
    currency: string
    market_value_base: number
    weight_pct: number
    accrued_interest: number | null
    ytm: number | null
    duration: number | null
    coupon_rate: number | null
    maturity_date: string | null
    remaining_days: number | null
    rating: string | null
  }>
  stock_sectors: Array<{
    sector: string
    market_value_base: number
    weight_pct: number
    position_count: number
  }>
  snapshot_dates?: {
    asset: string | null
    stock: string | null
    bond: string | null
  }
}

export interface PortfolioOverviewTimeseriesResult {
  fund_id: string
  period_start: string
  period_end: string
  points: Array<{
    date: string
    nav: number
    net_asset: number | null
    daily_return_pct: number | null
    cumulative_return_pct: number | null
  }>
}

export interface RiskIndicatorsResult {
  fund_id: string
  period_start: string
  period_end: string
  interval_return_pct: number | null
  annualized_volatility_pct: number | null
  max_drawdown_pct: number | null
  max_drawdown_start: string | null
  max_drawdown_end: string | null
  sample_size: number
  equity_turnover: {
    buy_amount: number
    sell_amount: number
    average_equity_balance: number
    period_turnover_pct: number | null
    annualized_turnover_pct: number | null
    method: string
  }
  equity_beta: {
    value: number | null
    benchmark_id: string | null
    sample_size: number
    constituents: Array<{
      security_code: string
      security_name: string
      weight_pct: number
      beta: number
      sample_size: number
    }>
  }
}

export interface RiskIndicatorTimeseriesResult {
  fund_id: string
  period_start: string
  period_end: string
  points: Array<{
    date: string
    nav: number
    daily_return_pct: number | null
    cumulative_return_pct: number | null
    rolling_volatility_pct: number | null
    drawdown_pct: number | null
    rolling_var_95_pct: number | null
  }>
}

export interface PerformanceAttributionResult {
  fund_id: string
  period_start: string
  period_end: string
  benchmark_id: string | null
  summary: {
    fund_return_pct: number
    benchmark_return_pct: number
    active_return_pct: number
    allocation_effect_pct: number
    selection_effect_pct: number
    interaction_effect_pct: number
  }
  asset_contribution: Array<{
    asset_class: string
    mtm_delta: number
    interest_income: number
    realized_gain: number
    fx_pnl: number
    fee_expense: number
    net_pnl: number
    contribution_pct: number | null
  }>
  sector_attribution: Array<{
    sector: string
    fund_weight_pct: number
    benchmark_weight_pct: number
    overweight_pct: number
    fund_return_pct: number
    benchmark_return_pct: number
    allocation_effect_pct: number
    selection_effect_pct: number
    interaction_effect_pct: number
  }>
  top_winners: SecurityPnl[]
  top_losers: SecurityPnl[]
  average_top_holdings: Array<{
    security_code: string
    security_name: string
    sector: string
    average_weight_pct: number
    holding_days: number
    net_pnl: number
  }>
}

export interface PerformanceAttributionTimeseriesResult {
  fund_id: string
  period_start: string
  period_end: string
  benchmark_id: string | null
  cumulative_points: Array<{
    date: string
    fund_cumulative_return_pct: number
    benchmark_cumulative_return_pct: number
    active_cumulative_return_pct: number
  }>
  pnl_points: Array<{
    date: string
    net_pnl: number
    contribution_pct: number | null
  }>
}

export interface SecurityPnl {
  security_code: string | null
  security_name: string
  sector: string
  net_pnl: number
  contribution_pct: number | null
}

export interface RatesCreditResult {
  fund_id: string
  as_of_date: string
  net_asset: number
  total_bond_market_value: number
  bond_exposure_pct_nav: number | null
  weighted_duration_years: number | null
  portfolio_dv01: number
  portfolio_cs01: number
  krd_buckets: Array<{
    bucket: string
    duration_weighted_mv: number
    weight_pct_bond: number
  }>
  issuer_concentration: {
    hhi: number
    top_issuers: Array<{
      issuer: string
      market_value: number
      weight_pct: number
    }>
  }
  rating_distribution: Array<{
    rating: string
    market_value: number
    weight_pct: number
  }>
  bond_count: number
}

export interface LiquidityStressResult {
  fund_id: string
  as_of_date: string
  net_asset: number
  redemption_pct: number
  rate_shock_bps: number
  liquidity_ladder: Array<{
    asset_class: string
    market_value: number
    ttl_days: number
    cumulative_market_value: number
    cumulative_pct_nav: number | null
  }>
  ttl_snapshot: {
    ttl_10pct_days: number | null
    ttl_25pct_days: number | null
    ttl_50pct_days: number | null
  }
  stress_summary: {
    redemption_amount: number
    liquid_within_7d: number
    liquidity_coverage_ratio: number | null
    stressed_bond_loss: number
    redemption_impact_cost: number
    projected_stressed_nav: number | null
  }
  historical_stress: {
    worst_1d_return_pct: number | null
    worst_5d_cumulative_return_pct: number | null
    sample_size: number
  }
  breach_flags: string[]
}

export interface PretradeRiskResult {
  fund_id: string
  as_of_date: string
  trade: {
    trade_amount: number
    trade_side: string
    asset_class: string
    duration_years: number
    issuer_name: string
  }
  current: {
    net_asset: number
    bond_market_value: number
    duration_years: number
    issuer_pct_nav: number | null
    portfolio_dv01: number
  }
  projected: {
    bond_market_value: number
    duration_years: number
    issuer_pct_nav: number | null
    portfolio_dv01: number
    tracking_error_proxy_pct: number | null
  }
  limits: {
    duration_years: number
    issuer_pct_nav: number
    tracking_error_proxy_pct: number
  }
  applied_rules?: Array<{
    application_id: number
    rule_type: string
    code: string
    name: string
    dimension: string
    limit_value: number
    limit_unit: string
    target_limit: string
  }>
  breach_flags: string[]
  decision: "ALLOW" | "ALLOW_WITH_WARNING" | "BLOCK"
}

export interface MacroDynamicsResult {
  fund_id: string
  period_start: string
  period_end: string
  fund_regime: {
    annualized_volatility_pct: number | null
    regime: string
    sample_size: number
  }
  macro_indicators: Array<{
    index_code: string
    period_return_pct: number | null
    annualized_volatility_pct: number | null
    sample_size: number
  }>
  cross_asset_correlations: Array<{
    left: string
    right: string
    correlation: number
  }>
  fund_vs_market_correlations: Array<{
    index_code: string
    correlation: number
  }>
}

export interface FactorBehaviorResult {
  fund_id: string
  period_start: string
  period_end: string
  style_exposure: {
    momentum_exposure: number | null
    low_volatility_exposure: number | null
    size_exposure: number | null
    coverage_weight: number
  }
  sector_concentration: {
    hhi: number
    weights: Array<{ sector: string; weight_pct: number }>
  }
  trading_behavior: {
    turnover_pct: number | null
    crowding_top: Array<{
      security_code: string
      security_name: string
      sector: string
      weight_pct: number
      avg_daily_volume: number
      position_quantity: number
      crowding_ratio: number | null
    }>
  }
  warnings: string[]
}

export interface UserApiKey {
  id: string
  name: string
  masked_key: string
  is_active: boolean
  created_at: string
  expires_at: string | null
  last_used_at: string | null
}

export interface CreatedUserApiKey extends UserApiKey {
  key: string
}

export interface LocalApiConfig {
  name: string
  api_base_url: string
  header_name: string
  key_prefix: string
  processing_api: {
    url: string
    header_name: string
    secret_source: string
    browser_exposed: boolean
  }
  note: string
}

export type NotificationChannel = "email" | "feishu" | "wecom"

export type NotificationChannels = Record<NotificationChannel, {
  configured: boolean
  description: string
}>

export interface Position {
  asset_id: string
  asset_name: string
  asset_type: string
  issuer_name?: string | null
  issuer_group?: string | null
  currency: string
  face_value?: number | null
  market_value?: number | null
  market_value_hkd?: number | null
  weight_pct?: number | null
  maturity_date?: string | null
  coupon_rate?: number | null
  credit_rating?: string | null
  rating_agency?: string | null
  country?: string | null
  sector?: string | null
}

export interface PositionsResponse {
  fund_id: string
  as_of_date: string
  count: number
  positions: Position[]
}

export interface AgentTaskRequest {
  task: string
  fund_id?: string
  date?: string
  mode?: "agent" | "chat"
}

export interface AgentTaskResponse {
  task_id: string
  status: string
  message: string
}

export interface AgentTaskStatus {
  status: string
  created_at?: string
  completed_at?: string
  request?: AgentTaskRequest
  result?: string
  error?: string
}

// ── 風控規則配置 ────────────────────────────────────────────────
export type RiskRuleType = "regulatory" | "contract" | "internal"

export interface RiskRule {
  id: number
  rule_type: RiskRuleType
  port_id: string
  code: string
  name: string
  name_en: string | null
  category: string | null
  source: string | null
  dimension: string
  dimension_key: string | null
  lower_limit: number | null
  upper_limit: number | null
  limit_unit: string
  limit_direction: "MIN" | "MAX" | null
  clause_ref: string | null
  mandate_ref: string | null
  client_name: string | null
  breach_action: string | null
  alert_pct: number | null
  is_hard: boolean
  effective_date: string
  expiry_date: string | null
  is_active: boolean
  description: string | null
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
  attachment_count?: number
}

export interface RiskRuleAttachment {
  id: number
  rule_type: RiskRuleType
  rule_id: number
  file_name: string
  content_type: string
  file_size: number
  note: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface RiskRuleAttachmentListResponse {
  items: RiskRuleAttachment[]
  count: number
}

export interface RegulatoryRuleBriefItem {
  code: string
  name: string | null
  name_en: string | null
  dimension: string | null
  limit_unit: string | null
  clause_ref: string | null
  description: string | null
  active_count: number
  total_count: number
  limit_brief: string
}

export interface RegulatoryRuleBriefResponse {
  items: RegulatoryRuleBriefItem[]
  count: number
}

export type RuleApplyScope = "portfolio" | "trade" | "pretrade" | "posttrade"

export interface RuleApplication {
  application_id: number
  rule_type: RiskRuleType
  rule_id: number
  rule_code: string | null
  rule_name: string | null
  rule_name_en: string | null
  apply_scope: RuleApplyScope
  port_id: string | null
  strategy_code: string | null
  instrument_type: string | null
  trade_side: "BUY" | "SELL" | "BOTH" | null
  priority: number
  effective_date: string
  expiry_date: string | null
  is_active: boolean
  note: string | null
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface RuleApplicationPayload {
  rule_type: RiskRuleType
  rule_id: number
  apply_scope: RuleApplyScope
  port_id?: string | null
  strategy_code?: string | null
  instrument_type?: string | null
  trade_side?: "BUY" | "SELL" | "BOTH" | null
  priority: number
  effective_date: string
  expiry_date?: string | null
  is_active: boolean
  note?: string | null
}

export interface RuleApplicationListResponse {
  items: RuleApplication[]
  count: number
}

export interface RiskRulePayload {
  rule_type: RiskRuleType
  port_id: string
  code: string
  name: string
  name_en?: string | null
  category?: string | null
  source?: string | null
  dimension: string
  dimension_key?: string | null
  lower_limit?: number | null
  upper_limit?: number | null
  limit_unit: string
  limit_direction?: "MIN" | "MAX" | null
  clause_ref?: string | null
  mandate_ref?: string | null
  client_name?: string | null
  breach_action?: string | null
  alert_pct?: number | null
  is_hard?: boolean
  effective_date: string
  expiry_date?: string | null
  is_active?: boolean
  description?: string | null
}

export interface RiskRuleListResponse {
  items: RiskRule[]
  count: number
}

export interface RiskRuleSummary {
  by_type: Partial<Record<RiskRuleType, { total: number; active: number }>>
  total: number
  active: number
}

// ── 定時報表 ─────────────────────────────────────────────────────
export interface Schedule {
  schedule_id: string
  name: string
  report_id: string
  report_name: string
  fund_id: string
  fund_name: string
  hour: number
  minute: number
  enabled: boolean
  run_count: number
  last_run: string | null
  last_status: "completed" | "failed" | null
  created_at: string
}

export interface ScheduleHistory {
  run_id: string
  schedule_id: string
  report_id: string
  fund_id: string
  as_of_date: string
  status: "completed" | "failed"
  output_file: string | null
  message: string
  started_at: string
  finished_at: string
}

export interface ScheduleFile {
  filename: string
  size_kb: number
  modified: string
}

// ── 報表生成 ────────────────────────────────────────────────────
export interface ReportTask {
  task_id: string
  report_id: string
  fund_id: string
  as_of_date: string
  status: "queued" | "running" | "completed" | "failed"
  progress: number
  message: string
  output_file: string | null          // 主文件（兼容舊版）
  output_files?: string[]             // 全部文件：xlsx + docx + pdf
  created_at: string
  finished_at: string | null
}

export interface AgentChatResponse {
  reply: string
  model: string
}

export interface AgentVarSkillResponse extends VarCompareResult {
  summary: string
}

// ── 用戶專屬 Agent 配置 ───────────────────────────────────────────
export interface UserAgentConfig {
  user_id:             string
  agent_name:          string | null
  default_agent_id:    string
  default_model_id:    string
  custom_instructions: string | null
  tools_enabled:       string   // JSON array string
  memory_enabled:      boolean
  rag_enabled:         boolean
  max_context_turns:   number
  created_at:          string
  updated_at:          string
}

export interface UserAgentConfigUpdate {
  agent_name?:          string | null
  default_agent_id?:    string
  default_model_id?:    string
  custom_instructions?: string | null
  tools_enabled?:       string
  memory_enabled?:      boolean
  rag_enabled?:         boolean
  max_context_turns?:   number
}

// ── Chat 持久化 ───────────────────────────────────────────────────
export interface ChatSessionRecord {
  id:         string
  title:      string
  agent_id:   string
  model_id:   string
  created_at: string
  updated_at: string
}

export interface ChatMessageRecord {
  id:         string
  session_id: string
  role:       "user" | "assistant"
  content:    string
  tool_calls: string   // JSON string
  created_at: string
}

// ── API 調用 ──────────────────────────────────────────────────────

export const fsiApi = {
  getMyAccessContext() {
    return axios.get<MyAccessContext>(`${BASE}/api/v1/access-control/me`, { headers: authHeaders() })
  },

  getAccessCatalog() {
    return axios.get<AccessCatalog>(`${BASE}/api/v1/access-control/catalog`, { headers: authHeaders() })
  },

  getUserAccess(userId: string) {
    return axios.get<UserAccessConfiguration>(`${BASE}/api/v1/access-control/users/${userId}`, { headers: authHeaders() })
  },

  getAccessGrants() {
    return axios.get<{ grants: UserAccessGrant[] }>(`${BASE}/api/v1/access-control/grants`, { headers: authHeaders() })
  },

  updateUserAccess(userId: string, data: Omit<UserAccessConfiguration, "user_id">) {
    return axios.put<UserAccessConfiguration>(`${BASE}/api/v1/access-control/users/${userId}`, data, { headers: authHeaders() })
  },

  updateRoleAccess(roleId: string, data: {
    name: string
    description?: string | null
    is_active: boolean
    permission_ids: string[]
    menu_ids: string[]
  }) {
    return axios.put<AccessRole>(`${BASE}/api/v1/access-control/roles/${roleId}`, data, { headers: authHeaders() })
  },

  createRole(data: {
    name: string
    code: string
    description?: string | null
    is_active: boolean
    permission_ids: string[]
    menu_ids: string[]
  }) {
    return axios.post<AccessRole>(`${BASE}/api/v1/access-control/roles`, data, { headers: authHeaders() })
  },

  deleteRole(roleId: string) {
    return axios.delete<{ message: string }>(`${BASE}/api/v1/access-control/roles/${roleId}`, { headers: authHeaders() })
  },

  getDashboardOverview(asOfDate: string) {
    return axios.get<PortfolioDashboardOverview>(`${BASE}/api/v1/fsi/risk/dashboard-overview`, {
      params: { as_of_date: asOfDate },
      headers: authHeaders(),
    })
  },

  /** 投資風險分析：組合概況 */
  getPortfolioOverview(fundId: string, asOfDate: string) {
    return axios.get<PortfolioOverviewResult>(
      `${BASE}/api/v1/fsi/investment/overview/${fundId}`,
      { params: { as_of_date: asOfDate }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：組合概況時序圖表 */
  getPortfolioOverviewTimeseries(fundId: string, start: string, end: string) {
    return axios.get<PortfolioOverviewTimeseriesResult>(
      `${BASE}/api/v1/fsi/investment/overview-timeseries/${fundId}`,
      { params: { start, end }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：基金基本信息與投資經理 */
  getBasicInfo(fundId: string, asOfDate: string) {
    return axios.get<PortfolioBasicInfo>(
      `${BASE}/api/v1/fsi/investment/basic-info/${fundId}`,
      { params: { as_of_date: asOfDate }, headers: authHeaders() },
    )
  },

  /** 風控指標 SQL 片段目錄（查看SQL） */
  getIndicatorSqlCatalog() {
    return axios.get<{ items: IndicatorSql[] }>(
      `${BASE}/api/v1/fsi/indicator-sql/`,
      { headers: authHeaders() },
    )
  },

  /** 投資風險分析：確定性風險指標 */
  getRiskIndicators(fundId: string, start: string, end: string) {
    return axios.get<RiskIndicatorsResult>(
      `${BASE}/api/v1/fsi/investment/risk-indicators/${fundId}`,
      { params: { start, end }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：風險指標時序圖表 */
  getRiskIndicatorTimeseries(fundId: string, start: string, end: string) {
    return axios.get<RiskIndicatorTimeseriesResult>(
      `${BASE}/api/v1/fsi/investment/risk-indicators-timeseries/${fundId}`,
      { params: { start, end }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：績效歸因 */
  getPerformanceAttribution(fundId: string, start: string, end: string) {
    return axios.get<PerformanceAttributionResult>(
      `${BASE}/api/v1/fsi/investment/attribution/${fundId}`,
      { params: { start, end }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：績效歸因時序圖表 */
  getPerformanceAttributionTimeseries(fundId: string, start: string, end: string) {
    return axios.get<PerformanceAttributionTimeseriesResult>(
      `${BASE}/api/v1/fsi/investment/attribution-timeseries/${fundId}`,
      { params: { start, end }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：利率與信用敏感度 */
  getRatesCredit(fundId: string, asOfDate: string) {
    return axios.get<RatesCreditResult>(
      `${BASE}/api/v1/fsi/investment/rates-credit/${fundId}`,
      { params: { as_of_date: asOfDate }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：流動性與壓力測試 */
  getLiquidityStress(
    fundId: string,
    asOfDate: string,
    options?: { redemptionPct?: number; rateShockBps?: number },
  ) {
    return axios.get<LiquidityStressResult>(
      `${BASE}/api/v1/fsi/investment/liquidity-stress/${fundId}`,
      {
        params: {
          as_of_date: asOfDate,
          redemption_pct: options?.redemptionPct ?? 20,
          rate_shock_bps: options?.rateShockBps ?? 50,
        },
        headers: authHeaders(),
      },
    )
  },

  /** 投資風險分析：風險預算與前置試算 */
  getPretradeCheck(
    fundId: string,
    asOfDate: string,
    options: {
      tradeAmount: number
      tradeSide: "BUY" | "SELL"
      assetClass: string
      durationYears: number
      issuerName: string
    },
  ) {
    return axios.get<PretradeRiskResult>(
      `${BASE}/api/v1/fsi/investment/pretrade-check/${fundId}`,
      {
        params: {
          as_of_date: asOfDate,
          trade_amount: options.tradeAmount,
          trade_side: options.tradeSide,
          asset_class: options.assetClass,
          duration_years: options.durationYears,
          issuer_name: options.issuerName,
        },
        headers: authHeaders(),
      },
    )
  },

  /** 投資風險分析：宏觀與市場動態 */
  getMacroDynamics(fundId: string, start: string, end: string) {
    return axios.get<MacroDynamicsResult>(
      `${BASE}/api/v1/fsi/investment/macro-dynamics/${fundId}`,
      { params: { start, end }, headers: authHeaders() },
    )
  },

  /** 投資風險分析：基本面、因子與行為風險 */
  getFactorBehavior(fundId: string, start: string, end: string) {
    return axios.get<FactorBehaviorResult>(
      `${BASE}/api/v1/fsi/investment/factor-behavior/${fundId}`,
      { params: { start, end }, headers: authHeaders() },
    )
  },

  /** 暴露分析 + SFC 合規狀態 */
  getExposure(fundId: string, asOfDate: string) {
    return axios.get<ExposureResult>(
      `${BASE}/api/v1/fsi/risk/exposure/${fundId}`,
      { params: { as_of_date: asOfDate }, headers: authHeaders() },
    )
  },

  /** 查詢基金在參考日期之前（含當天）的最新可用暴露數據日期 */
  getExposureLatestDate(fundId: string, asOfDate: string) {
    return axios.get<ExposureLatestDateResult>(
      `${BASE}/api/v1/fsi/risk/exposure-latest-date/${fundId}`,
      { params: { as_of_date: asOfDate }, headers: authHeaders() },
    )
  },

  /** 單方法 VaR */
  getVar(
    fundId: string,
    asOfDate: string,
    options?: { method?: string; confidence?: number; horizonDays?: number; simulations?: number },
  ) {
    return axios.get<VarResult>(`${BASE}/api/v1/fsi/risk/var/${fundId}`, {
      params: {
        as_of_date: asOfDate,
        method: options?.method ?? "historical",
        confidence: options?.confidence ?? 0.99,
        horizon_days: options?.horizonDays ?? 1,
        simulations: options?.simulations ?? 10000,
      },
      headers: authHeaders(),
    })
  },

  /** 三方法 VaR 對比 */
  getVarCompare(
    fundId: string,
    asOfDate: string,
    options?: { confidence?: number; horizonDays?: number },
  ) {
    return axios.get<VarCompareResult>(
      `${BASE}/api/v1/fsi/risk/var-compare/${fundId}`,
      {
        params: {
          as_of_date: asOfDate,
          confidence: options?.confidence ?? 0.99,
          horizon_days: options?.horizonDays ?? 1,
        },
        headers: authHeaders(),
      },
    )
  },

  /** 持倉列表 */
  getPositions(fundId: string, asOfDate: string, assetType?: string) {
    return axios.get<PositionsResponse>(
      `${BASE}/api/v1/fsi/positions/${fundId}`,
      {
        params: {
          as_of_date: asOfDate,
          ...(assetType ? { asset_type: assetType } : {}),
        },
        headers: authHeaders(),
      },
    )
  },

  // ── 風控規則配置 API ──────────────────────────────────────────
  listRiskRules(params?: {
    ruleType?: RiskRuleType
    fundId?: string
    activeOnly?: boolean
    search?: string
    skip?: number
    limit?: number
  }) {
    return axios.get<RiskRuleListResponse>(`${BASE}/api/v1/fsi/risk-rules/`, {
      params: {
        rule_type: params?.ruleType,
        fund_id: params?.fundId,
        active_only: params?.activeOnly ?? false,
        search: params?.search,
        skip: params?.skip ?? 0,
        limit: params?.limit ?? 200,
      },
      headers: authHeaders(),
    })
  },
  getRiskRuleSummary() {
    return axios.get<RiskRuleSummary>(`${BASE}/api/v1/fsi/risk-rules/summary`, { headers: authHeaders() })
  },
  createRiskRule(data: RiskRulePayload) {
    return axios.post<RiskRule>(`${BASE}/api/v1/fsi/risk-rules/`, data, { headers: authHeaders() })
  },
  updateRiskRule(ruleType: RiskRuleType, ruleId: number, data: Partial<RiskRulePayload>) {
    return axios.patch<RiskRule>(`${BASE}/api/v1/fsi/risk-rules/${ruleType}/${ruleId}`, data, { headers: authHeaders() })
  },
  deactivateRiskRule(ruleType: RiskRuleType, ruleId: number) {
    return axios.delete<RiskRule>(`${BASE}/api/v1/fsi/risk-rules/${ruleType}/${ruleId}`, { headers: authHeaders() })
  },
  listRiskRuleAttachments(ruleType: RiskRuleType, ruleId: number) {
    return axios.get<RiskRuleAttachmentListResponse>(`${BASE}/api/v1/fsi/risk-rules/${ruleType}/${ruleId}/attachments`, {
      headers: authHeaders(),
    })
  },
  uploadRiskRuleAttachment(ruleType: RiskRuleType, ruleId: number, file: File, note?: string) {
    const form = new FormData()
    form.append("file", file)
    if (note) form.append("note", note)
    return axios.post<RiskRuleAttachment>(`${BASE}/api/v1/fsi/risk-rules/${ruleType}/${ruleId}/attachments`, form, {
      headers: { ...authHeaders(), "Content-Type": "multipart/form-data" },
    })
  },
  downloadRiskRuleAttachment(attachmentId: number) {
    return axios.get<Blob>(`${BASE}/api/v1/fsi/risk-rules/attachment-files/${attachmentId}/download`, {
      responseType: "blob",
      headers: authHeaders(),
    })
  },
  deleteRiskRuleAttachment(attachmentId: number) {
    return axios.delete<{ ok: boolean; attachment_id: number }>(`${BASE}/api/v1/fsi/risk-rules/attachment-files/${attachmentId}`, {
      headers: authHeaders(),
    })
  },
  bootstrapRegulatoryRules(effectiveDate = "2024-01-01") {
    return axios.post<{ inserted: number; active_regulatory_total: number; effective_date: string }>(
      `${BASE}/api/v1/fsi/risk-rules/regulatory/bootstrap`,
      null,
      { params: { effective_date: effectiveDate }, headers: authHeaders() },
    )
  },
  getRegulatoryRuleBrief(fundId?: string, activeOnly = true) {
    return axios.get<RegulatoryRuleBriefResponse>(`${BASE}/api/v1/fsi/risk-rules/regulatory-brief`, {
      params: { fund_id: fundId, active_only: activeOnly },
      headers: authHeaders(),
    })
  },
  listRuleApplications(params?: {
    applyScope?: RuleApplyScope
    fundId?: string
    activeOnly?: boolean
    skip?: number
    limit?: number
  }) {
    return axios.get<RuleApplicationListResponse>(`${BASE}/api/v1/fsi/risk-rules/applications`, {
      params: {
        apply_scope: params?.applyScope,
        fund_id: params?.fundId,
        active_only: params?.activeOnly ?? false,
        skip: params?.skip ?? 0,
        limit: params?.limit ?? 200,
      },
      headers: authHeaders(),
    })
  },
  createRuleApplication(data: RuleApplicationPayload) {
    return axios.post<RuleApplication>(`${BASE}/api/v1/fsi/risk-rules/applications`, data, { headers: authHeaders() })
  },
  updateRuleApplication(applicationId: number, data: Partial<RuleApplicationPayload>) {
    return axios.patch<RuleApplication>(`${BASE}/api/v1/fsi/risk-rules/applications/item/${applicationId}`, data, { headers: authHeaders() })
  },
  deactivateRuleApplication(applicationId: number) {
    return axios.delete<{ application_id: number; is_active: boolean }>(`${BASE}/api/v1/fsi/risk-rules/applications/item/${applicationId}`, {
      headers: authHeaders(),
    })
  },

  chat(payload: AgentTaskRequest) {
    return axios.post<AgentChatResponse>(
      `${BASE}/api/v1/fsi/agent/chat`,
      payload,
      { headers: authHeaders() },
    )
  },

  runAgentTask(payload: AgentTaskRequest) {
    return axios.post<AgentTaskResponse>(
      `${BASE}/api/v1/fsi/agent/run`,
      payload,
      { headers: authHeaders() },
    )
  },

  getAgentTaskStatus(taskId: string) {
    return axios.get<AgentTaskStatus>(
      `${BASE}/api/v1/fsi/agent/status/${taskId}`,
      { headers: authHeaders() },
    )
  },

  // ── 定時報表 API ──────────────────────────────────────────────
  listSchedules() {
    return axios.get<Schedule[]>(`${BASE}/api/v1/fsi/schedules/`, { headers: authHeaders() })
  },
  createSchedule(data: { name: string; report_id: string; fund_id: string; hour: number; minute: number; enabled: boolean }) {
    return axios.post<Schedule>(`${BASE}/api/v1/fsi/schedules/`, data, { headers: authHeaders() })
  },
  updateSchedule(scheduleId: string, data: Partial<Schedule>) {
    return axios.patch<Schedule>(`${BASE}/api/v1/fsi/schedules/${scheduleId}`, data, { headers: authHeaders() })
  },
  deleteSchedule(scheduleId: string) {
    return axios.delete(`${BASE}/api/v1/fsi/schedules/${scheduleId}`, { headers: authHeaders() })
  },
  runScheduleNow(scheduleId: string) {
    return axios.post(`${BASE}/api/v1/fsi/schedules/${scheduleId}/run-now`, {}, { headers: authHeaders() })
  },
  getScheduleHistory(scheduleId: string) {
    return axios.get<ScheduleHistory[]>(`${BASE}/api/v1/fsi/schedules/${scheduleId}/history`, { headers: authHeaders() })
  },
  deleteScheduleHistory(runId: string) {
    return axios.delete(`${BASE}/api/v1/fsi/schedules/history/${runId}`, { headers: authHeaders() })
  },
  getScheduleFiles(scheduleId: string) {
    return axios.get<ScheduleFile[]>(`${BASE}/api/v1/fsi/schedules/${scheduleId}/files`, { headers: authHeaders() })
  },
  async downloadScheduleFile(scheduleId: string, filename: string): Promise<void> {
    const resp = await axios.get(
      `${BASE}/api/v1/fsi/schedules/${scheduleId}/download/${encodeURIComponent(filename)}`,
      { headers: authHeaders(), responseType: "blob" },
    )
    const url = URL.createObjectURL(new Blob([resp.data]))
    const a = document.createElement("a"); a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  },

  /** 查詢已生成文件（頁面刷新後恢復，無需任務 ID） */
  getReportResult(reportId: string, fundId: string, asOfDate: string) {
    return axios.get<{
      found: boolean
      output_files: string[]
      report_id: string
      fund_id: string
      as_of_date: string
    }>(
      `${BASE}/api/v1/fsi/reports/result/${reportId}`,
      { params: { fund_id: fundId, as_of_date: asOfDate }, headers: authHeaders() },
    )
  },

  /** 觸發報表生成任務 */
  generateReport(reportId: string, fundId: string, asOfDate: string) {
    return axios.post<ReportTask>(
      `${BASE}/api/v1/fsi/reports/generate`,
      { report_id: reportId, fund_id: fundId, as_of_date: asOfDate },
      { headers: authHeaders() },
    )
  },

  /** 查詢任務進度 */
  getReportTask(taskId: string) {
    return axios.get<ReportTask>(
      `${BASE}/api/v1/fsi/reports/tasks/${taskId}`,
      { headers: authHeaders() },
    )
  },

  /** 下載報表文件（axios blob → 觸發瀏覽器另存） */
  async downloadReport(reportId: string, fundId: string, filename: string): Promise<void> {
    const resp = await axios.get(
      `${BASE}/api/v1/fsi/reports/download/${reportId}/${encodeURIComponent(filename)}`,
      { params: { fund_id: fundId }, headers: authHeaders(), responseType: "blob" },
    )
    const url = URL.createObjectURL(new Blob([resp.data]))
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },

  getAgentVarSkill(
    fundId: string,
    asOfDate: string,
    options?: { confidence?: number; horizonDays?: number; simulations?: number },
  ) {
    return axios.post<AgentVarSkillResponse>(
      `${BASE}/api/v1/fsi/agent/skills/var-analysis`,
      {
        fund_id: fundId,
        as_of_date: asOfDate,
        confidence: options?.confidence ?? 0.99,
        horizon_days: options?.horizonDays ?? 1,
        simulations: options?.simulations ?? 10000,
      },
      { headers: authHeaders() },
    )
  },

  // ── Agent V2 API（SSE 流式 + tool_use） ──────────────────────────

  /** 可用 Agent 列表 */
  listAgents() {
    return axios.get<Array<{ id: string; name: string }>>(
      `${BASE}/api/v1/fsi/agent/v2/agents`,
      { headers: authHeaders() },
    )
  },

  /** 支持的模型列表（含 Provider 和默認標記） */
  listModels() {
    return axios.get<Array<{
      id: string
      label: string
      provider: "anthropic" | "openai" | "gemini" | "moonshot" | "deepseek" | "openrouter"
      default: boolean
    }>>(
      `${BASE}/api/v1/fsi/agent/v2/models`,
      { headers: authHeaders() },
    )
  },

  /** Agent V2 非流式 chat */
  chatV2(message: string, agent: string, context?: { fund_id?: string; as_of_date?: string }) {
    return axios.post<{ reply: string; agent: string; tool_calls: unknown[] }>(
      `${BASE}/api/v1/fsi/agent/v2/chat`,
      { message, agent, context },
      { headers: authHeaders() },
    )
  },

  // ── 用戶專屬 Agent 配置 API ──────────────────────────────────────

  getMyAgentConfig() {
    return axios.get<UserAgentConfig>(`${BASE}/api/v1/agent-config/me`, { headers: authHeaders() })
  },

  updateMyAgentConfig(data: UserAgentConfigUpdate) {
    return axios.put<UserAgentConfig>(`${BASE}/api/v1/agent-config/me`, data, { headers: authHeaders() })
  },

  resetMyAgentConfig() {
    return axios.delete<UserAgentConfig>(`${BASE}/api/v1/agent-config/me/reset`, { headers: authHeaders() })
  },

  refreshSkills() {
    return axios.post<{ ok: boolean; scanned: number; indexed: number; message: string }>(
      `${BASE}/api/v1/knowledge/refresh-skills`,
      {},
      { headers: authHeaders() },
    )
  },

  // ── Chat 歷史 API ────────────────────────────────────────────────

  listChatSessions() {
    return axios.get<ChatSessionRecord[]>(`${BASE}/api/v1/chat/sessions`, { headers: authHeaders() })
  },

  createChatSession(data: { title?: string; agent_id?: string; model_id?: string }) {
    return axios.post<ChatSessionRecord>(`${BASE}/api/v1/chat/sessions`, data, { headers: authHeaders() })
  },

  updateChatSession(id: string, data: { title?: string; agent_id?: string; model_id?: string }) {
    return axios.patch<ChatSessionRecord>(`${BASE}/api/v1/chat/sessions/${id}`, data, { headers: authHeaders() })
  },

  deleteChatSession(id: string) {
    return axios.delete(`${BASE}/api/v1/chat/sessions/${id}`, { headers: authHeaders() })
  },

  getChatMessages(sessionId: string) {
    return axios.get<ChatMessageRecord[]>(`${BASE}/api/v1/chat/sessions/${sessionId}/messages`, { headers: authHeaders() })
  },

  saveChatMessages(sessionId: string, messages: Array<{ role: string; content: string; tool_calls?: unknown[] }>) {
    return axios.post<ChatMessageRecord[]>(
      `${BASE}/api/v1/chat/sessions/${sessionId}/messages`,
      { messages },
      { headers: authHeaders() },
    )
  },

  // ── 用戶 API Key 管理 ──────────────────────────────────────────
  listApiKeys() {
    return axios.get<UserApiKey[]>(`${BASE}/api/v1/api-keys/`, { headers: authHeaders() })
  },

  getLocalApiConfig() {
    return axios.get<LocalApiConfig>(`${BASE}/api/v1/api-keys/local-config`, { headers: authHeaders() })
  },

  createApiKey(data: { name: string; expires_days?: number | null }) {
    return axios.post<CreatedUserApiKey>(`${BASE}/api/v1/api-keys/`, data, { headers: authHeaders() })
  },

  revokeApiKey(id: string) {
    return axios.delete<UserApiKey>(`${BASE}/api/v1/api-keys/${id}`, { headers: authHeaders() })
  },

  // ── 獨立通知接口（可供其他頁面的發送按鈕複用） ────────────────
  getNotificationChannels() {
    return axios.get<NotificationChannels>(`${BASE}/api/v1/notifications/channels`, { headers: authHeaders() })
  },

  sendNotification(
    channel: NotificationChannel,
    data: { title: string; content: string; recipient?: string },
  ) {
    return axios.post<{ channel: NotificationChannel; status: "sent"; message: string }>(
      `${BASE}/api/v1/notifications/${channel}`,
      data,
      { headers: authHeaders() },
    )
  },

  /**
   * Agent V2 SSE 流式對話（主要接口）。
   *
   * 返回原始 Response，由調用方使用 ReadableStream 處理 SSE 事件。
   * SSE 事件格式：{"type":"text"|"tool_call"|"tool_result"|"done"|"error", ...}
   *
   * 使用示例：
   *   const res = await fsiApi.streamAgentChat(messages, "risk-analyst", ctx)
   *   const reader = res.body!.getReader()
   */
  async streamAgentChat(
    messages:   Array<{ role: string; content: string }>,
    agent:      string,
    context?:   { fund_id?: string; as_of_date?: string },
    model?:     string,
    sessionId?: string,
    userId?:    string,
  ): Promise<Response> {
    const token = localStorage.getItem("access_token") ?? ""
    return fetch(`${BASE}/api/v1/fsi/agent/v2/stream`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messages,
        agent,
        context,
        model,
        session_id: sessionId,
        user_id:    userId,
      }),
    })
  },
}
