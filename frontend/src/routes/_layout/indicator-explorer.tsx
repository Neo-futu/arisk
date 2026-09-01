import { createFileRoute } from "@tanstack/react-router"

import { IndicatorExplorerPage } from "@/modules/indicator-explorer/IndicatorExplorerPage"

export const Route = createFileRoute("/_layout/indicator-explorer")({
  component: IndicatorExplorerPage,
  head: () => ({ meta: [{ title: "指標探索 — ARISK" }] }),
})
