/** Wave 9 navigation contract. Titles are i18n keys. */

export const INVESTMENT_RISK_NAV = [
  { id: "investment-overview", titleKey: "nav.portfolioOverview", path: "/investment-risk/overview" },
  { id: "risk-exposure", titleKey: "nav.riskExposure", path: "/investment-risk/indicators#risk-exposure" },
  { id: "factor-risk", titleKey: "nav.factorRisk", path: "/investment-risk/factor-behavior#factor-risk" },
  { id: "market-risk", titleKey: "nav.marketRisk", path: "/investment-risk/macro-dynamics#market-risk" },
  { id: "rates-credit", titleKey: "nav.ratesCreditRisk", path: "/investment-risk/rates-credit" },
  { id: "liquidity-risk", titleKey: "nav.liquidityRisk", path: "/investment-risk/liquidity-stress" },
  { id: "concentration-risk", titleKey: "nav.concentrationRisk", path: "/investment-risk/rates-credit#concentration-risk" },
  { id: "counterparty-risk", titleKey: "nav.counterpartyRisk", path: "/investment-risk/rates-credit#counterparty-risk" },
  { id: "leverage-derivatives-risk", titleKey: "nav.leverageDerivativesRisk", path: "/investment-risk/indicators#leverage-derivatives-risk" },
  { id: "performance-pnl", titleKey: "nav.performancePnlAttribution", path: "/investment-risk/attribution" },
  { id: "risk-budget", titleKey: "nav.riskBudget", path: "/investment-risk/pretrade-budget#risk-budget" },
  { id: "macro-dynamics", titleKey: "nav.macroDynamics", path: "/investment-risk/macro-dynamics" },
  { id: "factor-behavior", titleKey: "nav.factorBehavior", path: "/investment-risk/factor-behavior" },
] as const

export const PORTFOLIO_OPT_NAV = [
  { id: "portfolio-construction", titleKey: "nav.portfolioConstruction", path: "/portfolio-opt#construction" },
  { id: "po-optimization", titleKey: "nav.poOptimization", path: "/portfolio-opt#optimization" },
  { id: "po-constraints", titleKey: "nav.poConstraints", path: "/portfolio-opt#constraints" },
  { id: "simulated-portfolio", titleKey: "nav.simulatedPortfolio", path: "/portfolio-opt#simulation" },
  { id: "po-comparison", titleKey: "nav.poComparison", path: "/portfolio-opt#comparison" },
  { id: "portfolio-validation", titleKey: "nav.portfolioValidation", path: "/portfolio-opt#validation" },
] as const

export const RISK_TESTING_NAV = [
  { id: "sensitivity", titleKey: "nav.sensitivityTesting", path: "/risk-testing/sensitivity" },
  { id: "stress", titleKey: "nav.stressTesting", path: "/risk-testing/stress" },
  { id: "scenario", titleKey: "nav.scenarioTesting", path: "/risk-testing/scenario" },
  { id: "reverse-stress", titleKey: "nav.reverseStressTesting", path: "/risk-testing/reverse-stress" },
  { id: "tail-risk", titleKey: "nav.tailRiskTesting", path: "/risk-testing/tail-risk" },
  { id: "krd", titleKey: "nav.krdTesting", path: "/risk-testing/krd" },
  { id: "pnl-explain", titleKey: "nav.pnlExplainTesting", path: "/risk-testing/pnl-explain" },
  { id: "historical-backtest", titleKey: "nav.historicalBacktesting", path: "/risk-testing/historical-backtest" },
  { id: "var-backtest", titleKey: "nav.varBacktesting", path: "/risk-testing/var-backtest" },
  { id: "xva", titleKey: "nav.xvaTesting", path: "/risk-testing/xva" },
] as const

export const RISK_GOVERNANCE_NAV = [
  { id: "risk-limits", titleKey: "nav.riskLimits", path: "/risk-governance#limits" },
  { id: "risk-alerts", titleKey: "nav.riskAlerts", path: "/risk-governance#alerts" },
  { id: "risk-breaches", titleKey: "nav.riskBreaches", path: "/risk-governance#breaches" },
  { id: "exception-management", titleKey: "nav.exceptionManagement", path: "/risk-governance#exceptions" },
  { id: "escalation-disposition", titleKey: "nav.escalationDisposition", path: "/risk-governance#escalation" },
  { id: "risk-policy", titleKey: "nav.riskPolicy", path: "/risk-governance#policy" },
  { id: "model-validation", titleKey: "nav.modelValidation", path: "/risk-governance#model-validation" },
  { id: "valuation-control", titleKey: "nav.valuationControl", path: "/risk-governance#valuation-control" },
  { id: "liquidity-governance", titleKey: "nav.liquidityGovernance", path: "/risk-governance#liquidity" },
  { id: "compliance", titleKey: "nav.compliance", path: "/risk-governance#compliance" },
  { id: "risk-reports", titleKey: "nav.riskReports", path: "/risk-governance#reports" },
] as const

export const WORKBENCH_FLOW = ["Parameter", "Data / Table", "Charts / Analytics", "Ask AI"] as const

export function parseNavPath(path: string): {
  to: string
  search: Record<string, string>
  hash: string
} {
  const hashIndex = path.indexOf("#")
  const hash = hashIndex >= 0 ? path.slice(hashIndex + 1) : ""
  const withoutHash = hashIndex >= 0 ? path.slice(0, hashIndex) : path
  const queryIndex = withoutHash.indexOf("?")
  const to = (queryIndex >= 0 ? withoutHash.slice(0, queryIndex) : withoutHash) || "/"
  const query = queryIndex >= 0 ? withoutHash.slice(queryIndex + 1) : ""
  const search = query ? Object.fromEntries(new URLSearchParams(query).entries()) : {}
  return { to, search, hash }
}

export function navHref(path: string): string {
  const parsed = parseNavPath(path)
  const query = new URLSearchParams(parsed.search).toString()
  return `${parsed.to}${query ? `?${query}` : ""}${parsed.hash ? `#${parsed.hash}` : ""}`
}

export function locationHref(pathname: string, searchStr: string, hash: string): string {
  const normalizedHash = hash ? (hash.startsWith("#") ? hash : `#${hash}`) : ""
  return `${pathname}${searchStr || ""}${normalizedHash}`
}

export function moduleFromPath(pathname: string): string {
  if (pathname.startsWith("/investment-risk")) return "investment-risk"
  if (pathname.startsWith("/portfolio-opt")) return "portfolio-optimization"
  if (pathname.startsWith("/risk-testing")) return "risk-testing"
  if (pathname.startsWith("/risk-governance")) return "risk-governance"
  if (pathname.startsWith("/valuation")) return "valuation"
  if (pathname.startsWith("/trading")) return "trading"
  if (pathname.startsWith("/data-management")) return "data-management"
  if (pathname.startsWith("/portfolio-cockpit")) return "portfolio-cockpit"
  if (pathname.startsWith("/indicator-explorer")) return "market-data"
  if (pathname.startsWith("/chat")) return "agent-ai"
  if (pathname.startsWith("/autorisk")) return "autorisk"
  return pathname.replace(/^\//, "") || "dashboard"
}

export function agentForModule(module: string): string {
  if (module === "portfolio-optimization") return "fund-reporter"
  if (module === "valuation") return "valuation-reviewer"
  if (module === "autorisk") return "month-end-closer"
  if (module === "investment-risk" || module === "risk-testing" || module === "risk-governance") {
    return "risk-analyst"
  }
  return "general"
}
