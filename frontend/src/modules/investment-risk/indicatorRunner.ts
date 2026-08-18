/**
 * Shared indicator runner — the endpoint dispatch + summary logic used by both the
 * validation page and the risk-indicators catalog panel. Extracted so the full
 * PROCESSING_INDICATORS catalog can be executed from multiple pages without
 * duplicating the fsiApi wiring.
 */
import { fsiApi } from "@/fsiClient"
import type { EndpointKey } from "@/modules/investment-risk/processingIndicatorCatalog"

export type IndicatorResult = {
  running: boolean
  ok: boolean
  latencyMs: number
  outputPreview: string
  rawOutput?: unknown
  message?: string
}

export interface RunnerParams {
  asOfDate: string
  startDate: string
  endDate: string
  redemptionPct: number
  rateShockBps: number
  tradeAmount: number
  tradeSide: "BUY" | "SELL"
  assetClass: string
  durationYears: number
  issuerName: string
  confidence: number
  horizonDays: number
}

export const DEFAULT_RUNNER_PARAMS: Omit<RunnerParams, "asOfDate" | "startDate" | "endDate"> = {
  redemptionPct: 20,
  rateShockBps: 50,
  tradeAmount: 10_000_000,
  tradeSide: "BUY",
  assetClass: "BOND_CORP",
  durationYears: 2,
  issuerName: "UNKNOWN_ISSUER",
  confidence: 0.99,
  horizonDays: 1,
}

export async function callEndpoint(
  endpoint: EndpointKey,
  fundId: string,
  params: RunnerParams,
): Promise<unknown> {
  switch (endpoint) {
    case "overview":
      return (await fsiApi.getPortfolioOverview(fundId, params.asOfDate)).data
    case "risk-indicators":
      return (await fsiApi.getRiskIndicators(fundId, params.startDate, params.endDate)).data
    case "attribution":
      return (await fsiApi.getPerformanceAttribution(fundId, params.startDate, params.endDate)).data
    case "rates-credit":
      return (await fsiApi.getRatesCredit(fundId, params.asOfDate)).data
    case "liquidity-stress":
      return (await fsiApi.getLiquidityStress(fundId, params.asOfDate, {
        redemptionPct: params.redemptionPct,
        rateShockBps: params.rateShockBps,
      })).data
    case "pretrade-check":
      return (await fsiApi.getPretradeCheck(fundId, params.asOfDate, {
        tradeAmount: params.tradeAmount,
        tradeSide: params.tradeSide,
        assetClass: params.assetClass,
        durationYears: params.durationYears,
        issuerName: params.issuerName,
      })).data
    case "macro-dynamics":
      return (await fsiApi.getMacroDynamics(fundId, params.startDate, params.endDate)).data
    case "factor-behavior":
      return (await fsiApi.getFactorBehavior(fundId, params.startDate, params.endDate)).data
    case "exposure":
      return (await fsiApi.getExposure(fundId, params.asOfDate)).data
    case "var-compare":
      return (await fsiApi.getVarCompare(fundId, params.asOfDate, {
        confidence: params.confidence,
        horizonDays: params.horizonDays,
      })).data
    default:
      return null
  }
}

export function summarize(endpoint: EndpointKey, payload: any): string {
  if (!payload) return "空輸出"
  switch (endpoint) {
    case "overview":
      return `NAV: ${Number(payload.portfolio?.net_asset ?? 0).toLocaleString("zh-HK", { maximumFractionDigits: 0 })}`
    case "risk-indicators":
      return `Vol: ${Number(payload.annualized_volatility_pct ?? 0).toFixed(3)}%`
    case "attribution":
      return `Active: ${Number(payload.summary?.active_return_pct ?? 0).toFixed(3)}%`
    case "rates-credit":
      return `DV01: ${Number(payload.portfolio_dv01 ?? 0).toLocaleString("zh-HK", { maximumFractionDigits: 0 })}`
    case "liquidity-stress":
      return `LCR: ${Number(payload.stress_summary?.liquidity_coverage_ratio ?? 0).toFixed(2)}`
    case "pretrade-check":
      return `Decision: ${String(payload.decision ?? "UNKNOWN")}`
    case "macro-dynamics":
      return `Regime: ${String(payload.fund_regime?.regime ?? "UNKNOWN")}`
    case "factor-behavior":
      return `HHI: ${Number(payload.sector_concentration?.hhi ?? 0).toFixed(2)}`
    case "exposure":
      return `D/W: ${Number(payload.daily_liquid_pct ?? 0).toFixed(2)}% / ${Number(payload.weekly_liquid_pct ?? 0).toFixed(2)}%`
    case "var-compare":
      return `Max VaR: ${Number(payload.max_var_pct_nav ?? 0).toFixed(4)}%`
    default:
      return "已完成"
  }
}

export function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
