export type InvestmentRiskTopic = {
  id: "rates-credit" | "liquidity-stress" | "pretrade-budget" | "macro-dynamics" | "factor-behavior"
  title: string
  subtitle: string
  summary: string
  capabilities: string[]
  processingRoutes: string[]
  storageTables: string[]
  agentIntegration: string[]
}

export const INVESTMENT_RISK_TOPICS: InvestmentRiskTopic[] = [
  {
    id: "rates-credit",
    title: "利率與信用風險敏感度",
    subtitle: "Rates & Credit Sensitivities",
    summary:
      "量化組合對關鍵期限利率曲線與信用利差的敏感度，並穿透到底層發行人集中度與信用遷移風險。",
    capabilities: [
      "關鍵期限久期 KRD：1M/3M/6M/1Y 期限桶暴露",
      "CS01 / Spread DV01：信用利差每 1bps 對 NAV 的影響",
      "Issuer 集中度穿透 + HHI 指標監控",
      "評級下調遷移情景的敞口預警",
    ],
    processingRoutes: [
      "/api/v1/inv-risk/krd",
      "/api/v1/inv-risk/cs01",
      "/api/v1/inv-risk/issuer-concentration",
    ],
    storageTables: [
      "fsi.portfolio_sensitivities",
      "fsi.issuer_concentration_snapshots",
    ],
    agentIntegration: [
      "InvestmentRisk Subagent 可用自然語言請求期限敏感度分析",
      "MCP 工具可拉取歷史敏感度快照並比較漂移",
    ],
  },
  {
    id: "liquidity-stress",
    title: "流動性風險與壓力測試",
    subtitle: "Liquidity & Stress Testing",
    summary:
      "建立 TTL 與 L1-L4 流動性分層，並支持歷史、假設與反向壓力測試以評估極端情況下的淨值與規則紅線風險。",
    capabilities: [
      "TTL 變現天數：基於 ADV 與 bid-ask spread",
      "歷史情景壓測：2008 / 2020 等極端市況",
      "贖回衝擊壓測：20%-30% 大額贖回對 WAM/WAL 與覆蓋率影響",
      "反向壓測：倒推出觸發監管紅線所需最小衝擊",
    ],
    processingRoutes: [
      "/api/v1/inv-risk/ttl",
      "/api/v1/inv-risk/stress-test",
      "/api/v1/inv-risk/reverse-stress",
    ],
    storageTables: [
      "fsi.stress_test_results",
      "fsi.liquidity_ladder_snapshots",
    ],
    agentIntegration: [
      "支持自然語言生成多情景壓測任務",
      "輸出可追溯的結構化壓測報告與告警結果",
    ],
  },
  {
    id: "pretrade-budget",
    title: "風險預算與前置試算",
    subtitle: "Risk Budgeting & Pre-trade Analysis",
    summary:
      "在交易前評估新訂單對組合整體風險暴露的邊際影響，幫助 PM 與風控團隊做配額與越權防線管理。",
    capabilities: [
      "MCTR：單一資產/策略對 VaR 或波動率的邊際風險貢獻",
      "Pre-trade 檢查：模擬訂單對 WAM/WAL/集中度/Tracking Error 的影響",
      "風險預算分配與剩餘可用風險空間檢查",
      "超限前置攔截與建議調倉方案",
    ],
    processingRoutes: [
      "/api/v1/inv-risk/mctr",
      "/api/v1/inv-risk/pretrade-check",
      "/api/v1/inv-risk/risk-budget",
    ],
    storageTables: [
      "fsi.pretrade_checks",
      "fsi.risk_budget_snapshots",
    ],
    agentIntegration: [
      "Agent 可把自然語言交易意圖轉為風險試算請求",
      "與審批流程串接，支持人工覆核與留痕",
    ],
  },
  {
    id: "macro-dynamics",
    title: "宏觀與市場動態風險",
    subtitle: "Macro & Market Dynamics Risk",
    summary:
      "跟蹤宏觀數據、隱含波動率與跨資產相關性矩陣，識別 Regime Shift 與跨市場傳染路徑。",
    capabilities: [
      "宏觀監控矩陣：PMI、CPI/PPI、非農、政策利率預期",
      "隱含波動率與宏觀變量聯動分析",
      "跨資產關聯矩陣監控與關聯性破裂檢測",
      "傳染風險路徑識別（利率、美元、VIX、信用利差）",
    ],
    processingRoutes: [
      "/api/v1/inv-risk/macro-dashboard",
      "/api/v1/inv-risk/correlation-regime",
      "/api/v1/inv-risk/contagion-path",
    ],
    storageTables: [
      "fsi.macro_regime_snapshots",
      "fsi.cross_asset_correlation",
    ],
    agentIntegration: [
      "Subagent 可按宏觀假設批量生成風險敞口對比",
      "可直接輸出高管摘要與技術明細雙版本報告",
    ],
  },
  {
    id: "factor-behavior",
    title: "基本面、因子與行為風險",
    subtitle: "Fundamental, Factor & Behavioral Risk",
    summary:
      "整合基本面健康度、風格因子暴露與交易擁擠度，監測估值陷阱、風格漂移和踩踏風險。",
    capabilities: [
      "固收/權益基本面健康度追蹤與惡化預警",
      "Barra 類多因子暴露（Size/Value/Momentum/Quality/LowVol）",
      "風格漂移監控與非預期因子偏離提示",
      "交易擁擠度評分與踩踏風險預警",
    ],
    processingRoutes: [
      "/api/v1/inv-risk/fundamental-health",
      "/api/v1/inv-risk/factor-exposure",
      "/api/v1/inv-risk/crowding-score",
    ],
    storageTables: [
      "fsi.factor_exposure_snapshots",
      "fsi.crowding_signals",
    ],
    agentIntegration: [
      "Agent 自動整合微觀結構與因子數據給出風險解釋",
      "支持對策略踩踏風險生成前置預警工單",
    ],
  },
]

export function getInvestmentRiskTopic(id: InvestmentRiskTopic["id"]) {
  return INVESTMENT_RISK_TOPICS.find((topic) => topic.id === id)
}
