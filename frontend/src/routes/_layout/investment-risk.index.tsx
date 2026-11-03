import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/investment-risk/")({
  beforeLoad: () => {
    throw redirect({ to: "/investment-risk/overview" })
  },
})
