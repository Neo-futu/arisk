import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { useRouterState } from "@tanstack/react-router"

import { moduleFromPath } from "@/platform/nav"

export type PlatformPageContext = {
  portfolio?: string
  date?: string
  module: string
  result?: string
  chart?: string
  riskMetrics?: Record<string, unknown>
}

const EMPTY: PlatformPageContext = { module: "dashboard" }

type Store = {
  context: PlatformPageContext
  patch: (partial: Partial<PlatformPageContext>) => void
}

const PageContext = createContext<Store | null>(null)

export function PageContextProvider({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const [context, setContext] = useState<PlatformPageContext>({
    ...EMPTY,
    module: moduleFromPath(pathname),
  })

  useEffect(() => {
    setContext((previous) => ({
      ...previous,
      module: moduleFromPath(pathname),
      result: undefined,
      chart: undefined,
      riskMetrics: undefined,
    }))
  }, [pathname])

  const patch = useCallback((partial: Partial<PlatformPageContext>) => {
    setContext((previous) => {
      const next = { ...previous, ...partial }
      if (
        next.portfolio === previous.portfolio
        && next.date === previous.date
        && next.module === previous.module
        && next.result === previous.result
        && next.chart === previous.chart
        && next.riskMetrics === previous.riskMetrics
      ) {
        return previous
      }
      return next
    })
  }, [])

  const value = useMemo(() => ({ context, patch }), [context, patch])
  return <PageContext.Provider value={value}>{children}</PageContext.Provider>
}

export function usePageContext() {
  const store = useContext(PageContext)
  if (!store) {
    throw new Error("usePageContext must be used within PageContextProvider")
  }
  return store
}

export function useBindPageContext(partial: Partial<PlatformPageContext>) {
  const { patch } = usePageContext()
  const serialized = JSON.stringify(partial)
  useEffect(() => {
    patch(JSON.parse(serialized) as Partial<PlatformPageContext>)
  }, [patch, serialized])
}

export function formatPageContext(context: PlatformPageContext): string {
  return JSON.stringify(
    {
      Portfolio: context.portfolio ?? null,
      Date: context.date ?? null,
      "Current Module": context.module,
      "Current Result": context.result ?? null,
      "Current Chart": context.chart ?? null,
      "Risk Metrics": context.riskMetrics ?? null,
    },
    null,
    2,
  )
}
