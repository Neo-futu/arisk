import { createFileRoute } from "@tanstack/react-router"

import { PretradeBudgetRuntimePage } from "@/modules/investment-risk/runtimePages"

export const Route = createFileRoute("/_layout/investment-risk/pretrade-budget")({
  component: PretradeBudgetPage,
  head: () => ({ meta: [{ title: "風險預算與前置試算 — 投資風險模塊 — ARISK" }] }),
})

function PretradeBudgetPage() {
  return <PretradeBudgetRuntimePage />
}
