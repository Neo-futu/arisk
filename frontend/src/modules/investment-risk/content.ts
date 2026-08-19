export type InvestmentRiskTopic = {
  id: "rates-credit" | "liquidity-stress" | "pretrade-budget" | "macro-dynamics" | "factor-behavior"
  /** i18n key resolving to the topic title */
  titleKey: string
  /** English subtitle, kept literal */
  subtitle: string
  /** i18n key resolving to the topic summary */
  summaryKey: string
  /** i18n key resolving to a returnObjects string[] of capabilities */
  capabilitiesKey: string
  processingRoutes: string[]
  storageTables: string[]
  /** i18n key resolving to a returnObjects string[] of agent integration notes */
  agentIntegrationKey: string
}

export const INVESTMENT_RISK_TOPICS: InvestmentRiskTopic[] = [
  {
    id: "rates-credit",
    titleKey: "investmentRisk.module.topics.rates-credit.title",
    subtitle: "Rates & Credit Sensitivities",
    summaryKey: "investmentRisk.module.topics.rates-credit.summary",
    capabilitiesKey: "investmentRisk.module.topics.rates-credit.capabilities",
    processingRoutes: [
      "/api/v1/inv-risk/krd",
      "/api/v1/inv-risk/cs01",
      "/api/v1/inv-risk/issuer-concentration",
    ],
    storageTables: [
      "fsi.portfolio_sensitivities",
      "fsi.issuer_concentration_snapshots",
    ],
    agentIntegrationKey: "investmentRisk.module.topics.rates-credit.agentIntegration",
  },
  {
    id: "liquidity-stress",
    titleKey: "investmentRisk.module.topics.liquidity-stress.title",
    subtitle: "Liquidity & Stress Testing",
    summaryKey: "investmentRisk.module.topics.liquidity-stress.summary",
    capabilitiesKey: "investmentRisk.module.topics.liquidity-stress.capabilities",
    processingRoutes: [
      "/api/v1/inv-risk/ttl",
      "/api/v1/inv-risk/stress-test",
      "/api/v1/inv-risk/reverse-stress",
    ],
    storageTables: [
      "fsi.stress_test_results",
      "fsi.liquidity_ladder_snapshots",
    ],
    agentIntegrationKey: "investmentRisk.module.topics.liquidity-stress.agentIntegration",
  },
  {
    id: "pretrade-budget",
    titleKey: "investmentRisk.module.topics.pretrade-budget.title",
    subtitle: "Risk Budgeting & Pre-trade Analysis",
    summaryKey: "investmentRisk.module.topics.pretrade-budget.summary",
    capabilitiesKey: "investmentRisk.module.topics.pretrade-budget.capabilities",
    processingRoutes: [
      "/api/v1/inv-risk/mctr",
      "/api/v1/inv-risk/pretrade-check",
      "/api/v1/inv-risk/risk-budget",
    ],
    storageTables: [
      "fsi.pretrade_checks",
      "fsi.risk_budget_snapshots",
    ],
    agentIntegrationKey: "investmentRisk.module.topics.pretrade-budget.agentIntegration",
  },
  {
    id: "macro-dynamics",
    titleKey: "investmentRisk.module.topics.macro-dynamics.title",
    subtitle: "Macro & Market Dynamics Risk",
    summaryKey: "investmentRisk.module.topics.macro-dynamics.summary",
    capabilitiesKey: "investmentRisk.module.topics.macro-dynamics.capabilities",
    processingRoutes: [
      "/api/v1/inv-risk/macro-dashboard",
      "/api/v1/inv-risk/correlation-regime",
      "/api/v1/inv-risk/contagion-path",
    ],
    storageTables: [
      "fsi.macro_regime_snapshots",
      "fsi.cross_asset_correlation",
    ],
    agentIntegrationKey: "investmentRisk.module.topics.macro-dynamics.agentIntegration",
  },
  {
    id: "factor-behavior",
    titleKey: "investmentRisk.module.topics.factor-behavior.title",
    subtitle: "Fundamental, Factor & Behavioral Risk",
    summaryKey: "investmentRisk.module.topics.factor-behavior.summary",
    capabilitiesKey: "investmentRisk.module.topics.factor-behavior.capabilities",
    processingRoutes: [
      "/api/v1/inv-risk/fundamental-health",
      "/api/v1/inv-risk/factor-exposure",
      "/api/v1/inv-risk/crowding-score",
    ],
    storageTables: [
      "fsi.factor_exposure_snapshots",
      "fsi.crowding_signals",
    ],
    agentIntegrationKey: "investmentRisk.module.topics.factor-behavior.agentIntegration",
  },
]

export function getInvestmentRiskTopic(id: InvestmentRiskTopic["id"]) {
  return INVESTMENT_RISK_TOPICS.find((topic) => topic.id === id)
}
