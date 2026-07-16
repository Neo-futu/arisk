import {
  BarChart3,
  BookOpen,
  CalendarClock,
  FileText,
  Home,
  List,
  MessageSquare,
  Settings,
  Shield,
  Users,
} from "lucide-react"

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
  useSidebar,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { useNavigate, useRouterState } from "@tanstack/react-router"
import { User } from "./User"

type NavItem = {
  icon: React.ComponentType<{ className?: string }>
  title: string
  path: string
}

const fsiItems: NavItem[] = [
  { icon: Home, title: "儀表板", path: "/" },
  { icon: BarChart3, title: "風控分析", path: "/risk" },
  { icon: List, title: "持倉明細", path: "/positions" },
  { icon: Shield, title: "合規核查", path: "/compliance" },
  { icon: FileText,     title: "報表中心", path: "/reports" },
  { icon: CalendarClock, title: "定時任務", path: "/schedules" },
  { icon: MessageSquare, title: "Agent Chat", path: "/chat" },
  { icon: BookOpen,      title: "專家知識庫", path: "/expert" },
]

const adminItems: NavItem[] = [
  { icon: Users, title: "用戶管理", path: "/admin" },
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

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton
                tooltip={item.title}
                isActive={currentPath === item.path}
                onClick={() => {
                  navigate({ to: item.path })
                  if (isMobile) setOpenMobile(false)
                }}
              >
                <item.icon className="h-4 w-4" />
                <span>{item.title}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const visibleAdminItems = currentUser?.is_superuser
    ? adminItems
    : adminItems.filter((i) => i.path === "/settings")

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
