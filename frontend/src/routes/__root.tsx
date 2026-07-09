import { createRootRoute, HeadContent, Outlet } from "@tanstack/react-router"
import ErrorComponent from "@/components/Common/ErrorComponent"
import NotFound from "@/components/Common/NotFound"
import { ErrorBoundary } from "@/components/ErrorBoundary"

export const Route = createRootRoute({
  component: () => (
    <>
      <HeadContent />
      <ErrorBoundary module="root">
        <Outlet />
      </ErrorBoundary>
    </>
  ),
  notFoundComponent: () => <NotFound />,
  errorComponent: () => <ErrorComponent />,
})
