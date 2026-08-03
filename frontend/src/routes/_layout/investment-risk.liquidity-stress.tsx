import { createFileRoute } from "@tanstack/react-router"

import { LiquidityStressRuntimePage } from "@/modules/investment-risk/runtimePages"

export const Route = createFileRoute("/_layout/investment-risk/liquidity-stress")({
  component: LiquidityStressPage,
  head: () => ({ meta: [{ title: "流動性風險與壓力測試 — 投資風險模塊 — ARISK" }] }),
})

function LiquidityStressPage() {
  return <LiquidityStressRuntimePage />
}
