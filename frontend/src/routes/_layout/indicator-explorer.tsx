import { createFileRoute } from "@tanstack/react-router"

import { MarketDataIndicatorsPage } from "@/modules/indicator-explorer/MarketDataIndicatorsPage"

export const Route = createFileRoute("/_layout/indicator-explorer")({
  validateSearch: (search: Record<string, unknown>) => ({
    tab: search.tab === "indicators" || search.tab === "market"
      ? (String(search.tab) as "market" | "indicators")
      : undefined,
  }),
  component: IndicatorExplorerRoute,
  head: () => ({ meta: [{ title: "市场数据与指标 — ARISK" }] }),
})

function IndicatorExplorerRoute() {
  const { tab } = Route.useSearch()
  return <MarketDataIndicatorsPage tab={tab === "indicators" ? "indicators" : "market"} />
}
