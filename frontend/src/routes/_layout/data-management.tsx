import { createFileRoute } from "@tanstack/react-router"

import { DataManagementPage } from "@/modules/data-management/DataManagementPage"

export const Route = createFileRoute("/_layout/data-management")({
  validateSearch: (search: Record<string, unknown>) => ({
    section: ["positions", "market", "trades", "portfolios"].includes(String(search.section))
      ? String(search.section) as "positions" | "market" | "trades" | "portfolios"
      : undefined,
  }),
  component: DataManagementRoute,
  head: () => ({ meta: [{ title: "數據管理中心 — ARISK" }] }),
})

function DataManagementRoute() {
  const { section } = Route.useSearch()
  return <DataManagementPage initialSection={section} />
}