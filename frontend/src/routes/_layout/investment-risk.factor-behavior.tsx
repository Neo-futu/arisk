import { createFileRoute } from "@tanstack/react-router"

import { FactorBehaviorRuntimePage } from "@/modules/investment-risk/runtimePages"

export const Route = createFileRoute("/_layout/investment-risk/factor-behavior")({
  component: FactorBehaviorPage,
  head: () => ({ meta: [{ title: "基本面、因子與行為風險 — 投資風險模塊 — ARISK" }] }),
})

function FactorBehaviorPage() {
  return <FactorBehaviorRuntimePage />
}
