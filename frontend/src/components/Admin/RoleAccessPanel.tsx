import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Settings2, Shield, Trash2 } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { fsiApi, type AccessCatalog, type AccessRole } from "@/fsiClient"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

const BUILTIN_ROLE_CODES = new Set([
  "PORTFOLIO_VIEWER",
  "INVESTMENT_DIRECTOR",
  "INVESTMENT_MANAGER",
  "SYSTEM_ADMIN",
])

type EditorMode = { type: "edit"; role: AccessRole } | { type: "create" }

function RoleEditor({
  mode,
  catalog,
  onClose,
}: {
  mode: EditorMode
  catalog: AccessCatalog
  onClose: () => void
}) {
  const isCreate = mode.type === "create"
  const role = mode.type === "edit" ? mode.role : null
  const isBuiltin = role ? BUILTIN_ROLE_CODES.has(role.code) : false

  const [name, setName] = useState(role?.name ?? "")
  const [code, setCode] = useState(role?.code ?? "")
  const [description, setDescription] = useState(role?.description ?? "")
  const [isActive, setIsActive] = useState(role?.is_active ?? true)
  const [permissionIds, setPermissionIds] = useState(role?.permission_ids ?? [])
  const [menuIds, setMenuIds] = useState(role?.menu_ids ?? [])
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["access-control-catalog"] })
    void queryClient.invalidateQueries({ queryKey: ["access-control-grants"] })
    void queryClient.invalidateQueries({ queryKey: ["my-access-context"] })
  }

  const mutation = useMutation({
    mutationFn: () =>
      isCreate
        ? fsiApi.createRole({
            name,
            code,
            description: description || null,
            is_active: isActive,
            permission_ids: permissionIds,
            menu_ids: menuIds,
          })
        : fsiApi.updateRoleAccess(role!.id, {
            name,
            description: description || null,
            is_active: isActive,
            permission_ids: permissionIds,
            menu_ids: menuIds,
          }),
    onSuccess: () => {
      showSuccessToast(isCreate ? "角色已创建" : "角色配置已更新")
      invalidate()
      onClose()
    },
    onError: handleError.bind(showErrorToast),
  })

  const toggle = (values: string[], id: string, checked: boolean) =>
    checked ? [...new Set([...values, id])] : values.filter((value) => value !== id)

  const canSubmit = name.trim().length > 0 && (!isCreate || /^[A-Za-z][A-Za-z0-9_]*$/.test(code))

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isCreate ? "新建角色" : `配置角色：${role!.name}`}</DialogTitle>
          <DialogDescription>
            {isCreate ? "定义角色的标识、菜单可见性与功能权限。" : `${role!.code} · 配置菜单可见性与功能权限。`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          <section className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>角色名称 <span className="text-destructive">*</span></Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如：合规经理" />
            </div>
            <div className="space-y-2">
              <Label>角色代码 {isCreate ? <span className="text-destructive">*</span> : null}</Label>
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="如：COMPLIANCE_OFFICER"
                disabled={!isCreate}
              />
              {isCreate ? <p className="text-xs text-muted-foreground">字母开头，仅限字母/数字/下划线；创建后不可修改。</p> : null}
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label>描述</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="角色职责说明" />
            </div>
            <div className="flex items-center gap-3 sm:col-span-2">
              <Switch checked={isActive} onCheckedChange={setIsActive} disabled={isBuiltin && role?.code === "SYSTEM_ADMIN"} />
              <span className="text-sm">启用该角色</span>
            </div>
          </section>

          <section>
            <h3 className="mb-3 text-sm font-semibold">菜单权限</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {catalog.menus.map((menu) => (
                <label key={menu.id} className="flex cursor-pointer items-center gap-3 rounded-md border p-3">
                  <Checkbox
                    checked={menuIds.includes(menu.id)}
                    onCheckedChange={(checked) => setMenuIds((current) => toggle(current, menu.id, checked === true))}
                  />
                  <span>
                    <span className="block text-sm font-medium">{menu.name}</span>
                    <span className="text-xs text-muted-foreground">{menu.path || menu.code}</span>
                  </span>
                </label>
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 text-sm font-semibold">功能权限</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {catalog.permissions.map((permission) => (
                <label key={permission.id} className="flex cursor-pointer items-start gap-3 rounded-md border p-3">
                  <Checkbox
                    checked={permissionIds.includes(permission.id)}
                    onCheckedChange={(checked) => setPermissionIds((current) => toggle(current, permission.id, checked === true))}
                  />
                  <span>
                    <span className="block text-sm font-medium">{permission.name}</span>
                    <span className="text-xs text-muted-foreground">{permission.code}</span>
                  </span>
                </label>
              ))}
            </div>
          </section>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button
            className="bg-orange-600 hover:bg-orange-700"
            disabled={!canSubmit || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "保存中..." : isCreate ? "创建角色" : "保存角色配置"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DeleteRoleButton({ role }: { role: AccessRole }) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const mutation = useMutation({
    mutationFn: () => fsiApi.deleteRole(role.id),
    onSuccess: () => {
      showSuccessToast("角色已删除")
      void queryClient.invalidateQueries({ queryKey: ["access-control-catalog"] })
      void queryClient.invalidateQueries({ queryKey: ["access-control-grants"] })
      setOpen(false)
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        variant="ghost"
        size="sm"
        className="mt-2 w-full text-destructive hover:bg-destructive/10 hover:text-destructive"
        onClick={() => setOpen(true)}
      >
        <Trash2 />
        删除角色
      </Button>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>删除角色：{role.name}</DialogTitle>
          <DialogDescription>
            此操作不可撤销。若该角色仍分配给用户，需先取消分配。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={mutation.isPending}>取消</Button>
          </DialogClose>
          <Button variant="destructive" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "删除中..." : "确认删除"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function RoleAccessPanel() {
  const [editor, setEditor] = useState<EditorMode | null>(null)
  const catalogQuery = useQuery({
    queryKey: ["access-control-catalog"],
    queryFn: () => fsiApi.getAccessCatalog().then((response) => response.data),
    staleTime: 30_000,
  })

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-5 w-5 text-orange-600" />
              角色、菜单与功能权限
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              角色决定平台菜单和职能能力；组合 VIEW/MANAGE 范围在用户行的橙色授权入口配置。
            </p>
          </div>
          <Button
            className="bg-orange-600 hover:bg-orange-700"
            size="sm"
            disabled={!catalogQuery.data}
            onClick={() => setEditor({ type: "create" })}
          >
            <Plus />
            新建角色
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {catalogQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">正在加载角色配置...</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {catalogQuery.data?.roles.map((role) => (
              <div key={role.id} className="rounded-lg border p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{role.name}</p>
                    <p className="text-xs text-muted-foreground">{role.code}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Badge variant={role.is_active ? "secondary" : "outline"}>
                      {role.is_active ? "启用" : "停用"}
                    </Badge>
                    {BUILTIN_ROLE_CODES.has(role.code) ? (
                      <Badge variant="outline" className="text-[10px]">内置</Badge>
                    ) : null}
                  </div>
                </div>
                <p className="mt-3 min-h-10 text-xs text-muted-foreground">{role.description}</p>
                <div className="mt-3 flex gap-2 text-xs text-muted-foreground">
                  <span>{role.menu_ids.length} 个菜单</span>
                  <span>·</span>
                  <span>{role.permission_ids.length} 项权限</span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-4 w-full border-orange-300 text-orange-700 hover:bg-orange-50 hover:text-orange-800"
                  onClick={() => setEditor({ type: "edit", role })}
                >
                  <Settings2 />
                  配置角色权限
                </Button>
                {!BUILTIN_ROLE_CODES.has(role.code) ? <DeleteRoleButton role={role} /> : null}
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {editor && catalogQuery.data ? (
        <RoleEditor mode={editor} catalog={catalogQuery.data} onClose={() => setEditor(null)} />
      ) : null}
    </Card>
  )
}
