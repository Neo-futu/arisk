import { createFileRoute } from "@tanstack/react-router"

import { ValuationPnlPage } from "@/modules/valuation-pnl/ValuationPnlPage"

export const Route = createFileRoute("/_layout/valuation")({
  component: ValuationPnlPage,
  head: () => ({ meta: [{ title: "組合估值與損益 — ARISK" }] }),
})
