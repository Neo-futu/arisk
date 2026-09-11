import { createFileRoute, Outlet } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/risk-testing")({ component: () => <Outlet /> })
