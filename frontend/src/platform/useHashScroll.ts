import { useEffect } from "react"
import { useRouterState } from "@tanstack/react-router"

/** Native hash targets after React paint. */
export function useHashScroll() {
  const hash = useRouterState({ select: (state) => state.location.hash })
  useEffect(() => {
    const id = hash.replace(/^#/, "")
    if (!id) return
    const timer = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
    }, 50)
    return () => window.clearTimeout(timer)
  }, [hash])
}
