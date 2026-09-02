import { createFileRoute } from "@tanstack/react-router"
import { RiskTestingPage } from "@/modules/risk-testing/RiskTestingPage"

export const Route = createFileRoute("/_layout/risk-testing/scenario")({ component: () => <RiskTestingPage analytic="SCENARIO" /> })
