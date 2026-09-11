import { createFileRoute } from '@tanstack/react-router'
import { RiskTestingPage } from '@/modules/risk-testing/RiskTestingPage'

function HistoricalBacktestRoute() {
  return <RiskTestingPage analytic="HISTORICAL_BACKTEST" />
}

export const Route = createFileRoute("/_layout/risk-testing/historical-backtest")({
  component: HistoricalBacktestRoute,
})

