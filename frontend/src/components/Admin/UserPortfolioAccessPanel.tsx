import { useQuery } from "@tanstack/react-query"
import { BriefcaseBusiness, Eye, ShieldCheck } from "lucide-react"

import type { UserPublic } from "@/client"
import UserAccessDialog from "@/components/Admin/UserAccessDialog"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi, type UserAccessGrant } from "@/fsiClient"

function toUserPublic(grant: UserAccessGrant): UserPublic {
  return {
    id: grant.user_id,
    email: grant.email,
    full_name: grant.full_name,
    is_active: grant.is_active,
    is_superuser: grant.is_superuser,
  }
}

function GrantRow({ grant }: { grant: UserAccessGrant }) {
  const manageCount = grant.portfolios.filter((p) => p.access_level === "MANAGE").length
  const viewCount = grant.portfolios.filter((p) => p.access_level === "VIEW").length

  return (
    <TableRow>
      <TableCell className="align-top">
        <div className="flex items-center gap-2">
          <span className="font-medium">{grant.full_name || grant.email}</span>
          {grant.is_superuser ? <Badge variant="default">超级管理员</Badge> : null}
          {!grant.is_active ? <Badge variant="outline">已停用</Badge> : null}
        </div>
        <p className="text-xs text-muted-foreground">{grant.email}</p>
      </TableCell>

      <TableCell className="align-top">
        {grant.roles.length === 0 ? (
          <span className="text-xs text-muted-foreground">未分配角色</span>
        ) : (
          <div className="flex flex-wrap gap-1">
            {grant.roles.map((role) => (
              <Badge key={role.id} variant="secondary" className="text-[11px]">
                {role.name}
              </Badge>
            ))}
          </div>
        )}
      </TableCell>

      <TableCell className="align-top">
        {grant.is_superuser ? (
          <Badge className="bg-orange-600 hover:bg-orange-600">
            <ShieldCheck className="mr-1 h-3 w-3" />
            全部组合 · MANAGE
          </Badge>
        ) : grant.portfolios.length === 0 ? (
          <span className="text-xs text-muted-foreground">未授权任何组合</span>
        ) : (
          <div className="space-y-2">
            <div className="flex gap-2 text-xs text-muted-foreground">
              <span>共 {grant.portfolios.length} 个组合</span>
              {manageCount > 0 ? <span className="text-orange-700">MANAGE {manageCount}</span> : null}
              {viewCount > 0 ? <span>VIEW {viewCount}</span> : null}
            </div>
            <div className="flex flex-wrap gap-1">
              {grant.portfolios.map((portfolio) => (
                <Badge
                  key={portfolio.port_id}
                  variant={portfolio.access_level === "MANAGE" ? "default" : "outline"}
                  className={portfolio.access_level === "MANAGE" ? "bg-orange-600 hover:bg-orange-600 text-[11px]" : "text-[11px]"}
                  title={`${portfolio.port_id} · ${portfolio.access_level}`}
                >
                  {portfolio.access_level === "MANAGE" ? (
                    <ShieldCheck className="mr-1 h-3 w-3" />
                  ) : (
                    <Eye className="mr-1 h-3 w-3" />
                  )}
                  {portfolio.port_name || portfolio.port_id}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </TableCell>

      <TableCell className="align-top text-right">
        {grant.is_superuser ? (
          <span className="text-xs text-muted-foreground">系统内置</span>
        ) : (
          <UserAccessDialog user={toUserPublic(grant)} triggerVariant="button" onSuccess={() => {}} />
        )}
      </TableCell>
    </TableRow>
  )
}

export default function UserPortfolioAccessPanel() {
  const grantsQuery = useQuery({
    queryKey: ["access-control-grants"],
    queryFn: () => fsiApi.getAccessGrants().then((response) => response.data.grants),
    staleTime: 30_000,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BriefcaseBusiness className="h-5 w-5 text-orange-600" />
          用户 · 角色 · 组合授权总览
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          集中查看每位用户的平台角色，以及其对具体组合的授权（VIEW 查看/监督，MANAGE 投资管理/交易）。点击「配置授权」即可调整。
        </p>
      </CardHeader>
      <CardContent>
        {grantsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">正在加载授权总览...</p>
        ) : grantsQuery.isError ? (
          <p className="text-sm text-destructive">加载授权总览失败，请刷新重试。</p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-64">用户</TableHead>
                  <TableHead className="w-56">平台角色</TableHead>
                  <TableHead>组合授权</TableHead>
                  <TableHead className="w-32 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(grantsQuery.data ?? []).map((grant) => (
                  <GrantRow key={grant.user_id} grant={grant} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
