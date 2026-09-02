import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/risk-testing/")({
	beforeLoad: () => {
		throw redirect({ to: "/risk-testing/sensitivity" })
	},
})
