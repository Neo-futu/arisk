import { createFileRoute } from "@tanstack/react-router"

import { FactorRiskRuntimePage } from "@/modules/investment-risk/runtimePages"

export const Route = createFileRoute("/_layout/investment-risk/factor-risk")({
  component: FactorRiskPage,
  head: () => ({ meta: [{ title: "因子風險 — 投資風險模塊 — ARISK" }] }),
})

function FactorRiskPage() {
  return <FactorRiskRuntimePage />
}
