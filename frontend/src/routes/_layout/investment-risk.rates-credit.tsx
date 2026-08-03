import { createFileRoute } from "@tanstack/react-router"

import { RatesCreditRuntimePage } from "@/modules/investment-risk/runtimePages"

export const Route = createFileRoute("/_layout/investment-risk/rates-credit")({
  component: RatesCreditPage,
  head: () => ({ meta: [{ title: "利率與信用風險敏感度 — 投資風險模塊 — ARISK" }] }),
})

function RatesCreditPage() {
  return <RatesCreditRuntimePage />
}
