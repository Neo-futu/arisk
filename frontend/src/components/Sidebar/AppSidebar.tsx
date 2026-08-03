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

const fsiItems: NavItem[] = [
  { icon: Home, title: "儀表板", path: "/" },
  {
    icon: BarChart3,
    title: "投資風險分析",
    path: "/investment-risk",
    children: [
      { title: "模塊總覽", path: "/investment-risk" },
      { title: "組合概況", path: "/investment-risk/overview" },
      { title: "風險指標", path: "/investment-risk/indicators" },
      { title: "績效歸因", path: "/investment-risk/attribution" },
      { title: "利率與信用敏感度", path: "/investment-risk/rates-credit" },
      { title: "流動性與壓力測試", path: "/investment-risk/liquidity-stress" },
      { title: "風險預算與前置試算", path: "/investment-risk/pretrade-budget" },
      { title: "宏觀與市場動態", path: "/investment-risk/macro-dynamics" },
      { title: "基本面因子與行為", path: "/investment-risk/factor-behavior" },
    ],
  },
  { icon: List, title: "持倉明細", path: "/positions" },
  { icon: Shield, title: "合規核查", path: "/compliance" },
  { icon: FileText, title: "報表中心", path: "/reports" },
  { icon: CalendarClock, title: "定時任務", path: "/schedules" },
  { icon: Sparkles, title: "自動風控", path: "/autorisk" },
  { icon: MessageSquare, title: "Agent Chat", path: "/chat" },
  { icon: BookOpen, title: "專家知識庫", path: "/expert" },
]

const adminItems: NavItem[] = [
  { icon: Users, title: "用戶管理", path: "/admin" },
  { icon: KeyRound, title: "API Key 管理", path: "/api-keys" },
  { icon: Bell, title: "通知中心", path: "/notifications" },
  { icon: Settings, title: "設置", path: "/settings" },
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
  const { user: currentUser } = useAuth()

  const visibleAdminItems = currentUser?.is_superuser
    ? adminItems
    : adminItems.filter((i) => i.path !== "/admin")

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <NavSection label="阿雷斯 · 智能風控和投資分析系統" items={fsiItems} />
        <NavSection label="系統管理" items={visibleAdminItems} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
