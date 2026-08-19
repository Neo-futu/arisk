import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { BriefcaseBusiness, RefreshCw, TrendingDown, UserRound, Users, Waves } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import { lastTradeDate } from "@/components/FsiToolbar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DatePicker } from "@/components/DatePicker"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fsiApi, type ExposureResult, type PortfolioDashboardOverview } from "@/fsiClient"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "儀表板 — ARISK" }],
  }),
})

const LATEST_EXPOSURE_DATE_CACHE_TTL_MS = 60_000

type LatestExposureDateCacheEntry = {
  effectiveDate: string
  expiresAt: number
}

const latestExposureDateCache = new Map<string, LatestExposureDateCacheEntry>()

async function resolveLatestExposureDate(fundId: string, requestedDate: string) {
  const now = Date.now()
  const cached = latestExposureDateCache.get(fundId)

  // Reuse short-lived per-fund cache when requested date is not earlier than cached effective date.
  if (cached && cached.expiresAt > now && requestedDate >= cached.effectiveDate) {
    return {
      effectiveDate: cached.effectiveDate,
      fallbackUsed: cached.effectiveDate !== requestedDate,
    }
  }

  const response = await fsiApi.getExposureLatestDate(fundId, requestedDate)
  const latestDate = response.data.effective_date

  if (latestDate) {
    latestExposureDateCache.set(fundId, {
      effectiveDate: latestDate,
      expiresAt: now + LATEST_EXPOSURE_DATE_CACHE_TTL_MS,
    })
  }

  const effectiveDate = latestDate ?? requestedDate
  return {
    effectiveDate,
    fallbackUsed: effectiveDate !== requestedDate,
  }
}

function MetricCard({
  title,
  value,
  sub,
  limit,
  status,
  icon: Icon,
}: {
  title: string
  value: string
  sub?: string
  limit?: string
  status?: "ok" | "warn" | "breach"
  icon: React.ComponentType<{ className?: string }>
}) {
  const iconColor =
    status === "breach"
      ? "text-destructive"
      : status === "warn"
        ? "text-yellow-500"
        : "text-green-500"
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className={`h-4 w-4 ${iconColor}`} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        {limit && (
          <p className="text-xs text-muted-foreground mt-1">{limit}</p>
        )}
      </CardContent>
    </Card>
  )
}

function AllPortfolioOverview({
  data,
  selectedFundId,
  onSelect,
}: {
  data: PortfolioDashboardOverview
  selectedFundId: string
  onSelect: (fundId: string) => void
}) {
  const { t } = useTranslation()

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <BriefcaseBusiness className="h-5 w-5 text-primary" />
              {t("dashboard.authorizedPortfolioOverview")}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">{t("dashboard.authorizedPortfolioHint")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{t("dashboard.portfolioTotal", { count: data.total })}</Badge>
            <Badge className="bg-green-600 hover:bg-green-600">{t("dashboard.portfolioCompliant", { count: data.compliant })}</Badge>
            <Badge variant={data.breached > 0 ? "destructive" : "secondary"}>
              {t("dashboard.portfolioBreached", { count: data.breached })}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {data.portfolios.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            {t("dashboard.noAuthorizedPortfolios")}
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.portfolios.map((portfolio) => {
              const selected = portfolio.port_id === selectedFundId
              const hasData = portfolio.status === "ok"
              return (
                <button
                  type="button"
                  key={portfolio.port_id}
                  onClick={() => onSelect(portfolio.port_id)}
                  className={`rounded-lg border p-4 text-left transition-colors hover:border-primary/60 hover:bg-muted/30 ${selected ? "border-primary bg-primary/5 ring-1 ring-primary/20" : ""}`}
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{portfolio.port_name}</p>
                    <p className="text-xs text-muted-foreground">{portfolio.port_id} · {portfolio.port_type}</p>
                  </div>

                  <div className="mt-3 space-y-1.5 text-xs">
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <UserRound className="h-3.5 w-3.5 shrink-0" />
                      <span className="shrink-0">{t("dashboard.investmentManager")}:</span>
                      <span className="truncate font-medium text-foreground">
                        {portfolio.manager_name || t("dashboard.unassigned")}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <Users className="h-3.5 w-3.5 shrink-0" />
                      <span className="shrink-0">{t("dashboard.platformManager")}:</span>
                      <span className="truncate">
                        {portfolio.manage_users || t("dashboard.unassigned")}
                      </span>
                    </div>
                  </div>

                  {hasData ? (
                    <>
                      <div className="mt-4 grid grid-cols-3 gap-3 text-xs">
                        <div>
                          <p className="text-muted-foreground">NAV</p>
                          <p className="mt-1 font-mono font-medium">{((portfolio.total_nav_hkd ?? 0) / 1e8).toFixed(2)} {t("dashboard.hundredMillion")}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">WAM</p>
                          <p className="mt-1 font-mono font-medium">{(portfolio.wam_days ?? 0).toFixed(1)} {t("dashboard.days")}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">WAL</p>
                          <p className="mt-1 font-mono font-medium">{(portfolio.wal_days ?? 0).toFixed(1)} {t("dashboard.days")}</p>
                        </div>
                      </div>
                      <div className="mt-4 flex items-center justify-between">
                        <Badge variant={portfolio.is_compliant ? "secondary" : "destructive"}>
                          {portfolio.is_compliant
                            ? t("dashboard.fullyCompliant")
                            : t("dashboard.breaches", { count: portfolio.breach_count ?? 0 })}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{portfolio.effective_date}</span>
                      </div>
                    </>
                  ) : (
                    <p className="mt-4 text-sm text-muted-foreground">
                      {portfolio.status === "no_data" ? t("dashboard.portfolioNoData") : t("dashboard.portfolioLoadError")}
                    </p>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ExposureDashboard({ data }: { data: ExposureResult }) {
  const { t } = useTranslation()
  const nav = (data.total_nav_hkd / 1e8).toFixed(2)
  const [expandedGroups, setExpandedGroups] = useState<Partial<Record<SourceGroup, boolean>>>({})
  const complianceDetails = data.compliance_details ?? []
  const detailMap = new Map(complianceDetails.map((item) => [item.breach_code, item]))

  type SourceGroup = "regulatory" | "contract" | "internal"

  function getSourceGroup(ruleCode: string): SourceGroup {
    const trace = data.rule_trace?.[ruleCode]
    if (!trace) return "internal"

    const entries: Array<{ key: SourceGroup; value: number }> = [
      { key: "regulatory", value: trace.regulatory },
      { key: "contract", value: trace.contract },
      { key: "internal", value: trace.internal },
    ]
    entries.sort((a, b) => b.value - a.value)

    return entries[0].key
  }

  function sourceGroupLabel(group: SourceGroup) {
    if (group === "regulatory") return t("dashboard.sourceRegulatory")
    if (group === "contract") return t("dashboard.sourceContract")
    if (group === "internal") return t("dashboard.sourceInternal")
    return t("dashboard.sourceInternal")
  }

  function formatCurrentValue(detail: (typeof complianceDetails)[number]) {
    if (detail.unit === "PCT") return `${detail.current_value.toFixed(2)}%`
    return `${detail.current_value.toFixed(1)} ${t("dashboard.days")}`
  }

  function formatLimitValue(detail: (typeof complianceDetails)[number]) {
    const val = detail.unit === "PCT" ? `${detail.limit_value}%` : `${detail.limit_value} ${t("dashboard.days")}`
    return `${detail.operator} ${val}`
  }

  function formatBreachGap(detail: (typeof complianceDetails)[number]) {
    const delta = detail.operator === "<="
      ? detail.current_value - detail.limit_value
      : detail.limit_value - detail.current_value

    if (delta <= 0) {
      return t("dashboard.withinLimit")
    }

    if (detail.unit === "PCT") {
      return t("dashboard.exceedBy", { value: `${delta.toFixed(2)}%` })
    }
    return t("dashboard.exceedBy", { value: `${delta.toFixed(1)} ${t("dashboard.days")}` })
  }

  const sourceCounts = {
    regulatory: 0,
    contract: 0,
    internal: 0,
  } as Record<SourceGroup, number>

  const groupedDetails = complianceDetails.reduce<Record<SourceGroup, typeof complianceDetails>>(
    (acc, detail) => {
      const group = getSourceGroup(detail.rule_code)
      sourceCounts[group] += 1
      acc[group].push(detail)
      return acc
    },
    {
      regulatory: [],
      contract: [],
      internal: [],
    },
  )

  const breachedRules = complianceDetails.filter((item) => item.is_breached).length
  const sourceOrder: SourceGroup[] = ["regulatory", "contract", "internal"]
  const topAssetAllocation = Object.entries(data.by_asset_type)
    .sort((a, b) => b[1].pct - a[1].pct)
    .slice(0, 3)

  function renderLimit(breachCode: string, fallback: string) {
    const detail = detailMap.get(breachCode)
    if (!detail) return fallback
    const val = detail.unit === "PCT" ? `${detail.limit_value}%` : `${detail.limit_value} ${t("dashboard.days")}`
    return `${detail.operator} ${val}`
  }

  function renderValue(breachCode: string, fallback: string) {
    const detail = detailMap.get(breachCode)
    if (!detail) return fallback
    if (detail.unit === "PCT") return `${detail.current_value.toFixed(2)}%`
    return `${detail.current_value.toFixed(1)} ${t("dashboard.days")}`
  }

  function renderSource(breachCode: string) {
    const detail = detailMap.get(breachCode)
    if (!detail || !data.rule_trace) return undefined
    const trace = data.rule_trace[detail.rule_code]
    if (!trace) return undefined
    const parts = [
      `R:${trace.regulatory}`,
      `C:${trace.contract}`,
      `I:${trace.internal}`,
    ]
    return trace.used_default
      ? `${t("dashboard.defaultBaseline")} (${parts.join("/")})`
      : `${t("dashboard.customConfig")} (${parts.join("/")})`
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title={t("dashboard.totalNav")}
          value={`HKD ${nav} ${t("dashboard.hundredMillion")}`}
          icon={Waves}
          status="ok"
        />
        <MetricCard
          title={t("dashboard.wam")}
          value={renderValue("WAM_BREACH", `${data.wam_days.toFixed(1)} ${t("dashboard.days")}`)}
          limit={t("dashboard.limit", { value: renderLimit("WAM_BREACH", `≤ 60 ${t("dashboard.days")}`) })}
          status={
            data.wam_days > 60 ? "breach" : data.wam_days > 50 ? "warn" : "ok"
          }
          icon={TrendingDown}
        />
        <MetricCard
          title={t("dashboard.wal")}
          value={renderValue("WAL_BREACH", `${data.wal_days.toFixed(1)} ${t("dashboard.days")}`)}
          limit={t("dashboard.limit", { value: renderLimit("WAL_BREACH", `≤ 120 ${t("dashboard.days")}`) })}
          status={
            data.wal_days > 120
              ? "breach"
              : data.wal_days > 100
                ? "warn"
                : "ok"
          }
          icon={TrendingDown}
        />
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{t("dashboard.assetAllocation")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {topAssetAllocation.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("dashboard.noData", { fund: data.fund_id, date: data.as_of_date })}</p>
            ) : (
              topAssetAllocation.map(([type, v]) => (
                <div key={type} className="flex items-center gap-2">
                  <span className="w-20 truncate text-xs text-muted-foreground">{type}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(v.pct, 100)}%` }} />
                  </div>
                  <span className="w-12 text-right text-xs font-mono">{v.pct.toFixed(1)}%</span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("dashboard.riskComplianceCheck")}</CardTitle>
            <p className={`text-sm ${data.is_compliant ? "text-green-700" : "text-red-700"}`}>
              {data.is_compliant
                ? t("dashboard.complianceSummaryOk")
                : t("dashboard.complianceSummaryBreach", { count: breachedRules })}
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {sourceOrder.map((group) => {
                const count = sourceCounts[group]
                return (
                  <Badge key={group} variant="outline">
                    {sourceGroupLabel(group)}: {count}
                  </Badge>
                )
              })}
            </div>

            {complianceDetails.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("dashboard.noRuleDetails")}</p>
            ) : (
              <div className="space-y-3">
                {sourceOrder.map((group) => {
                  const details = groupedDetails[group]

                  const orderedDetails = [...details].sort((a, b) => Number(b.is_breached) - Number(a.is_breached))
                  const previewCount = 3
                  const isExpanded = expandedGroups[group] ?? false
                  const visibleDetails = isExpanded ? orderedDetails : orderedDetails.slice(0, previewCount)
                  const hiddenCount = Math.max(orderedDetails.length - visibleDetails.length, 0)

                  return (
                    <div key={group} className="rounded-lg border bg-card/50 p-3">
                      <div className="mb-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">{sourceGroupLabel(group)}</span>
                          <Badge variant="outline" className="h-5 px-2 text-[10px]">
                            {details.length}
                          </Badge>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {details.filter((item) => item.is_breached).length > 0
                            ? t("dashboard.breaches", { count: details.filter((item) => item.is_breached).length })
                            : t("dashboard.fullyCompliant")}
                        </span>
                      </div>

                      {visibleDetails.length === 0 ? (
                        <div className="rounded-md border border-dashed bg-background/60 p-3 text-sm text-muted-foreground">
                          {t("dashboard.noRuleInGroup")}
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {visibleDetails.map((detail) => {
                            const sourceText = renderSource(detail.breach_code)
                            return (
                              <div key={`${detail.rule_code}-${detail.breach_code}`} className="rounded-md border bg-background p-2">
                                <div className="flex items-center justify-between gap-3">
                                  <div>
                                    <p className="text-sm font-medium">{detail.rule_name}</p>
                                    <p className="text-xs text-muted-foreground">{t("dashboard.ruleCode")}: {detail.rule_code}</p>
                                  </div>
                                  <Badge variant={detail.is_breached ? "destructive" : "secondary"} className="whitespace-nowrap">
                                    {detail.is_breached ? t("dashboard.breach") : t("dashboard.compliant")}
                                  </Badge>
                                </div>
                                <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                                  <span>{t("dashboard.current")}: {formatCurrentValue(detail)}</span>
                                  <span>{t("dashboard.threshold")}: {formatLimitValue(detail)}</span>
                                  <span>{formatBreachGap(detail)}</span>
                                </div>
                                {sourceText ? <p className="mt-2 text-xs text-muted-foreground">{t("dashboard.source")}: {sourceText}</p> : null}
                              </div>
                            )
                          })}
                        </div>
                      )}

                      {hiddenCount > 0 ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2 h-7 px-2 text-xs"
                          onClick={() => setExpandedGroups((prev) => ({ ...prev, [group]: true }))}
                        >
                          {t("dashboard.expandMore", { count: hiddenCount })}
                        </Button>
                      ) : details.length > previewCount ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="mt-2 h-7 px-2 text-xs"
                          onClick={() => setExpandedGroups((prev) => ({ ...prev, [group]: false }))}
                        >
                          {t("dashboard.collapse")}
                        </Button>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function Dashboard() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [fundId, setFundId] = useState("")
  const [asOfDate, setAsOfDate] = useState(lastTradeDate)

  const accessQuery = useQuery({
    queryKey: ["my-access-context"],
    queryFn: () => fsiApi.getMyAccessContext().then((response) => response.data),
    staleTime: 30_000,
  })
  const authorizedPortfolios = accessQuery.data?.portfolios ?? []

  useEffect(() => {
    if (authorizedPortfolios.length === 0) {
      if (fundId) setFundId("")
      return
    }
    if (!authorizedPortfolios.some((portfolio) => portfolio.port_id === fundId)) {
      setFundId(authorizedPortfolios[0].port_id)
    }
  }, [authorizedPortfolios, fundId])

  const overviewQuery = useQuery({
    queryKey: ["portfolio-dashboard-overview", asOfDate],
    queryFn: () => fsiApi.getDashboardOverview(asOfDate).then((response) => response.data),
    enabled: accessQuery.isSuccess,
    staleTime: 30_000,
    retry: 1,
  })

  const latestDateQuery = useQuery({
    queryKey: ["exposure-latest-date", fundId, asOfDate],
    queryFn: () => resolveLatestExposureDate(fundId, asOfDate),
    enabled: Boolean(fundId),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 0,
  })

  const effectiveDate = latestDateQuery.data?.effectiveDate ?? asOfDate

  const exposureQuery = useQuery({
    queryKey: ["exposure", fundId, effectiveDate],
    queryFn: () => fsiApi.getExposure(fundId, effectiveDate).then((r) => r.data),
    enabled: Boolean(fundId) && !latestDateQuery.isFetching && !latestDateQuery.isError,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 1,
  })

  const exposureData = exposureQuery.data
  const fallbackUsed = latestDateQuery.data?.fallbackUsed ?? false
  const isFetching = latestDateQuery.isFetching || exposureQuery.isFetching
  const isAnyFetching = accessQuery.isFetching || overviewQuery.isFetching || isFetching
  const isError = latestDateQuery.isError || exposureQuery.isError

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("dashboard.title")}</h1>
          <p className="text-muted-foreground text-sm">
            {t("dashboard.welcome", {
              user: user?.full_name || user?.email,
              date: asOfDate,
            })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <DatePicker value={asOfDate} onChange={setAsOfDate} />
          <Button
            variant="outline"
            size="icon"
            onClick={() => {
              if (fundId) latestExposureDateCache.delete(fundId)
              void accessQuery.refetch()
              void overviewQuery.refetch()
              if (fundId) {
                void latestDateQuery.refetch()
                void exposureQuery.refetch()
              }
            }}
            disabled={isAnyFetching}
            title={t("dashboard.reload")}
          >
            <RefreshCw className={`h-4 w-4 ${isAnyFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {overviewQuery.isFetching ? (
        <p className="text-muted-foreground text-sm animate-pulse">{t("dashboard.loadingPortfolios")}</p>
      ) : null}
      {overviewQuery.data ? (
        <AllPortfolioOverview
          data={overviewQuery.data}
          selectedFundId={fundId}
          onSelect={setFundId}
        />
      ) : null}
      {accessQuery.isSuccess && authorizedPortfolios.length === 0 ? (
        <Card className="border-orange-300 bg-orange-50/30">
          <CardContent className="pt-4 text-sm text-orange-800">
            {t("dashboard.noAuthorizedPortfolios")}
          </CardContent>
        </Card>
      ) : null}
      {overviewQuery.isError ? (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">{t("dashboard.portfolioOverviewError")}</CardContent>
        </Card>
      ) : null}

      {authorizedPortfolios.length > 0 ? (
        <div className="flex flex-col gap-3 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold">{t("dashboard.selectedPortfolioDetail")}</h2>
            <p className="text-sm text-muted-foreground">{t("dashboard.selectedPortfolioHint")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Select value={fundId} onValueChange={setFundId}>
              <SelectTrigger className="w-72">
                <SelectValue placeholder={t("dashboard.selectFund")} />
              </SelectTrigger>
              <SelectContent>
                {authorizedPortfolios.map((portfolio) => (
                  <SelectItem key={portfolio.port_id} value={portfolio.port_id}>
                    {portfolio.port_name} · {portfolio.access_level}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {fallbackUsed ? <Badge variant="secondary">{t("dashboard.autoFallback")}: {effectiveDate}</Badge> : null}
          </div>
        </div>
      ) : null}

      {isFetching && fundId ? (
        <p className="text-muted-foreground text-sm animate-pulse">{t("dashboard.loading")}</p>
      ) : null}
      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-4 text-sm text-destructive">
            {t("dashboard.apiError")}
          </CardContent>
        </Card>
      )}
      {exposureData && exposureData.total_nav_hkd === 0 && !isFetching && (
        <Card className="border-yellow-500/50">
          <CardContent className="pt-4 text-sm text-yellow-600">
            {t("dashboard.noData", {
              fund: fundId,
              date: asOfDate,
            })}
          </CardContent>
        </Card>
      )}
      {exposureData && exposureData.total_nav_hkd > 0 && <ExposureDashboard data={exposureData} />}
    </div>
  )
}
