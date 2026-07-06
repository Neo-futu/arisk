import type { AgentVarSkillResponse, DirectVarCompareResponse, VarRequest } from '../types/var'

const API_BASE = import.meta.env.VITE_ENTRY_API_BASE || 'http://127.0.0.1:8000'

async function parseOrThrow<T>(resp: Response): Promise<T> {
  const text = await resp.text()
  const payload = text ? JSON.parse(text) : {}
  if (!resp.ok) {
    const detail = payload?.detail ? JSON.stringify(payload.detail) : text
    throw new Error(`HTTP ${resp.status}: ${detail}`)
  }
  return payload as T
}

export async function fetchDirectVarCompare(req: VarRequest): Promise<DirectVarCompareResponse> {
  const params = new URLSearchParams({
    as_of_date: req.as_of_date,
    confidence: String(req.confidence),
    horizon_days: String(req.horizon_days),
    simulations: String(req.simulations),
  })
  const url = `${API_BASE}/query/risk/var-compare/${encodeURIComponent(req.fund_id)}?${params.toString()}`
  const resp = await fetch(url)
  return parseOrThrow<DirectVarCompareResponse>(resp)
}

export async function fetchAgentVarSkill(req: VarRequest): Promise<AgentVarSkillResponse> {
  const url = `${API_BASE}/agent/skills/var-analysis`
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  return parseOrThrow<AgentVarSkillResponse>(resp)
}
