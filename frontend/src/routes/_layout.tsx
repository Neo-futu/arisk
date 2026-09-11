import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { Footer } from "@/components/Common/Footer"
import { LanguageSwitcher } from "@/components/Common/LanguageSwitcher"
import { FloatingAiChat } from "@/components/FloatingAiChat"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { isLoggedIn } from "@/hooks/useAuth"
import { PageContextProvider } from "@/platform/page-context"
import { useHashScroll } from "@/platform/useHashScroll"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

function Layout() {
  return (
    <PageContextProvider>
      <LayoutShell />
    </PageContextProvider>
  )
}

function LayoutShell() {
  useHashScroll()
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="bg-background">
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-card px-4 shadow-[0_1px_4px_rgba(0,0,0,0.04)]">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
          <div className="ml-auto">
            <LanguageSwitcher />
          </div>
        </header>
        <main className="flex-1 p-5 md:p-6">
          <div className="mx-auto max-w-7xl rounded-[10px] bg-card p-7 shadow-[0_1px_4px_rgba(0,0,0,0.06)]">
            <Outlet />
          </div>
        </main>
        <Footer />
        <FloatingAiChat />
      </SidebarInset>
    </SidebarProvider>
  )
}
