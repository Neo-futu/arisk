import { createFileRoute } from "@tanstack/react-router"

import { MacroDynamicsRuntimePage } from "@/modules/investment-risk/runtimePages"

export const Route = createFileRoute("/_layout/investment-risk/macro-dynamics")({
  component: MacroDynamicsPage,
  head: () => ({ meta: [{ title: "宏觀與市場動態風險 — 投資風險模塊 — ARISK" }] }),
})

function MacroDynamicsPage() {
  return <MacroDynamicsRuntimePage />
}
