import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ShieldCheck } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import type { UserPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fsiApi, type PortfolioAccessLevel } from "@/fsiClient"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface UserAccessDialogProps {
  user: UserPublic
  onSuccess: () => void
  /** "dropdown" renders a DropdownMenuItem trigger (row actions menu);
   *  "button" renders a standalone Button trigger (overview panel). */
  triggerVariant?: "dropdown" | "button"
}

type GrantValue = PortfolioAccessLevel | "NONE"

export default function UserAccessDialog({ user, onSuccess, triggerVariant = "dropdown" }: UserAccessDialogProps) {
  const [open, setOpen] = useState(false)
  const [roleIds, setRoleIds] = useState<string[]>([])
  const [portfolioGrants, setPortfolioGrants] = useState<Record<string, GrantValue>>({})
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const catalogQuery = useQuery({
    queryKey: ["access-control-catalog"],
    queryFn: () => fsiApi.getAccessCatalog().then((response) => response.data),
    enabled: open,
    staleTime: 30_000,
  })
  const userAccessQuery = useQuery({
    queryKey: ["user-access", user.id],
    queryFn: () => fsiApi.getUserAccess(user.id).then((response) => response.data),
    enabled: open,
  })

  useEffect(() => {
    if (!userAccessQuery.data) return
    setRoleIds(userAccessQuery.data.role_ids)
    setPortfolioGrants(
      Object.fromEntries(
        userAccessQuery.data.portfolios.map((grant) => [grant.port_id, grant.access_level]),
      ),
    )
  }, [userAccessQuery.data])

  const managerRole = catalogQuery.data?.roles.find((role) => role.code === "INVESTMENT_MANAGER")
  const selectedPermissionCodes = useMemo(() => {
    if (!catalogQuery.data) return new Set<string>()
    const selectedPermissionIds = new Set(
      catalogQuery.data.roles
        .filter((role) => roleIds.includes(role.id))
        .flatMap((role) => role.permission_ids),
    )
    return new Set(
      catalogQuery.data.permissions
        .filter((permission) => selectedPermissionIds.has(permission.id))
        .map((permission) => permission.code),
    )
  }, [catalogQuery.data, roleIds])

  const hasManageGrant = Object.values(portfolioGrants).includes("MANAGE")
  const invalidManageGrant = hasManageGrant && !(
    selectedPermissionCodes.has("portfolio.manage") && selectedPermissionCodes.has("trade.manage")
  )

  const mutation = useMutation({
    mutationFn: () => fsiApi.updateUserAccess(user.id, {
      role_ids: roleIds,
      portfolios: Object.entries(portfolioGrants)
        .filter(([, level]) => level !== "NONE")
        .map(([port_id, access_level]) => ({
          port_id,
          access_level: access_level as PortfolioAccessLevel,
        })),
    }),
    onSuccess: () => {
      showSuccessToast("用户角色与组合权限已更新")
      void queryClient.invalidateQueries({ queryKey: ["users"] })
      void queryClient.invalidateQueries({ queryKey: ["user-access", user.id] })
      void queryClient.invalidateQueries({ queryKey: ["access-control-grants"] })
      setOpen(false)
      onSuccess()
    },
    onError: handleError.bind(showErrorToast),
  })

  const setGrant = (portId: string, value: GrantValue) => {
    setPortfolioGrants((current) => ({ ...current, [portId]: value }))
    if (value === "MANAGE" && managerRole) {
      setRoleIds((current) => current.includes(managerRole.id) ? current : [...current, managerRole.id])
    }
  }

  const loading = catalogQuery.isLoading || userAccessQuery.isLoading

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {triggerVariant === "button" ? (
        <Button
          variant="outline"
          size="sm"
          className="border-orange-300 text-orange-700 hover:bg-orange-50 hover:text-orange-800"
          onClick={() => setOpen(true)}
        >
          <ShieldCheck className="text-orange-600" />
          配置授权
        </Button>
      ) : (
        <DropdownMenuItem
          className="text-orange-700 focus:text-orange-800"
          onSelect={(event) => event.preventDefault()}
          onClick={() => setOpen(true)}
        >
          <ShieldCheck className="text-orange-600" />
          角色与组合授权
        </DropdownMenuItem>
      )}
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-orange-600" />
            用户角色与组合授权
          </DialogTitle>
          <DialogDescription>
            {user.full_name || user.email} · VIEW 用于查看/监督，MANAGE 用于投资管理与交易。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">正在加载授权配置...</p>
        ) : (
          <div className="space-y-6">
            <section>
              <h3 className="mb-3 text-sm font-semibold">平台菜单角色</h3>
              <div className="grid gap-3 md:grid-cols-2">
                {catalogQuery.data?.roles.map((role) => (
                  <label key={role.id} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3">
                    <Checkbox
                      checked={roleIds.includes(role.id)}
                      onCheckedChange={(checked) => setRoleIds((current) =>
                        checked ? [...new Set([...current, role.id])] : current.filter((id) => id !== role.id),
                      )}
                    />
                    <span>
                      <span className="flex items-center gap-2 text-sm font-medium">
                        {role.name}
                        <Badge variant="outline" className="text-[10px]">{role.code}</Badge>
                      </span>
                      <span className="mt-1 block text-xs text-muted-foreground">{role.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <section>
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold">组合职能权限</h3>
                <div className="flex gap-2 text-xs">
                  <Badge variant="outline">VIEW 查看/总监监督</Badge>
                  <Badge className="bg-orange-600 hover:bg-orange-600">MANAGE 投资管理/交易</Badge>
                </div>
              </div>
              <div className="space-y-2">
                {catalogQuery.data?.portfolios.filter((portfolio) => portfolio.is_active).map((portfolio) => (
                  <div key={portfolio.port_id} className="grid items-center gap-3 rounded-lg border p-3 sm:grid-cols-[1fr_220px]">
                    <div>
                      <p className="text-sm font-medium">{portfolio.port_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {portfolio.port_id} · {portfolio.port_type} · {portfolio.base_currency}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        投资经理：{portfolio.manager_name || "未指派"}
                      </p>
                    </div>
                    <Select
                      value={portfolioGrants[portfolio.port_id] ?? "NONE"}
                      onValueChange={(value) => setGrant(portfolio.port_id, value as GrantValue)}
                    >
                      <SelectTrigger className={portfolioGrants[portfolio.port_id] === "MANAGE" ? "border-orange-400 text-orange-700" : ""}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="NONE">无权限</SelectItem>
                        <SelectItem value="VIEW">VIEW · 查看与监督</SelectItem>
                        <SelectItem value="MANAGE">MANAGE · 投资管理与交易</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
              {invalidManageGrant ? (
                <p className="mt-2 text-sm text-destructive">MANAGE 授权必须同时选择具备投资管理和交易权限的角色。</p>
              ) : null}
            </section>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
          <Button
            className="bg-orange-600 hover:bg-orange-700"
            disabled={loading || invalidManageGrant || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "保存中..." : "保存授权"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
