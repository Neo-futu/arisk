import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute, redirect } from "@tanstack/react-router"
import { Shield, Users } from "lucide-react"
import { Suspense } from "react"
import { useTranslation } from "react-i18next"

import { type UserPublic, UsersService } from "@/client"
import AddUser from "@/components/Admin/AddUser"
import RoleAccessPanel from "@/components/Admin/RoleAccessPanel"
import UserPortfolioAccessPanel from "@/components/Admin/UserPortfolioAccessPanel"
import { columns, type UserTableData } from "@/components/Admin/columns"
import { DataTable } from "@/components/Common/DataTable"
import PendingUsers from "@/components/Pending/PendingUsers"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"
import { fsiApi } from "@/fsiClient"

function getUsersQueryOptions() {
  return {
    queryFn: () => UsersService.readUsers({ skip: 0, limit: 100 }),
    queryKey: ["users"],
  }
}

export const Route = createFileRoute("/_layout/admin")({
  component: Admin,
  beforeLoad: async () => {
    const access = await fsiApi.getMyAccessContext().then((response) => response.data)
    if (!access.can_manage_access) {
      throw redirect({ to: "/" })
    }
  },
  head: () => ({
    meta: [{ title: "用户与权限管理 — ARISK" }],
  }),
})

function UsersTableContent() {
  const { user: currentUser } = useAuth()
  const { data: users } = useSuspenseQuery(getUsersQueryOptions())

  const tableData: UserTableData[] = users.data.map((user: UserPublic) => ({
    ...user,
    isCurrentUser: currentUser?.id === user.id,
  }))

  return <DataTable columns={columns} data={tableData} />
}

function UsersTable() {
  return (
    <Suspense fallback={<PendingUsers />}>
      <UsersTableContent />
    </Suspense>
  )
}

function Admin() {
  const { t } = useTranslation()
  return (
    <div className="space-y-5" data-testid="platform-workbench">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge className="gap-1">
              <Users className="h-3.5 w-3.5" />
              {t("nav.systemManagement")}
            </Badge>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("admin.pageTitle")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("admin.pageSubtitle")}</p>
        </div>
        <AddUser />
      </div>

      <Tabs defaultValue="users" className="space-y-4">
        <TabsList className="grid w-full max-w-xl grid-cols-3">
          <TabsTrigger value="users">{t("admin.tabs.users")}</TabsTrigger>
          <TabsTrigger value="grants">{t("admin.tabs.grants")}</TabsTrigger>
          <TabsTrigger value="roles">{t("admin.tabs.roles")}</TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="mt-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Users className="h-4 w-4 text-primary" />
                {t("admin.tabs.users")}
              </CardTitle>
              <p className="text-sm text-muted-foreground">{t("admin.usersHint")}</p>
            </CardHeader>
            <CardContent>
              <UsersTable />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="grants" className="mt-0">
          <UserPortfolioAccessPanel />
        </TabsContent>

        <TabsContent value="roles" className="mt-0">
          <RoleAccessPanel />
        </TabsContent>
      </Tabs>

      <Card className="border-dashed">
        <CardContent className="flex items-start gap-3 pt-5 text-sm text-muted-foreground">
          <Shield className="mt-0.5 h-4 w-4 shrink-0 text-orange-600" />
          <p>{t("admin.platformHint")}</p>
        </CardContent>
      </Card>
    </div>
  )
}
