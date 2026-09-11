import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowRight,
  BrainCircuit,
  Database,
  Download,
  Filter,
  Search,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Workflow,
} from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

import { FUNDS, lastTradeDate } from "@/components/FsiToolbar"
import { DatePicker } from "@/components/DatePicker"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fsiApi, type PortfolioOverviewResult } from "@/fsiClient"
import { INVESTMENT_RISK_TOPICS, type InvestmentRiskTopic } from "@/modules/investment-risk/content"

const integrationItems = [
  {
    titleKey: "investmentRisk.module.integrationProcessingTitle",
    descKey: "investmentRisk.module.integrationProcessingDesc",
    icon: Workflow,
  },
  {
    titleKey: "investmentRisk.module.integrationStorageTitle",
    descKey: "investmentRisk.module.integrationStorageDesc",
    icon: Database,
  },
  {
    titleKey: "investmentRisk.module.integrationAgentTitle",
    descKey: "investmentRisk.module.integrationAgentDesc",
    icon: BrainCircuit,
  },
]

type RiskSeverity = "high" | "medium"

const riskItems: Array<{
  id: string
  nameKey: string
  bucketKey: string
  severity: RiskSeverity
  score: number
  statusKey: string
  updatedAt: string
}> = [
  {
    id: "R-1021",
    nameKey: "investmentRisk.module.riskName1",
    bucketKey: "investmentRisk.module.exposureCredit",
    severity: "high",
    score: 82,
    statusKey: "investmentRisk.module.riskStatus1",
    updatedAt: "2026-08-02",
  },
  {
    id: "R-1038",
    nameKey: "investmentRisk.module.riskName2",
    bucketKey: "investmentRisk.module.exposureLiquidity",
    severity: "medium",
    score: 67,
    statusKey: "investmentRisk.module.riskStatus2",
    updatedAt: "2026-08-01",
  },
  {
    id: "R-1042",
    nameKey: "investmentRisk.module.riskName3",
    bucketKey: "investmentRisk.module.exposureRates",
    severity: "high",
    score: 79,
    statusKey: "investmentRisk.module.riskStatus3",
    updatedAt: "2026-08-02",
  },
  {
    id: "R-1051",
    nameKey: "investmentRisk.module.riskName4",
    bucketKey: "investmentRisk.module.exposureFactor",
    severity: "medium",
    score: 61,
    statusKey: "investmentRisk.module.riskStatus4",
    updatedAt: "2026-07-31",
  },
]

function shiftDate(dateText: string, offsetDays: number) {
  const date = new Date(`${dateText}T00:00:00`)
  date.setDate(date.getDate() + offsetDays)
  return date.toISOString().split("T")[0]
}

function hasOverviewData(data: PortfolioOverviewResult) {
  return (
    !!data.portfolio?.data_date
    && (data.asset_allocation.length > 0 || data.top_stocks.length > 0 || data.performance.length > 0)
  )
}

async function loadOverviewWithFallback(fundId: string, selectedDate: string, lookbackDays = 365) {
  for (let step = 0; step <= lookbackDays; step += 1) {
    const probeDate = shiftDate(selectedDate, -step)
    const response = await fsiApi.getPortfolioOverview(fundId, probeDate)
    if (hasOverviewData(response.data)) {
      return {
        payload: response.data,
        effectiveDate: probeDate,
        fallbackUsed: step > 0,
      }
    }
  }
  throw new Error("在回溯區間內未找到可用數據")
}

function money(value: number | null | undefined, currency = "HKD") {
  if (value == null) return "—"
  return new Intl.NumberFormat("zh-HK", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(value))
}

function percent(value: number | null | undefined, digits = 2) {
  if (value == null) return "—"
  return `${Number(value).toFixed(digits)}%`
}

function buildLinePath(values: number[]) {
  const width = 360
  const height = 170
  const maxValue = Math.max(...values)
  const minValue = Math.min(...values)
  const range = maxValue - minValue || 1

  return values
    .map((value, index) => {
      const x = 20 + (index / (values.length - 1)) * (width - 40)
      const normalized = (value - minValue) / range
      const y = height - 30 - normalized * (height - 60)
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
}

export function InvestmentRiskModuleHome() {
  const { t } = useTranslation()
  const [selectedTopic, setSelectedTopic] = useState<InvestmentRiskTopic["id"]>(INVESTMENT_RISK_TOPICS[0].id)
  const [selectedFundId, setSelectedFundId] = useState(FUNDS[0].id)
  const [analysisDate, setAnalysisDate] = useState(lastTradeDate)
  const [searchQuery, setSearchQuery] = useState("")
  const [severityFilter, setSeverityFilter] = useState("all")
  const [timeWindow, setTimeWindow] = useState("30D")

  const selectedTopicMeta = INVESTMENT_RISK_TOPICS.find((topic) => topic.id === selectedTopic) ?? INVESTMENT_RISK_TOPICS[0]
  const dashboardQuery = useQuery({
    queryKey: ["investment-home-dashboard", selectedFundId, analysisDate],
    queryFn: () => loadOverviewWithFallback(selectedFundId, analysisDate),
    retry: 0,
  })

  const dashboardData = dashboardQuery.data?.payload
  const effectiveDate = dashboardQuery.data?.effectiveDate ?? analysisDate
  const fallbackUsed = dashboardQuery.data?.fallbackUsed ?? false

  const trendValues = useMemo(() => {
    const values = dashboardData?.performance.map((item) => item.return_pct) ?? []
    return values.length > 1 ? values : []
  }, [dashboardData?.performance])

  const trendLabels = useMemo(() => {
    const labels = dashboardData?.performance.map((item) => item.period) ?? []
    return labels.length > 1
      ? labels
      : [
          t("investmentRisk.module.weekdayMon"),
          t("investmentRisk.module.weekdayTue"),
          t("investmentRisk.module.weekdayWed"),
          t("investmentRisk.module.weekdayThu"),
          t("investmentRisk.module.weekdayFri"),
          t("investmentRisk.module.weekdaySat"),
          t("investmentRisk.module.weekdaySun"),
        ]
  }, [dashboardData?.performance, t])

  const exposureMixData = useMemo(() => {
    const items = (dashboardData?.asset_allocation ?? [])
      .slice(0, 4)
      .map((item) => ({ label: item.asset_class, value: Math.max(0, Math.min(100, item.weight_pct)) }))
    return items.length ? items : []
  }, [dashboardData?.asset_allocation, t])

  const dashboardRows = useMemo(() => {
    const dataDate = dashboardData?.portfolio.data_date ?? effectiveDate
    const top3Concentration = (dashboardData?.top_stocks ?? []).slice(0, 3).reduce((sum, item) => sum + item.weight_pct, 0)
    const dayReturnPct = dashboardData?.portfolio.day_return == null ? null : Number(dashboardData.portfolio.day_return) * 100
    return [
      {
        metric: t("investmentRisk.module.metricNetAsset", { date: dataDate }),
        value: money(dashboardData?.portfolio.net_asset, dashboardData?.portfolio.base_currency ?? "HKD"),
        status: dashboardData ? t("investmentRisk.module.statusUpdated") : "—",
      },
      {
        metric: t("investmentRisk.module.metricDayReturn"),
        value: percent(dayReturnPct, 3),
        status: dayReturnPct != null && dayReturnPct < 0 ? t("investmentRisk.module.statusVolatile") : t("investmentRisk.module.statusStable"),
      },
      {
        metric: t("investmentRisk.module.metricTop3"),
        value: percent(top3Concentration, 2),
        status: top3Concentration > 35 ? t("investmentRisk.module.statusWatch") : t("investmentRisk.module.statusNormal"),
      },
    ]
  }, [dashboardData, effectiveDate, t])

  const severityLabel = (severity: RiskSeverity) =>
    severity === "high" ? t("investmentRisk.module.severityHigh") : t("investmentRisk.module.severityMedium")

  const filteredItems = useMemo(() => {
    return riskItems.filter((item) => {
      const name = t(item.nameKey)
      const bucket = t(item.bucketKey)
      const matchesSearch = `${item.id} ${name} ${bucket}`.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesSeverity = severityFilter === "all" || item.severity === severityFilter
      return matchesSearch && matchesSeverity
    })
  }, [searchQuery, severityFilter, t])

  function handleExport() {
    const header = [
      t("investmentRisk.module.csvRiskId"),
      t("investmentRisk.module.csvName"),
      t("investmentRisk.module.csvCategory"),
      t("investmentRisk.module.csvSeverity"),
      t("investmentRisk.module.csvScore"),
      t("investmentRisk.module.csvStatus"),
      t("investmentRisk.module.csvUpdatedAt"),
    ]
    const body = filteredItems.map((item) => [item.id, t(item.nameKey), t(item.bucketKey), severityLabel(item.severity), item.score, t(item.statusKey), item.updatedAt])
    const csv = [header, ...body]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
      .join("\n")

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `investment-risk-${timeWindow}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline">{t("investmentRisk.module.independentBadge")}</Badge>
          <Badge variant="secondary">Investment Risk</Badge>
        </div>
        <h1 className="text-2xl font-bold tracking-tight">{t("investmentRisk.module.title")}</h1>
        <p className="max-w-4xl text-sm text-muted-foreground">
          {t("investmentRisk.module.description")}
        </p>
      </div>

      <Card className="border-primary/20 bg-gradient-to-br from-background to-primary/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            {t("investmentRisk.module.dashboardTitle")}
          </CardTitle>
          <CardDescription>{t("investmentRisk.module.dashboardSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <Select value={selectedFundId} onValueChange={setSelectedFundId}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder={t("investmentRisk.module.selectFund")} />
              </SelectTrigger>
              <SelectContent>
                {FUNDS.map((fund) => (
                  <SelectItem key={fund.id} value={fund.id}>
                    {fund.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DatePicker value={analysisDate} onChange={setAnalysisDate} />
            <Badge variant="outline">{t("investmentRisk.module.effectiveDate", { date: effectiveDate })}</Badge>
            {fallbackUsed ? <Badge variant="secondary">{t("investmentRisk.module.autoFallback")}</Badge> : null}
          </div>
          {dashboardQuery.isFetching ? <p className="text-sm text-muted-foreground">{t("investmentRisk.module.loadingLatest")}</p> : null}
          {dashboardQuery.isError ? <p className="text-sm text-destructive">{t("investmentRisk.module.dashboardLoadError")}</p> : null}
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border bg-background/80 p-4">
              <p className="text-xs text-muted-foreground">{t("investmentRisk.module.currentExposure")}</p>
              <p className="mt-2 text-2xl font-semibold">{percent((dashboardData?.asset_allocation ?? []).slice(0, 2).reduce((sum, item) => sum + item.weight_pct, 0), 2)}</p>
              <p className="mt-1 text-xs text-emerald-600">{t("investmentRisk.module.currentExposureHint")}</p>
            </div>
            <div className="rounded-lg border bg-background/80 p-4">
              <p className="text-xs text-muted-foreground">{t("investmentRisk.module.stressCoverage")}</p>
              <p className="mt-2 text-2xl font-semibold">{dashboardData?.performance.length ?? 0}</p>
              <p className="mt-1 text-xs text-muted-foreground">{t("investmentRisk.module.stressCoverageHint")}</p>
            </div>
            <div className="rounded-lg border bg-background/80 p-4">
              <p className="text-xs text-muted-foreground">{t("investmentRisk.module.tradeBudget")}</p>
              <p className="mt-2 text-2xl font-semibold">{money(dashboardData?.portfolio.net_asset, dashboardData?.portfolio.base_currency ?? "HKD")}</p>
              <p className="mt-1 text-xs text-amber-600">{t("investmentRisk.module.tradeBudgetHint")}</p>
            </div>
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.3fr_0.9fr]">
            <div className="rounded-lg border bg-background/70 p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">{t("investmentRisk.module.riskTrendTitle")}</p>
                  <p className="text-xs text-muted-foreground">{t("investmentRisk.module.riskTrendSubtitle")}</p>
                </div>
                <Badge variant="outline">{timeWindow}</Badge>
              </div>
              <svg viewBox="0 0 360 170" className="h-48 w-full">
                <line x1="20" y1="140" x2="340" y2="140" stroke="currentColor" strokeOpacity="0.25" />
                <line x1="20" y1="95" x2="340" y2="95" stroke="currentColor" strokeOpacity="0.15" />
                <line x1="20" y1="50" x2="340" y2="50" stroke="currentColor" strokeOpacity="0.15" />
                {trendValues.length > 1 ? (
                  <>
                    <path d={buildLinePath(trendValues)} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinecap="round" />
                    {trendValues.map((value, index) => {
                      const maxValue = Math.max(...trendValues)
                      const minValue = Math.min(...trendValues)
                      const range = maxValue - minValue || 1
                      const x = 20 + (index / (trendValues.length - 1)) * 320
                      const normalized = (value - minValue) / range
                      const y = 140 - normalized * 90
                      return <circle key={`${value}-${index}`} cx={x} cy={y} r="4.5" fill="#38bdf8" />
                    })}
                  </>
                ) : (
                  <text x="180" y="85" textAnchor="middle" className="fill-current text-xs" fill="currentColor">{t("platform.empty")}</text>
                )}
              </svg>
              <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                {trendLabels.map((label) => (
                  <span key={label}>{label}</span>
                ))}
              </div>
            </div>

            <div className="rounded-lg border bg-background/70 p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold">{t("investmentRisk.module.riskFactorTitle")}</p>
                  <p className="text-xs text-muted-foreground">{t("investmentRisk.module.riskFactorSubtitle")}</p>
                </div>
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <TrendingUp className="h-4 w-4" />
                  {t("investmentRisk.module.updating")}
                </div>
              </div>
              <div className="space-y-3">
                {exposureMixData.length ? exposureMixData.map((item) => (
                  <div key={item.label}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span>{item.label}</span>
                      <span className="text-muted-foreground">{item.value}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-muted">
                      <div className="h-2 rounded-full bg-primary" style={{ width: `${item.value}%` }} />
                    </div>
                  </div>
                )) : (
                  <p className="text-sm text-muted-foreground">{t("platform.empty")}</p>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert className="h-4 w-4" />
            {t("investmentRisk.module.analysisListTitle")}
          </CardTitle>
          <CardDescription>{t("investmentRisk.module.analysisListSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 rounded-md border px-3 py-2">
              <Search className="h-4 w-4 text-muted-foreground" />
              <Input
                className="h-8 border-0 p-0 shadow-none focus-visible:ring-0"
                placeholder={t("investmentRisk.module.searchRisk")}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <div className="flex items-center gap-2 rounded-md border px-3 py-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <Select value={severityFilter} onValueChange={setSeverityFilter}>
                <SelectTrigger className="h-8 w-32 border-0 p-0 shadow-none">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("investmentRisk.module.severityAll")}</SelectItem>
                  <SelectItem value="high">{t("investmentRisk.module.severityHigh")}</SelectItem>
                  <SelectItem value="medium">{t("investmentRisk.module.severityMedium")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Select value={timeWindow} onValueChange={setTimeWindow}>
              <SelectTrigger className="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7D">7D</SelectItem>
                <SelectItem value="30D">30D</SelectItem>
                <SelectItem value="90D">90D</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={handleExport}>
              <Download className="mr-2 h-4 w-4" />
              {t("investmentRisk.module.exportCsv")}
            </Button>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("investmentRisk.module.colRiskId")}</TableHead>
                <TableHead>{t("investmentRisk.module.colName")}</TableHead>
                <TableHead>{t("investmentRisk.module.colCategory")}</TableHead>
                <TableHead>{t("investmentRisk.module.colSeverity")}</TableHead>
                <TableHead>{t("investmentRisk.module.colScore")}</TableHead>
                <TableHead>{t("investmentRisk.module.colStatus")}</TableHead>
                <TableHead>{t("investmentRisk.module.colUpdatedAt")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredItems.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-mono">{item.id}</TableCell>
                  <TableCell>{t(item.nameKey)}</TableCell>
                  <TableCell>{t(item.bucketKey)}</TableCell>
                  <TableCell>{severityLabel(item.severity)}</TableCell>
                  <TableCell>{item.score}</TableCell>
                  <TableCell>{t(item.statusKey)}</TableCell>
                  <TableCell>{item.updatedAt}</TableCell>
                </TableRow>
              ))}
              {!filteredItems.length && (
                <TableRow>
                  <TableCell colSpan={7} className="h-16 text-center text-muted-foreground">
                    {t("investmentRisk.module.emptyItems")}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            {t("investmentRisk.module.quickEntryTitle")}
          </CardTitle>
          <CardDescription>{t("investmentRisk.module.quickEntrySubtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Select value={selectedTopic} onValueChange={(value) => setSelectedTopic(value as InvestmentRiskTopic["id"])}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder={t("investmentRisk.module.selectTopic")} />
              </SelectTrigger>
              <SelectContent>
                {INVESTMENT_RISK_TOPICS.map((topic) => (
                  <SelectItem key={topic.id} value={topic.id}>
                    {t(topic.titleKey)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DatePicker value={analysisDate} onChange={setAnalysisDate} />
            <Button asChild>
              <Link to={`/investment-risk/${selectedTopicMeta.id}`}>
                {t("investmentRisk.module.openPage")}
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
              <ShieldAlert className="h-4 w-4" />
              {t(selectedTopicMeta.titleKey)} · {effectiveDate}
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("investmentRisk.module.metricCol")}</TableHead>
                  <TableHead>{t("investmentRisk.module.currentValueCol")}</TableHead>
                  <TableHead>{t("investmentRisk.module.statusCol")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dashboardRows.map((row) => (
                  <TableRow key={row.metric}>
                    <TableCell>{row.metric}</TableCell>
                    <TableCell>{row.value}</TableCell>
                    <TableCell>{row.status}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {INVESTMENT_RISK_TOPICS.map((topic) => {
          const capabilities = t(topic.capabilitiesKey, { returnObjects: true }) as string[]
          return (
            <Card key={topic.id} className="h-full">
              <CardHeader>
                <CardTitle className="text-base">{t(topic.titleKey)}</CardTitle>
                <CardDescription>{topic.subtitle}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">{t(topic.summaryKey)}</p>
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {capabilities.slice(0, 3).map((capability) => (
                    <li key={capability}>{capability}</li>
                  ))}
                </ul>
                <Button asChild variant="outline" size="sm">
                  <Link to={`/investment-risk/${topic.id}`}>
                    {t("investmentRisk.module.openPage")}
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("investmentRisk.module.integrationTitle")}</CardTitle>
          <CardDescription>{t("investmentRisk.module.integrationSubtitle")}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 lg:grid-cols-3">
          {integrationItems.map((item) => (
            <div key={item.titleKey} className="rounded-lg border p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <item.icon className="h-4 w-4" />
                {t(item.titleKey)}
              </div>
              <p className="text-sm text-muted-foreground">{t(item.descKey)}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
