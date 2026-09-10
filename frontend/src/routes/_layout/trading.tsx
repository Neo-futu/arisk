import { createFileRoute } from "@tanstack/react-router"

import { TradingPage } from "@/modules/trading/TradingPage"

export const Route = createFileRoute("/_layout/trading")({
  component: TradingPage,
  head: () => ({ meta: [{ title: "交易管理 — ARISK" }] }),
})
