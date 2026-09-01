import { createFileRoute } from "@tanstack/react-router"

import { PortfolioOptPage } from "@/modules/portfolio-opt/PortfolioOptPage"

export const Route = createFileRoute("/_layout/portfolio-opt")({
  component: PortfolioOptPage,
  head: () => ({ meta: [{ title: "組合優化 — ARISK" }] }),
})
