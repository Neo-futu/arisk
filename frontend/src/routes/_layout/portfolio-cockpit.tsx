import { createFileRoute } from "@tanstack/react-router"

import { PortfolioCockpitPage } from "@/modules/portfolio-cockpit/PortfolioCockpitPage"

export const Route = createFileRoute("/_layout/portfolio-cockpit")({
  component: PortfolioCockpitPage,
  head: () => ({ meta: [{ title: "組合駕駛艙 — ARISK" }] }),
})
