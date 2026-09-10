import { createFileRoute } from "@tanstack/react-router"

import { HomePage } from "@/modules/home/HomePage"

export const Route = createFileRoute("/_layout/")({
  component: HomePage,
  head: () => ({
    meta: [{ title: "工作台 — ARISK" }],
  }),
})
