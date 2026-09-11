import { createFileRoute } from "@tanstack/react-router"
import { RiskTestingPage } from "@/modules/risk-testing/RiskTestingPage"

export const Route = createFileRoute("/_layout/risk-testing/pnl-explain")({ component: () => <RiskTestingPage analytic="PNL_EXPLAIN" /> })
