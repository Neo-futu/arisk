import {
  BarChart3,
  Bell,
  BookOpen,
  CalendarClock,
  ChevronDown,
  FileText,
  Home,
  KeyRound,
  List,
  MessageSquare,
  Settings,
  Shield,
  Sparkles,
  Users,
} from "lucide-react"
import { useEffect, useState } from "react"
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
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { User } from "./User"

type NavItem = {
  icon: React.ComponentType<{ className?: string }>
  title: string
  path: string
  children?: Array<{ title: string; path: string }>
}

const getFsiItems = (t: (key: string) => string): NavItem[] => [
  { icon: Home, title: t("nav.dashboard"), path: "/" },
  {
    icon: BarChart3,
    title: t("nav.investmentRisk"),
    path: "/investment-risk",
    children: [
      { title: t("nav.moduleOverview"), path: "/investment-risk" },
      { title: t("nav.validation"), path: "/investment-risk/validation" },
      { title: t("nav.portfolioOverview"), path: "/investment-risk/overview" },
      { title: t("nav.riskIndicators"), path: "/investment-risk/indicators" },
      { title: t("nav.attribution"), path: "/investment-risk/attribution" },
      { title: t("nav.ratesCredit"), path: "/investment-risk/rates-credit" },
      { title: t("nav.liquidityStress"), path: "/investment-risk/liquidity-stress" },
      { title: t("nav.pretradeBudget"), path: "/investment-risk/pretrade-budget" },
      { title: t("nav.macroDynamics"), path: "/investment-risk/macro-dynamics" },
      { title: t("nav.factorBehavior"), path: "/investment-risk/factor-behavior" },
    ],
  },
  { icon: List, title: t("nav.positions"), path: "/positions" },
  { icon: Shield, title: t("nav.compliance"), path: "/compliance" },
  { icon: FileText, title: t("nav.reports"), path: "/reports" },
  { icon: CalendarClock, title: t("nav.schedules"), path: "/schedules" },
  { icon: Sparkles, title: t("nav.autorisk"), path: "/autorisk" },
  { icon: MessageSquare, title: t("nav.chat"), path: "/chat" },
  { icon: BookOpen, title: t("nav.expert"), path: "/expert" },
]

const getAdminItems = (t: (key: string) => string): NavItem[] => [
  { icon: Users, title: t("nav.userManagement"), path: "/admin" },
  { icon: KeyRound, title: t("nav.apiKeys"), path: "/api-keys" },
  { icon: Bell, title: t("nav.notifications"), path: "/notifications" },
  { icon: Settings, title: t("nav.settings"), path: "/settings" },
]

function NavSection({
  label,
  items,
}: {
  label: string
  items: NavItem[]
}) {
  const { isMobile, setOpenMobile } = useSidebar()
  const navigate = useNavigate()
  const router = useRouterState()
  const currentPath = router.location.pathname
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      items
        .filter((item) => item.children)
        .map((item) => [item.title, currentPath === item.path || currentPath.startsWith(`${item.path}/`)]),
    ),
  )

  useEffect(() => {
    setOpenGroups((previous) => {
      const next = { ...previous }
      for (const item of items) {
        if (!item.children) continue
        const isActive = currentPath === item.path || currentPath.startsWith(`${item.path}/`)
        if (isActive) {
          next[item.title] = true
        }
      }
      return next
    })
  }, [currentPath, items])

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            const isParentActive = item.children
              ? currentPath === item.path || currentPath.startsWith(`${item.path}/`)
              : currentPath === item.path
            const isOpen = item.children ? (openGroups[item.title] ?? false) : false
            return (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  tooltip={item.title}
                  isActive={isParentActive}
                  onClick={() => {
                    if (item.children) {
                      setOpenGroups((previous) => ({
                        ...previous,
                        [item.title]: !isOpen,
                      }))
                    } else {
                      navigate({ to: item.path })
                    }
                    if (isMobile) setOpenMobile(false)
                  }}
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.title}</span>
                  {item.children && (
                    <ChevronDown className={`ml-auto h-3.5 w-3.5 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                  )}
                </SidebarMenuButton>
                {item.children && isOpen && (
                  <SidebarMenuSub>
                    {item.children.map((child) => (
                      <SidebarMenuSubItem key={child.path}>
                        <SidebarMenuSubButton
                          isActive={currentPath === child.path}
                          onClick={() => {
                            navigate({ to: child.path })
                            if (isMobile) setOpenMobile(false)
                          }}
                        >
                          <span>{child.title}</span>
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
  const fsiItems = getFsiItems(t)
  const adminItems = getAdminItems(t)

  const visibleAdminItems = currentUser?.is_superuser
    ? adminItems
    : adminItems.filter((i) => i.path !== "/admin")

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <NavSection label={t("nav.fsiSection")} items={fsiItems} />
        <NavSection label={t("nav.systemManagement")} items={visibleAdminItems} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
