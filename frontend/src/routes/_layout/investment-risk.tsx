import { createFileRoute, Outlet } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/investment-risk")({
  component: RouteComponent,
})

function RouteComponent() {
  return <Outlet />
}
