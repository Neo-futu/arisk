import { createFileRoute } from "@tanstack/react-router"

import { InvestmentRiskModuleHome } from "@/modules/investment-risk/InvestmentRiskModuleHome"

export const Route = createFileRoute("/_layout/investment-risk/")({
  component: InvestmentRiskIndexPage,
  head: () => ({ meta: [{ title: "投資風險模塊 — ARISK" }] }),
})

function InvestmentRiskIndexPage() {
  return <InvestmentRiskModuleHome />
}