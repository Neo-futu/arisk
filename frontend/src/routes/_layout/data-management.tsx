import { createFileRoute } from "@tanstack/react-router"

import { DataManagementPage } from "@/modules/data-management/DataManagementPage"

export const Route = createFileRoute("/_layout/data-management")({
  component: DataManagementPage,
  head: () => ({ meta: [{ title: "數據管理中心 — ARISK" }] }),
})