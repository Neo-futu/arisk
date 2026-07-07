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
  by_asset_type: Record<string, { mv_hkd: number; pct: number }>
  by_currency: Record<string, { mv_hkd: number; pct: number }>
  by_maturity_bucket: Record<string, { mv_hkd: number; pct: number }>
  top_issuers: Array<{ issuer: string; mv_hkd: number; pct: number }>
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

export interface Position {
  security_id: string
  security_name: string
  asset_type: string
  currency: string
  face_value: number
  market_value_hkd: number
  pct_nav: number
  maturity_date?: string
  rating?: string
  issuer?: string
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

export interface AgentChatResponse {
  reply: string
  model: string
}

export interface AgentVarSkillResponse extends VarCompareResult {
  summary: string
}

// ── API 調用 ──────────────────────────────────────────────────────

export const fsiApi = {
  /** 暴露分析 + SFC 合規狀態 */
  getExposure(fundId: string, asOfDate: string) {
    return axios.get<ExposureResult>(
      `${BASE}/api/v1/fsi/risk/exposure/${fundId}`,
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
    return axios.get<{ positions: Position[]; total_count: number }>(
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
}
