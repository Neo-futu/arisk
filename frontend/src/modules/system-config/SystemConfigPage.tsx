import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw, SlidersHorizontal } from "lucide-react"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi, type MenuRelease, type MenuReleaseStage } from "@/fsiClient"
import { groupMenusByPlatform } from "@/platform/menu-catalog"

const STAGES: MenuReleaseStage[] = ["GA", "BETA", "HIDDEN"]
const PROTECTED_CODES = new Set(["system-config", "admin", "settings"])

function stageVariant(stage: MenuReleaseStage) {
  if (stage === "GA") return "default" as const
  if (stage === "BETA") return "secondary" as const
  return "outline" as const
}

export function SystemConfigPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const releases = useQuery({
    queryKey: ["menu-releases"],
    queryFn: () => fsiApi.listMenuReleases().then((response) => response.data),
    staleTime: 15_000,
  })

  const mutation = useMutation({
    mutationFn: ({
      menu,
      release_stage,
      is_active,
    }: {
      menu: MenuRelease
      release_stage: MenuReleaseStage
      is_active: boolean
    }) => fsiApi.updateMenuRelease(menu.id, { release_stage, is_active }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["menu-releases"] })
      await queryClient.invalidateQueries({ queryKey: ["my-access-context"] })
      toast.success(t("systemConfig.saved"))
    },
    onError: () => toast.error(t("systemConfig.saveFailed")),
  })

  const groups = useMemo(
    () => groupMenusByPlatform(releases.data?.menus ?? []),
    [releases.data?.menus],
  )

  return (
    <div className="space-y-5" data-testid="platform-workbench">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Badge className="gap-1">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              {t("systemConfig.badge")}
            </Badge>
            <Badge variant="outline">{t("nav.systemManagement")}</Badge>
          </div>
          <h1 className="text-2xl font-bold tracking-tight">{t("systemConfig.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{t("systemConfig.subtitle")}</p>
        </div>
        <Button variant="outline" size="sm" disabled={releases.isFetching} onClick={() => void releases.refetch()}>
          <RefreshCw className={`mr-2 h-4 w-4 ${releases.isFetching ? "animate-spin" : ""}`} />
          {t("systemConfig.refresh")}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("systemConfig.legendTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-3">
          <div><Badge variant="default">GA</Badge> {t("systemConfig.legendGa")}</div>
          <div><Badge variant="secondary">BETA</Badge> {t("systemConfig.legendBeta")}</div>
          <div><Badge variant="outline">HIDDEN</Badge> {t("systemConfig.legendHidden")}</div>
        </CardContent>
      </Card>

      {releases.isError ? (
        <p className="py-6 text-center text-sm text-destructive">{t("systemConfig.loadFailed")}</p>
      ) : null}

      {groups.map((group) => (
        <Card key={group.id}>
          <CardHeader>
            <CardTitle className="text-base">{t(group.titleKey)}</CardTitle>
            <p className="text-xs text-muted-foreground">
              {t("systemConfig.groupCount", { count: group.menus.length })}
            </p>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("systemConfig.module")}</TableHead>
                    <TableHead>{t("systemConfig.path")}</TableHead>
                    <TableHead>{t("systemConfig.currentStage")}</TableHead>
                    <TableHead>{t("systemConfig.stage")}</TableHead>
                    <TableHead className="text-center">{t("systemConfig.active")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {group.menus.map((menu) => {
                    const locked = PROTECTED_CODES.has(menu.code)
                    const pending = mutation.isPending && mutation.variables?.menu.id === menu.id
                    return (
                      <TableRow key={menu.id} className={pending ? "opacity-60" : ""}>
                        <TableCell>
                          <div className="font-medium">{menu.name}</div>
                          <div className="font-mono text-xs text-muted-foreground">{menu.code}</div>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{menu.path ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant={stageVariant(menu.release_stage)}>{menu.release_stage}</Badge>
                        </TableCell>
                        <TableCell>
                          <Select
                            value={menu.release_stage}
                            disabled={locked || pending}
                            onValueChange={(value) =>
                              mutation.mutate({
                                menu,
                                release_stage: value as MenuReleaseStage,
                                is_active: menu.is_active,
                              })
                            }
                          >
                            <SelectTrigger className="h-8 w-32"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {STAGES.map((stage) => (
                                <SelectItem key={stage} value={stage}>{stage}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </TableCell>
                        <TableCell className="text-center">
                          <Switch
                            checked={menu.is_active}
                            disabled={locked || pending}
                            onCheckedChange={(checked) =>
                              mutation.mutate({
                                menu,
                                release_stage: menu.release_stage,
                                is_active: checked,
                              })
                            }
                          />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      ))}

      {!groups.length && !releases.isFetching ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            {t("systemConfig.empty")}
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
