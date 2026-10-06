import { useEffect } from "react"
import { useRouterState } from "@tanstack/react-router"

/** 僅用於切頁籤/路由定位、不應滾動到頁中錨點的 hash。 */
const TAB_ENTRY_HASHES = new Set([
  "risk-exposure",
  "leverage-derivatives-risk",
  "concentration-risk",
  "counterparty-risk",
  "factor-risk",
  "market-risk",
  "risk-budget",
])

function scrollDocumentToTop() {
  window.scrollTo({ top: 0, left: 0, behavior: "auto" })
  document.documentElement.scrollTop = 0
  document.body.scrollTop = 0
  const inset = document.querySelector<HTMLElement>('[data-slot="sidebar-inset"]')
  if (inset) inset.scrollTop = 0
  const main = document.querySelector<HTMLElement>("main.flex-1")
  if (main) main.scrollTop = 0
}

/** Native hash targets after React paint. */
export function useHashScroll() {
  const hash = useRouterState({ select: (state) => state.location.hash })
  useEffect(() => {
    const id = hash.replace(/^#/, "")
    if (!id) return

    // 菜單入口 hash：固定回頂，避免 scrollIntoView 把視口滾到標題下方
    if (TAB_ENTRY_HASHES.has(id)) {
      const timers = [0, 50, 150, 300].map((ms) =>
        window.setTimeout(scrollDocumentToTop, ms),
      )
      return () => timers.forEach((timer) => window.clearTimeout(timer))
    }

    const timer = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
    }, 50)
    return () => window.clearTimeout(timer)
  }, [hash])
}
