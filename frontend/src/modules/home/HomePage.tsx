import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  BarChart3,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  List,
  MessageSquare,
  PieChart,
  Scale,
  Sparkles,
} from "lucide-react"
import { useTranslation } from "react-i18next"

import { lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi } from "@/fsiClient"
import useAuth from "@/hooks/useAuth"
import { parseNavPath } from "@/platform/nav"

type FeatureEntry = {
  id: string
  path: string
  permissionPaths?: string[]
  titleKey: string
  descKey: string
  categoryKey: string
  icon: React.ComponentType<{ className?: string }>
}

const FEATURE_ENTRIES: FeatureEntry[] = [
  {
    id: "portfolio-cockpit",
    path: "/portfolio-cockpit",
    titleKey: "nav.portfolioCockpit",
    descKey: "home.feat.cockpit",
    categoryKey: "home.catRisk",
    icon: Gauge,
  },
  {
    id: "investment-risk",
    path: "/investment-risk",
    titleKey: "nav.investmentRisk",
    descKey: "home.feat.ir",
    categoryKey: "home.catInvest",
    icon: BarChart3,
  },
  {
    id: "portfolio-opt",
    path: "/portfolio-opt",
    titleKey: "nav.portfolioAllocationOptimization",
    descKey: "home.feat.po",
    categoryKey: "home.catInvest",
    icon: PieChart,
  },
  {
    id: "risk-testing",
    path: "/risk-testing",
    titleKey: "nav.riskTesting",
    descKey: "home.feat.rt",
    categoryKey: "home.catInvest",
    icon: FlaskConical,
  },
  {
    id: "trading",
    path: "/trading",
    permissionPaths: ["/trading", "/data-management"],
    titleKey: "nav.tradingManagement",
    descKey: "home.feat.trading",
    categoryKey: "home.catOps",
    icon: List,
  },
  {
    id: "risk-governance",
    path: "/risk-governance",
    permissionPaths: ["/risk-governance", "/risk-rules", "/compliance"],
    titleKey: "nav.riskGovernance",
    descKey: "home.feat.gov",
    categoryKey: "home.catOps",
    icon: Scale,
  },
  {
    id: "reports",
    path: "/reports",
    titleKey: "nav.reports",
    descKey: "home.feat.reports",
    categoryKey: "home.catOps",
    icon: FileText,
  },
  {
    id: "data-management",
    path: "/data-management",
    permissionPaths: ["/data-management", "/positions"],
    titleKey: "nav.dataManagement",
    descKey: "home.feat.data",
    categoryKey: "home.catOps",
    icon: Database,
  },
  {
    id: "autorisk",
    path: "/autorisk",
    titleKey: "nav.autorisk",
    descKey: "home.feat.autorisk",
    categoryKey: "home.catAi",
    icon: Sparkles,
  },
  {
    id: "agent-ai",
    path: "/chat",
    permissionPaths: ["/chat", "/expert"],
    titleKey: "nav.agentAi",
    descKey: "home.feat.ai",
    categoryKey: "home.catAi",
    icon: MessageSquare,
  },
]

type TodoItem = {
  key: string
  title: string
  urgency: "error" | "warning"
  actionLabel: string
  onAction: () => void
}

function stageLabel(
  t: (key: string) => string,
  stage: string | undefined,
  granted: boolean,
) {
  if (stage === "BETA")
    return { text: t("home.beta"), tone: "warning" as const }
  if (stage === "HIDDEN")
    return { text: t("home.hidden"), tone: "muted" as const }
  if (granted) return { text: t("home.ga"), tone: "success" as const }
  return { text: t("home.notGranted"), tone: "muted" as const }
}

export function HomePage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const asOfDate = lastTradeDate()

  const accessQuery = useQuery({
    queryKey: ["my-access-context"],
    queryFn: () =>
      fsiApi.getMyAccessContext().then((response) => response.data),
    staleTime: 30_000,
  })
  const overviewQuery = useQuery({
    queryKey: ["portfolio-dashboard-overview", asOfDate],
    queryFn: () =>
      fsiApi.getDashboardOverview(asOfDate).then((response) => response.data),
    enabled: accessQuery.isSuccess,
    staleTime: 30_000,
    retry: 1,
  })

  const menuPaths = new Set(accessQuery.data?.menu_paths ?? [])
  const menuStages = accessQuery.data?.menu_stages ?? {}
  const hasMenu = (path: string) =>
    user?.is_superuser ? menuStages[path] !== "HIDDEN" : menuPaths.has(path)

  const go = (path: string) => {
    const parsed = parseNavPath(path)
    navigate({
      to: parsed.to,
      search: parsed.search,
      hash: parsed.hash,
    } as never)
  }

  const visibleFeatures = FEATURE_ENTRIES.filter((item) =>
    (item.permissionPaths ?? [item.path]).some(hasMenu),
  )

  const todos: TodoItem[] = []
  const portfolios = accessQuery.data?.portfolios ?? []
  if (accessQuery.isSuccess && portfolios.length === 0) {
    todos.push({
      key: "no-portfolio",
      title: t("home.todoNoPortfolio"),
      urgency: "error",
      actionLabel: t("home.actionCockpit"),
      onAction: () => go("/portfolio-cockpit"),
    })
  }
  if (overviewQuery.isError) {
    todos.push({
      key: "overview-error",
      title: t("home.todoOverviewError"),
      urgency: "error",
      actionLabel: t("home.actionRetry"),
      onAction: () => {
        void overviewQuery.refetch()
      },
    })
  }
  const breached = overviewQuery.data?.breached ?? 0
  if (breached > 0) {
    todos.push({
      key: "breaches",
      title: t("home.todoBreaches", { count: breached }),
      urgency: "warning",
      actionLabel: t("home.actionCockpit"),
      onAction: () => go("/portfolio-cockpit"),
    })
  }
  const warnedBeta = visibleFeatures.filter((item) => {
    const stage =
      menuStages[item.path] ??
      item.permissionPaths?.map((path) => menuStages[path]).find(Boolean)
    return stage === "BETA"
  })
  if (warnedBeta.length > 0) {
    todos.push({
      key: "beta",
      title: t("home.todoBeta", { count: warnedBeta.length }),
      urgency: "warning",
      actionLabel: t("home.enter"),
      onAction: () => go(warnedBeta[0].path),
    })
  }

  const displayName = user?.full_name || user?.email || ""

  return (
    <div className="space-y-5" data-testid="home-workbench">
      <h1 className="text-xl font-semibold tracking-tight">
        {t("home.hello", { user: displayName })}
      </h1>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("home.todos")}</CardTitle>
        </CardHeader>
        <CardContent>
          {accessQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">{t("home.loading")}</p>
          ) : todos.length === 0 ? (
            <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              {t("home.noTodos")}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {todos.map((todo) => (
                <div
                  key={todo.key}
                  className={`flex items-center justify-between gap-3 rounded-md border px-3.5 py-2.5 ${
                    todo.urgency === "error"
                      ? "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
                      : "border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40"
                  }`}
                >
                  <div className="flex items-center gap-2 text-sm">
                    <span
                      className={`h-2 w-2 shrink-0 rounded-full ${
                        todo.urgency === "error"
                          ? "bg-destructive"
                          : "bg-amber-500"
                      }`}
                    />
                    <span>{todo.title}</span>
                  </div>
                  <Button size="sm" onClick={todo.onAction}>
                    {todo.actionLabel}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("home.shortcuts")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {visibleFeatures.map((item) => {
              const Icon = item.icon
              const stage =
                menuStages[item.path] ??
                item.permissionPaths
                  ?.map((path) => menuStages[path])
                  .find(Boolean)
              return (
                <button
                  key={item.id}
                  type="button"
                  data-testid={`home-shortcut-${item.id}`}
                  onClick={() => go(item.path)}
                  className="flex h-[72px] items-center gap-3 rounded-lg border px-4 text-left transition-colors hover:border-primary/60 hover:bg-accent/40"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">
                        {t(item.titleKey)}
                      </span>
                      {stage === "BETA" ? (
                        <Badge
                          variant="outline"
                          className="h-5 px-1.5 text-[10px] uppercase"
                        >
                          Beta
                        </Badge>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                      {t(item.descKey)}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            {t("home.statusOverview")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-28">{t("home.colCategory")}</TableHead>
                <TableHead>{t("home.colItem")}</TableHead>
                <TableHead className="w-48">{t("home.colStatus")}</TableHead>
                <TableHead className="w-24">{t("home.colAction")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {FEATURE_ENTRIES.map((item) => {
                const granted = (item.permissionPaths ?? [item.path]).some(
                  hasMenu,
                )
                const stage =
                  menuStages[item.path] ??
                  item.permissionPaths
                    ?.map((path) => menuStages[path])
                    .find(Boolean)
                const status = stageLabel(t, stage, granted)
                return (
                  <TableRow
                    key={item.id}
                    className={granted ? undefined : "opacity-60"}
                    data-testid={`home-status-${item.id}`}
                  >
                    <TableCell className="text-muted-foreground">
                      {t(item.categoryKey)}
                    </TableCell>
                    <TableCell className="whitespace-normal">
                      <div className="font-medium">{t(item.titleKey)}</div>
                      <div className="text-xs text-muted-foreground">
                        {t(item.descKey)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs ${
                          status.tone === "success"
                            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
                            : status.tone === "warning"
                              ? "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"
                              : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {status.tone === "success" ? (
                          <CheckCircle2 className="h-3.5 w-3.5" />
                        ) : (
                          <Clock3 className="h-3.5 w-3.5" />
                        )}
                        {status.text}
                      </span>
                    </TableCell>
                    <TableCell>
                      {granted ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => go(item.path)}
                        >
                          {t("home.enter")}
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {t("home.notGranted")}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
