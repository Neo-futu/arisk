import {
  BarChart3,
  CalendarClock,
  ChevronDown,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  Home,
  MessageSquare,
  PieChart,
  Scale,
  Settings,
  Sparkles,
} from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { fsiApi } from "@/fsiClient"
import {
  INVESTMENT_RISK_NAV,
  PORTFOLIO_OPT_NAV,
  RISK_GOVERNANCE_NAV,
  RISK_TESTING_NAV,
  locationHref,
  navHref,
  parseNavPath,
} from "@/platform/nav"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { User } from "./User"

type NavItem = {
  id: string
  icon: React.ComponentType<{ className?: string }>
  title: string
  path: string
  permissionPaths?: string[]
  landing?: boolean
  children?: Array<{
    id: string
    title: string
    path?: string
    permissionPath?: string
    disabled?: boolean
  }>
}

const getFsiItems = (t: (key: string) => string): NavItem[] => [
  { id: "dashboard", icon: Home, title: t("nav.dashboard"), path: "/" },
  { id: "portfolio-cockpit", icon: Gauge, title: t("nav.portfolioCockpit"), path: "/portfolio-cockpit" },
  {
    id: "investment-risk",
    icon: BarChart3,
    title: t("nav.investmentRisk"),
    path: "/investment-risk/overview",
    children: INVESTMENT_RISK_NAV.map((item) => ({
      id: item.id,
      title: t(item.titleKey),
      path: item.path,
    })),
  },
  {
    id: "portfolio-optimization",
    icon: PieChart,
    title: t("nav.portfolioOptRiskBudget"),
    path: "/portfolio-opt",
    permissionPaths: ["/portfolio-opt", "/investment-risk"],
    children: PORTFOLIO_OPT_NAV.map((item) => ({
      id: item.id,
      title: t(item.titleKey),
      path: item.path,
    })),
  },
  {
    id: "risk-testing",
    icon: FlaskConical,
    title: t("nav.riskTesting"),
    path: "/risk-testing",
    children: RISK_TESTING_NAV.map((item) => ({
      id: item.id,
      title: t(item.titleKey),
      path: item.path,
    })),
  },
  {
    id: "data-management",
    icon: Database,
    title: t("nav.dataManagement"),
    path: "/data-management",
    permissionPaths: [
      "/data-management",
      "/indicator-explorer",
      "/sql-library",
      "/valuation",
      "/trading",
    ],
    children: [
      { id: "portfolio-data", title: t("nav.portfolioData"), path: "/data-management", permissionPath: "/data-management" },
      { id: "market-data-indicators", title: t("nav.marketDataIndicators"), path: "/indicator-explorer", permissionPath: "/indicator-explorer" },
      { id: "sql-library", title: t("nav.sqlLibrary"), path: "/sql-library", permissionPath: "/sql-library" },
      { id: "valuation", title: t("nav.valuationPnl"), path: "/valuation", permissionPath: "/valuation" },
      { id: "trading", title: t("nav.tradingManagement"), path: "/trading", permissionPath: "/trading" },
    ],
  },
  {
    id: "risk-governance",
    icon: Scale,
    title: t("nav.riskGovernance"),
    path: "/risk-governance",
    permissionPaths: ["/risk-governance", "/risk-rules", "/compliance"],
    children: RISK_GOVERNANCE_NAV.map((item) => ({
      id: item.id,
      title: t(item.titleKey),
      path: item.path,
    })),
  },
  { id: "reports", icon: FileText, title: t("nav.reports"), path: "/reports" },
  { id: "schedules", icon: CalendarClock, title: t("nav.schedules"), path: "/schedules" },
  { id: "autorisk", icon: Sparkles, title: t("nav.autorisk"), path: "/autorisk" },
  {
    id: "agent-ai",
    icon: MessageSquare,
    title: t("nav.agentAi"),
    path: "/chat",
    permissionPaths: ["/chat", "/expert"],
    children: [
      { id: "agent-chat", title: t("nav.chat"), path: "/chat", permissionPath: "/chat" },
      { id: "expert", title: t("nav.expert"), path: "/expert", permissionPath: "/expert" },
    ],
  },
]

const getAdminItems = (t: (key: string) => string): NavItem[] => [
  {
    id: "system-management",
    icon: Settings,
    title: t("nav.systemManagement"),
    path: "/system-management",
    landing: false,
    permissionPaths: ["/admin", "/system-config", "/api-keys", "/notifications", "/settings"],
    children: [
      { id: "admin", title: t("nav.userManagement"), path: "/admin", permissionPath: "/admin" },
      { id: "system-config", title: t("nav.systemConfig"), path: "/system-config", permissionPath: "/system-config" },
      { id: "api-keys", title: t("nav.apiKeys"), path: "/api-keys", permissionPath: "/api-keys" },
      { id: "notifications", title: t("nav.notifications"), path: "/notifications", permissionPath: "/notifications" },
      { id: "settings", title: t("nav.settings"), path: "/settings", permissionPath: "/settings" },
    ],
  },
]

function NavSection({
  label,
  items,
  stages,
  canAccess,
}: {
  label: string
  items: NavItem[]
  stages: Record<string, string>
  canAccess: (path: string) => boolean
}) {
  const { t } = useTranslation()
  const { isMobile, setOpenMobile } = useSidebar()
  const navigate = useNavigate()
  const router = useRouterState()
  const currentPath = router.location.pathname
  const currentHash = (router.location.hash || "").replace(/^#/, "")
  const currentHref = locationHref(currentPath, router.location.searchStr, router.location.hash)
  const targetPathname = (path: string) => parseNavPath(path).to
  const isTargetActive = (path: string) => currentHref === navHref(path)
  const pathOwnsLocation = (path: string) => {
    const parsed = parseNavPath(path)
    const prefix = parsed.to
    // Exact path only — never claim sibling routes under the same prefix
    // (e.g. /investment-risk/overview must not own /investment-risk/pretrade-budget).
    const pathMatch = currentPath === prefix
    if (!pathMatch && !isTargetActive(path)) return false
    // Hash children (e.g. /risk-governance#alerts) must match hash; bare path only
    // matches when the URL has no hash (or the default first section).
    if (parsed.hash) {
      if (currentHash === parsed.hash) return true
      return !currentHash && parsed.hash === "limits" && pathMatch
    }
    return pathMatch || isTargetActive(path)
  }
  const groupOwnsLocation = (item: NavItem) => {
    if (item.children?.length) {
      if (item.children.some((child) => child.path && pathOwnsLocation(child.path))) return true
      // Parent index route only — do not treat all /prefix/* as this group
      // (portfolio-opt owns /investment-risk/pretrade-budget, not investment-risk).
      return currentPath === targetPathname(item.path)
    }
    return pathOwnsLocation(item.path)
  }
  const collapseOthers = (keepTitle: string | null) => {
    setOpenGroups((previous) => {
      const next = { ...previous }
      for (const other of items) {
        if (!other.children) continue
        next[other.title] = keepTitle != null && other.title === keepTitle
      }
      return next
    })
  }
  const go = (path: string) => {
    const parsed = parseNavPath(path)
    navigate({
      to: parsed.to,
      search: parsed.search,
      hash: parsed.hash,
    } as never)
  }
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      items
        .filter((item) => item.children)
        .map((item) => [item.title, groupOwnsLocation(item)]),
    ),
  )

  useEffect(() => {
    // Accordion: only the group that owns the current URL stays open.
    // Bail out with the previous object when nothing changed to avoid render loops
    // (parent passes a freshly filtered `items` array every render).
    setOpenGroups((previous) => {
      const next: Record<string, boolean> = {}
      let changed = false
      for (const item of items) {
        if (!item.children) continue
        const open = groupOwnsLocation(item)
        next[item.title] = open
        if (previous[item.title] !== open) changed = true
      }
      for (const key of Object.keys(previous)) {
        if (!(key in next) && previous[key]) {
          changed = true
          break
        }
      }
      return changed ? next : previous
    })
  }, [currentHref, items])

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            const visibleChildren = item.children?.filter((child) => (
              child.disabled || canAccess(child.permissionPath ?? item.permissionPaths?.[0] ?? item.path)
            ))
            const itemStage = stages[item.path]
              ?? item.permissionPaths?.map((path) => stages[path]).find(Boolean)
            const isParentActive = item.children
              ? groupOwnsLocation(item)
              : isTargetActive(item.path) || currentPath === targetPathname(item.path)
            const isOpen = item.children ? (openGroups[item.title] ?? false) : false
            return (
              <SidebarMenuItem key={item.id} data-testid={`nav-${item.id}`}>
                <SidebarMenuButton
                  tooltip={item.title}
                  isActive={isParentActive}
                  onClick={() => {
                    if (item.children) {
                      const willOpen = !isOpen
                      collapseOthers(willOpen ? item.title : null)
                      if (item.landing !== false && !groupOwnsLocation(item)) {
                        go(item.path)
                      }
                    } else {
                      collapseOthers(null)
                      go(item.path)
                    }
                    if (isMobile) setOpenMobile(false)
                  }}
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.title}</span>
                  {itemStage === "BETA" && (
                    <span className="ml-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-600 group-data-[collapsible=icon]:hidden dark:text-amber-400">
                      Beta
                    </span>
                  )}
                  {item.children && (
                    <ChevronDown className={`ml-auto h-3.5 w-3.5 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                  )}
                </SidebarMenuButton>
                {visibleChildren && isOpen && (
                  <SidebarMenuSub>
                    {visibleChildren.map((child) => (
                      <SidebarMenuSubItem key={child.id}>
                        <SidebarMenuSubButton
                          data-testid={`nav-${child.id}`}
                          isActive={Boolean(child.path && pathOwnsLocation(child.path))}
                          aria-disabled={child.disabled}
                          className={child.disabled ? "cursor-not-allowed opacity-50" : undefined}
                          onClick={() => {
                            if (child.disabled || !child.path) return
                            collapseOthers(item.title)
                            go(child.path)
                            if (isMobile) setOpenMobile(false)
                          }}
                        >
                          <span>{child.title}</span>
                          {child.disabled ? <span className="ml-auto text-[10px]">{t("nav.planned")}</span> : null}
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    ))}
                  </SidebarMenuSub>
                )}
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

export function AppSidebar() {
  const { t } = useTranslation()
  const { user: currentUser } = useAuth()
  const fsiItems = useMemo(() => getFsiItems(t), [t])
  const adminItems = useMemo(() => getAdminItems(t), [t])
  const accessQuery = useQuery({
    queryKey: ["my-access-context"],
    queryFn: () => fsiApi.getMyAccessContext().then((response) => response.data),
    enabled: Boolean(currentUser),
    staleTime: 30_000,
  })
  const menuPaths = accessQuery.data?.menu_paths
  const menuStages = accessQuery.data?.menu_stages
  const menuPathSet = useMemo(() => new Set(menuPaths ?? []), [menuPaths])
  // Superusers preview everything except HIDDEN modules; others follow granted GA paths.
  const hasMenu = useMemo(() => {
    const isSuper = Boolean(currentUser?.is_superuser)
    const stages = menuStages ?? {}
    return (path: string) => (isSuper ? stages[path] !== "HIDDEN" : menuPathSet.has(path))
  }, [currentUser?.is_superuser, menuPathSet, menuStages])
  const visibleFsiItems = useMemo(
    () => fsiItems.filter((item) => (item.permissionPaths ?? [item.path]).some(hasMenu)),
    [fsiItems, hasMenu],
  )
  const visibleAdminItems = useMemo(
    () => adminItems.filter((item) => (item.permissionPaths ?? [item.path]).some(hasMenu)),
    [adminItems, hasMenu],
  )

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <NavSection label={t("nav.fsiSection")} items={visibleFsiItems} stages={menuStages ?? {}} canAccess={hasMenu} />
        {visibleAdminItems.length > 0 ? (
          <NavSection label={t("nav.systemManagement")} items={visibleAdminItems} stages={menuStages ?? {}} canAccess={hasMenu} />
        ) : null}
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
