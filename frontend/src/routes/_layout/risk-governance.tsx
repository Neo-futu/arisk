import { createFileRoute } from "@tanstack/react-router"

import { RiskGovernancePage } from "@/modules/risk-governance/RiskGovernancePage"

export const Route = createFileRoute("/_layout/risk-governance")({
  component: RiskGovernancePage,
  head: () => ({ meta: [{ title: "風險治理 — ARISK" }] }),
})
