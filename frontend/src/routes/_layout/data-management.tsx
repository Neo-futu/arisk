import { createFileRoute, redirect } from "@tanstack/react-router"

import { DataManagementPage } from "@/modules/data-management/DataManagementPage"

export const Route = createFileRoute("/_layout/data-management")({
  validateSearch: (search: Record<string, unknown>) => ({
    section: ["positions", "market", "trades", "portfolios"].includes(String(search.section))
      ? String(search.section) as "positions" | "market" | "trades" | "portfolios"
      : undefined,
  }),
  beforeLoad: ({ search }) => {
    if (search.section === "trades") {
      throw redirect({ to: "/trading" })
    }
    if (search.section === "market") {
      throw redirect({ to: "/indicator-explorer", search: { tab: "market" } })
    }
  },
  component: DataManagementRoute,
  head: () => ({ meta: [{ title: "數據管理中心 — ARISK" }] }),
})

function DataManagementRoute() {
  const { section } = Route.useSearch()
  return <DataManagementPage initialSection={section === "trades" ? "positions" : section} hideMarketTab />
}
