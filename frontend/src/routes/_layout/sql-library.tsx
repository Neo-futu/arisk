import { createFileRoute } from "@tanstack/react-router"

import { SqlLibraryPage } from "@/modules/sql-library/SqlLibraryPage"

export const Route = createFileRoute("/_layout/sql-library")({
  component: SqlLibraryPage,
  head: () => ({ meta: [{ title: "SQL 資產庫 — ARISK" }] }),
})
