export type VarMethodResult = {
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

export type DirectVarCompareResponse = {
  fund_id: string
  as_of_date: string
  confidence: number
  horizon_days: number
  max_var_pct_nav: number
  results: VarMethodResult[]
}

export type AgentVarSkillResponse = DirectVarCompareResponse & {
  summary: string
}

export type VarRequest = {
  fund_id: string
  as_of_date: string
  confidence: number
  horizon_days: number
  simulations: number
}
